"""Authenticated loopback bridge for the optional Chromium DOM reader."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time


PORT = 51394
CONFIG_FILE = Path(__file__).resolve().parent / 'browser_extension' / 'bridge-config.json'


class WebBridge:
    def __init__(self, port=PORT, config_file=CONFIG_FILE):
        self.lock = threading.Lock()
        self.regions = None
        self.generation = 0
        self.snapshot = None
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            saved = json.loads(self.config_file.read_text(encoding='utf-8'))
            token = saved['token']
            if not isinstance(token, str) or len(token) != 48:
                raise ValueError('invalid token')
        except (OSError, KeyError, ValueError, TypeError):
            token = secrets.token_hex(24)
        self.token = token
        self.server = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
        self.port = self.server.server_address[1]
        self.config_file.write_text(json.dumps({'port': self.port, 'token': token}), encoding='utf-8')
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name='web-dom-bridge', daemon=True)
        self.thread.start()

    def _handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _reply(self, status, value):
                data = json.dumps(value, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorized(self):
                return secrets.compare_digest(
                    self.headers.get('X-Web-MCQ-Token', ''), bridge.token)

            def do_GET(self):
                if not self._authorized():
                    return self._reply(403, {'error': 'forbidden'})
                if self.path != '/state':
                    return self._reply(404, {'error': 'not found'})
                with bridge.lock:
                    return self._reply(200, {'generation': bridge.generation,
                                             'regions': bridge.regions})

            def do_POST(self):
                if not self._authorized():
                    return self._reply(403, {'error': 'forbidden'})
                if self.path == '/clear':
                    bridge.clear_snapshot()
                    return self._reply(200, {'ok': True})
                if self.path != '/snapshot':
                    return self._reply(404, {'error': 'not found'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 200_000:
                        raise ValueError('size')
                    item = json.loads(self.rfile.read(length))
                    if not isinstance(item, dict) or not isinstance(item.get('boxes'), list):
                        raise ValueError('payload')
                    if len(item['boxes']) > 250:
                        raise ValueError('boxes')
                    boxes = []
                    for raw in item['boxes']:
                        if not isinstance(raw, dict) or not isinstance(raw.get('text'), str):
                            raise ValueError('box')
                        text = ' '.join(raw['text'].split())[:2000]
                        if not text:
                            continue
                        coords = [float(raw[k]) for k in ('left', 'top', 'right', 'bottom')]
                        if not all(-100 <= value <= 20000 for value in coords):
                            raise ValueError('coordinates')
                        left, top, right, bottom = coords
                        if right <= left or bottom <= top:
                            continue
                        boxes.append({'text': text, 'score': 1.0, 'left': left,
                                      'top': top, 'right': right, 'bottom': bottom,
                                      'cy': (top + bottom) / 2, 'height': bottom - top})
                    raw_sections = item.get('sections', [])
                    if not isinstance(raw_sections, list) or len(raw_sections) > 9:
                        raise ValueError('sections')
                    sections = []
                    for section in raw_sections:
                        if not isinstance(section, list) or len(section) > 100 or any(
                                not isinstance(line, str) for line in section):
                            raise ValueError('section')
                        sections.append([' '.join(line.split())[:2000]
                                         for line in section if line.strip()])
                    with bridge.lock:
                        if (item.get('generation') != bridge.generation or
                                item.get('regions') != bridge.regions or not bridge.regions):
                            return self._reply(409, {'error': 'stale region'})
                        bridge.snapshot = {'boxes': boxes, 'sections': sections,
                                           'regions': bridge.regions,
                                           'generation': bridge.generation,
                                           'received_at': time.monotonic(),
                                           'tab_url': str(item.get('tab_url', ''))[:500]}
                    return self._reply(200, {'ok': True})
                except (ValueError, KeyError, TypeError, OverflowError):
                    return self._reply(400, {'error': 'invalid snapshot'})

        return Handler

    def set_regions(self, regions):
        normalized = [list(region) for region in regions] if regions else None
        with self.lock:
            if normalized != self.regions:
                self.regions = normalized
                self.generation += 1
                self.snapshot = None

    def get_snapshot(self, regions, max_age=1.5):
        with self.lock:
            item = self.snapshot
            if (item and item['regions'] == [list(region) for region in regions] and
                    time.monotonic() - item['received_at'] <= max_age and
                    (len(item['boxes']) >= 5 or len(item['sections']) >= 3)):
                return dict(item, boxes=[dict(box) for box in item['boxes']])
        return None

    def clear_snapshot(self):
        with self.lock:
            self.snapshot = None
            self.generation += 1

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
