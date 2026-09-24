"""Managed llama.cpp on loopback. No cloud/API keys and no network downloads at runtime."""
import atexit
import json
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from src.process_guard import ProcessGuard

ROOT = Path(__file__).resolve().parents[1]


class LocalModel:
    def __init__(self, settings, cpu=False):
        self.settings = settings
        self.process = None
        self.guard = None
        self.log = None
        self.cpu = cpu
        self.key = secrets.token_urlsafe(32)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        atexit.register(self.close)

    def start(self):
        if self.process and self.process.poll() is None:
            return
        import psutil
        available = psutil.virtual_memory().available / (1024 * 1024)
        required = self.settings.get('min_available_ram_mib', 1536)
        if available < required:
            raise RuntimeError(f'RAM trống chỉ {available:.0f} MiB; cần ít nhất {required} MiB để nạp model. '
                               'Đóng bớt ứng dụng rồi mở lại tool.')
        executable, model = ROOT / self.settings['server'], ROOT / self.settings['model']
        if not executable.is_file() or not model.is_file():
            raise RuntimeError('Thiếu runtime hoặc model cục bộ. Xem README.md; không tự tải khi đang dùng.')
        # Ask Windows for a free local port; fail closed if it is taken before bind.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        args = [str(executable), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
                '--ctx-size', str(self.settings['context_size']), '--parallel', '1',
                '--threads', str(self.settings['threads']), '--threads-batch', str(self.settings['threads']),
                '--threads-http', '2', '--poll', '0', '--poll-batch', '0', '--prio', '-1',
                '--api-key', self.key,
                '--sleep-idle-seconds', str(self.settings.get('sleep_idle_seconds', 15)),
                '--batch-size', '128', '--ubatch-size', '64', '--no-webui', '--reasoning', 'off',
                '--flash-attn', 'on', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
                '--n-gpu-layers', '0' if self.cpu else '99']
        if not self.cpu:
            args += ['--device', self.settings['device']]
        (ROOT / 'logs').mkdir(exist_ok=True)
        self.log_path = ROOT / 'logs' / f'model-{port}.log'
        self.log = self.log_path.open('w', encoding='utf-8')
        self.process = subprocess.Popen(args, stdout=self.log, stderr=self.log,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            self.guard = ProcessGuard(self.process)
        except OSError:
            self.close()
            raise
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.close()
                raise RuntimeError(f'Không khởi động được model; xem {self.log_path}')
            try:
                if self.request('/health', timeout=1).get('status') == 'ok':
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.15)
        self.close()
        raise RuntimeError('Nạp model quá 90 giây; xem logs.')

    def request(self, path, data=None, timeout=45):
        payload = json.dumps(data).encode('utf-8') if data is not None else None
        req = urllib.request.Request(self.url + path, data=payload, headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        with self.opener.open(req, timeout=timeout) as response:
            return json.load(response)

    def chat(self, messages, schema):
        self.start()
        result = self.request('/v1/chat/completions', {
            'messages': messages, 'temperature': 0, 'seed': 42,
            'max_tokens': self.settings['max_tokens'],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'mcq', 'strict': True, 'schema': schema}}})
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise RuntimeError('Model chưa hoàn tất câu trả lời; không copy đáp án dở dang.')
        return json.loads(choice['message']['content'])

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
        if self.log:
            self.log.close()
            self.log = None
        if self.guard:
            self.guard.close()
            self.guard = None
