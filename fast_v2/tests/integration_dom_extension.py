"""Local one-off browser integration smoke test; not part of installed app."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_bridge import WebBridge
from src.layout import DomCapture
from clipboard_solver import ExamSolver


HTML = '''<!doctype html><meta charset="utf-8"><style>
body{font:20px Arial;margin:20px}.card{border:1px solid #ccd;padding:14px;margin:8px 0}
</style><h2>17. Trong CSS Box Model, thứ tự nào đúng?</h2>
<div class="card">A Margin → Border → Padding → Content</div>
<div class="card">B Padding → Border → Margin → Content</div>
<div class="card">C Border → Margin → Padding → Content</div>
<div class="card">D Content → Padding → Border → Margin</div>
<pre id="snippet">const names = ["A", "B"];
function pick(value) {
    if (value === "A") {
        return names[0];
    }
    return null;
}</pre>'''


class PageHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        data = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        page_server = ThreadingHTTPServer(('127.0.0.1', 0), PageHandler)
        page_thread = threading.Thread(target=page_server.serve_forever, daemon=True)
        page_thread.start()
        bridge = WebBridge(port=0, config_file=root / 'bridge-config.json')
        extension = root / 'extension'
        shutil.copytree(Path(__file__).resolve().parents[1] / 'browser_extension', extension)
        shutil.copy2(bridge.config_file, extension / 'bridge-config.json')
        site = f'http://127.0.0.1:{page_server.server_address[1]}'
        manifest = json.loads((extension / 'manifest.json').read_text(encoding='utf-8'))
        manifest['content_scripts'] = [{'matches': ['http://127.0.0.1/*'],
                                        'js': ['heartbeat.js']}]
        (extension / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(root / 'profile'),
                    headless=False, viewport={'width': 900, 'height': 600},
                    args=[f'--disable-extensions-except={extension}',
                          f'--load-extension={extension}',
                          '--window-position=-32000,-32000', '--window-size=900,600'])
                try:
                    page = browser.new_page()
                    page.goto(site, wait_until='networkidle')
                    region = page.evaluate('''() => {
                        const scale = devicePixelRatio || 1;
                        const side = Math.min(16, Math.max(0, (outerWidth-innerWidth)/2));
                        const ch = Math.max(0, outerHeight-innerHeight);
                        const bottom = ch > 24 ? Math.min(8, ch/5) : 0;
                        const x = (screenX+side)*scale, y=(screenY+ch-bottom)*scale;
                        return [x+10*scale,y+10*scale,x+850*scale,y+400*scale].map(Math.round);
                    }''')
                    bridge.set_regions([region])
                    started = time.monotonic()
                    deadline = time.monotonic() + 12
                    found = None
                    while time.monotonic() < deadline:
                        found = bridge.get_snapshot([region])
                        if found:
                            break
                        time.sleep(.2)
                    print('region', region)
                    print('workers', [worker.url for worker in browser.service_workers])
                    print('boxes', len(found['boxes']) if found else 0)
                    print('region_to_dom_seconds', round(time.monotonic() - started, 3))
                    if found:
                        print('text', [box['text'] for box in found['boxes']])
                    if not found:
                        raise RuntimeError('No DOM snapshot received from extension')
                    screen = Image.open(io.BytesIO(page.screenshot())).convert('RGB')
                    selected = screen.crop((10, 10, 850, 400))
                    solver = ExamSolver()
                    try:
                        prepared = solver.prepare_image(DomCapture(selected, tuple(found['boxes'])))
                        print('capture_source', prepared['capture_source'])
                        print('options', prepared.get('structured').options if prepared.get('structured') else None)
                        if prepared['capture_source'] != 'DOM':
                            raise RuntimeError('DOM text did not parse into question and options')
                        regions = page.evaluate('''() => {
                            const scale = devicePixelRatio || 1;
                            const side = Math.min(16, Math.max(0, (outerWidth-innerWidth)/2));
                            const ch = Math.max(0, outerHeight-innerHeight);
                            const bottom = ch > 24 ? Math.min(8, ch/5) : 0;
                            const x = (screenX+side)*scale, y=(screenY+ch-bottom)*scale;
                            return [...document.querySelectorAll('h2,.card')].map(el => {
                                const r = el.getBoundingClientRect();
                                return [x+(r.left-2)*scale,y+(r.top-2)*scale,
                                        x+(r.right+2)*scale,y+(r.bottom+2)*scale].map(Math.round);
                            });
                        }''')
                        bridge.set_regions(regions)
                        deadline = time.monotonic() + 5
                        manual = None
                        while time.monotonic() < deadline:
                            manual = bridge.get_snapshot(regions)
                            if manual:
                                break
                            time.sleep(.2)
                        if not manual or len(manual['sections']) != 5:
                            raise RuntimeError('Manual DOM regions did not arrive')
                        manual_prepared = solver.prepare_image(DomCapture(
                            selected, tuple(manual['boxes']), site,
                            tuple(manual['sections']), tuple(tuple(r) for r in regions)))
                        print('manual_source', manual_prepared['capture_source'])
                        print('manual_options', manual_prepared['structured'].options)
                        if manual_prepared['capture_source'] != 'DOM':
                            raise RuntimeError('Manual DOM regions fell back to OCR')
                        page.locator('#snippet').scroll_into_view_if_needed()
                        code_region = page.evaluate('''() => {
                            const r = document.querySelector('#snippet').getBoundingClientRect();
                            const scale = devicePixelRatio || 1;
                            const side = Math.min(16, Math.max(0, (outerWidth-innerWidth)/2));
                            const ch = Math.max(0, outerHeight-innerHeight);
                            const bottom = ch > 24 ? Math.min(8, ch/5) : 0;
                            const x = (screenX+side)*scale, y=(screenY+ch-bottom)*scale;
                            return [x+(r.left-2)*scale,y+(r.top-2)*scale,
                                    x+(r.right+2)*scale,y+(r.bottom+2)*scale].map(Math.round);
                        }''')
                        bridge.set_regions([code_region])
                        deadline = time.monotonic() + 5
                        code_snapshot = None
                        while time.monotonic() < deadline:
                            code_snapshot = bridge.get_snapshot([code_region])
                            if code_snapshot:
                                break
                            time.sleep(.2)
                        if not code_snapshot:
                            raise RuntimeError('Code DOM region did not arrive')
                        code_lines = [box['text'] for box in code_snapshot['boxes']]
                        print('code_lines', code_lines)
                        if '    if (value === "A") {' not in code_lines or '}' not in code_lines:
                            raise RuntimeError('Code indentation or closing brace was lost')
                    finally:
                        solver.close()
                finally:
                    browser.close()
        finally:
            bridge.close()
            page_server.shutdown()
            page_server.server_close()


if __name__ == '__main__':
    main()
