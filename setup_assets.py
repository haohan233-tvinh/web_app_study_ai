"""Download and verify the exact offline model and llama.cpp runtime used here."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'artifacts' / 'download-manifest.json'
MODEL_NAME = 'qwen2.5-3b-instruct-q4_k_m.gguf'
CUDA_ARCHIVES = ('llama-b11159-bin-win-cuda-12.4-x64.zip',
                 'cudart-llama-bin-win-cuda-12.4-x64.zip')
CPU_ARCHIVES = ('llama-b11159-bin-win-cpu-x64.zip',)
CUDA_FILES = ('llama-server.exe', 'ggml-cuda.dll', 'cublas64_12.dll',
              'cublasLt64_12.dll', 'cudart64_12.dll')
CPU_FILES = ('llama-server.exe', 'ggml.dll', 'ggml-base.dll')


class SetupError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def matches(path: Path, item: dict) -> bool:
    return (path.is_file() and
            (not item.get('bytes') or path.stat().st_size == item['bytes']) and
            sha256_file(path).lower() == item['sha256'].lower())


def download_verified(url: str, target: Path, item: dict) -> bool:
    """Return True when downloaded; keep a .part file after network failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if matches(target, item):
        print(f'[OK] Đã có {target.name}; SHA-256 khớp.')
        return False
    partial = target.with_name(target.name + '.part')
    start = partial.stat().st_size if partial.exists() else 0
    if start and item.get('bytes') and start > item['bytes']:
        partial.unlink()
        start = 0
    headers = {'User-Agent': 'web-mcq-offline-setup/1.0', 'Accept-Encoding': 'identity'}
    if start:
        headers['Range'] = f'bytes={start}-'
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=90)
    except urllib.error.HTTPError as error:
        if error.code != 416 or not matches(partial, item):
            raise SetupError(f'Tải {target.name} thất bại: HTTP {error.code}') from error
        os.replace(partial, target)
        return True
    except (OSError, urllib.error.URLError) as error:
        raise SetupError(f'Không kết nối được nguồn tải {target.name}: {error}') from error

    with response:
        status = response.status
        if start and status == 206:
            content_range = response.headers.get('Content-Range', '')
            if not content_range.startswith(f'bytes {start}-'):
                raise SetupError(f'Máy chủ trả về đoạn tải sai cho {target.name}.')
            mode = 'ab'
        elif status == 200:
            start, mode = 0, 'wb'
        else:
            raise SetupError(f'Máy chủ trả về HTTP {status} cho {target.name}.')
        expected = item.get('bytes')
        print(f'[Tải] {target.name}' + (f' (tiếp từ {start / 2**20:.0f} MiB)' if start else ''))
        written = start
        last_percent = -1
        try:
            with partial.open(mode) as output:
                while block := response.read(4 * 1024 * 1024):
                    output.write(block)
                    written += len(block)
                    if expected:
                        percent = written * 100 // expected
                        if percent >= last_percent + 10 or percent == 100:
                            print(f'  {min(percent, 100)}% ({written / 2**20:.0f} MiB)')
                            last_percent = percent
        except (OSError, http.client.HTTPException) as error:
            raise SetupError(f'Tải {target.name} bị ngắt; chạy lại để tiếp tục: {error}') from error
    if expected and partial.stat().st_size != expected:
        raise SetupError(f'{target.name} chưa tải đủ; chạy lại để tiếp tục.')
    if not matches(partial, item):
        partial.unlink(missing_ok=True)
        raise SetupError(f'SHA-256 của {target.name} không khớp; tệp tải dở đã bị bỏ.')
    os.replace(partial, target)
    print(f'[OK] Đã kiểm tra SHA-256: {target.name}')
    return True


def runtime_ready(directory: Path, backend: str, release: str) -> bool:
    required = CUDA_FILES if backend == 'cuda' else CPU_FILES
    if not all((directory / name).is_file() for name in required):
        return False
    try:
        result = subprocess.run([str(directory / 'llama-server.exe'), '--version'],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and f'build {release.removeprefix("b")}' in result.stdout + result.stderr


def extract_archives(archives: list[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.setup-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        for archive in archives:
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    if member.is_dir():
                        continue
                    name = member.filename
                    # The pinned Windows releases are flat archives. Reject a
                    # changed layout instead of extracting outside runtime/.
                    if (name in {'', '.', '..'} or '/' in name or '\\' in name or
                            ':' in name or Path(name).name != name):
                        raise SetupError(f'Đường dẫn không hợp lệ trong {archive.name}: {name}')
                    with package.open(member) as source, (stage / name).open('wb') as output:
                        shutil.copyfileobj(source, output, 4 * 1024 * 1024)
        destination.mkdir(parents=True, exist_ok=True)
        for source in stage.iterdir():
            os.replace(source, destination / source.name)


def set_backend(backend: str, root: Path) -> None:
    for relative in ('settings.json', 'fast_v2/settings.json'):
        path = root / relative
        data = json.loads(path.read_text(encoding='utf-8'))
        prefix = '../' if relative.startswith('fast_v2/') else ''
        data['server'] = f'{prefix}runtime/{backend}/llama-server.exe'
        data['device'] = 'CPU' if backend == 'cpu' else 'CUDA0'
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, path)


def install(root: Path, backend: str, check_only: bool = False, keep_archives: bool = False) -> None:
    manifest = json.loads((root / 'artifacts' / 'download-manifest.json').read_text(encoding='utf-8'))
    model = next(item for item in manifest['models'] if Path(item['file']).name == MODEL_NAME)
    release = manifest['llama_cpp']['release']
    archive_items = {item['file']: item for item in manifest['llama_cpp']['assets']}
    names = CUDA_ARCHIVES if backend == 'cuda' else CPU_ARCHIVES
    model_file = root / model['file']
    runtime_dir = root / 'runtime' / backend
    if check_only:
        if not matches(model_file, model):
            raise SetupError(f'Thiếu hoặc sai SHA-256 model: {model_file}')
        if not runtime_ready(runtime_dir, backend, release):
            raise SetupError(f'Thiếu hoặc sai phiên bản llama.cpp: {runtime_dir}')
        print(f'[OK] Model và llama.cpp {release} ({backend}) đã sẵn sàng.')
        return

    free = shutil.disk_usage(root).free
    needs_model = not matches(model_file, model)
    needs_runtime = not runtime_ready(runtime_dir, backend, release)
    minimum = ((5 if backend == 'cuda' else 3) * 2**30 if needs_model else
               (2 * 2**30 if backend == 'cuda' else 200 * 2**20) if needs_runtime else 0)
    if free < minimum:
        raise SetupError(f'Cần ít nhất {minimum / 2**30:.1f} GiB trống trước khi tải model và runtime.')
    model_url = (f"https://huggingface.co/{model['repository']}/resolve/"
                 f"{model['revision']}/{MODEL_NAME}?download=true")
    download_verified(model_url, model_file, model)

    if runtime_ready(runtime_dir, backend, release):
        print(f'[OK] Đã có llama.cpp {release} ({backend}).')
    else:
        archives = []
        for name in names:
            if name not in archive_items:
                raise SetupError(f'Manifest thiếu gói {name}.')
            item = archive_items[name]
            archive = root / 'runtime' / 'downloads' / name
            url = f'https://github.com/ggml-org/llama.cpp/releases/download/{release}/{name}'
            download_verified(url, archive, item)
            archives.append(archive)
        extract_archives(archives, runtime_dir)
        if not runtime_ready(runtime_dir, backend, release):
            raise SetupError(f'Đã giải nén nhưng llama-server {release} không chạy được; kiểm tra Windows/driver.')
        if not keep_archives:
            for archive in archives:
                archive.unlink(missing_ok=True)
    if backend == 'cuda':
        result = subprocess.run([str(runtime_dir / 'llama-server.exe'), '--list-devices'],
            capture_output=True, text=True, timeout=40,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or not re.search(r'CUDA0', result.stdout + result.stderr):
            raise SetupError('Không thấy CUDA0; thử cài lại với -Backend cpu hoặc cập nhật driver NVIDIA.')
    set_backend(backend, root)
    print(f'[OK] Cài đặt xong. Chế độ: {backend.upper()}. Từ giờ ứng dụng chạy offline.')


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('cuda', 'cpu'), required=True)
    parser.add_argument('--check', action='store_true', help='Chỉ kiểm tra, không tải và không sửa cài đặt')
    parser.add_argument('--keep-archives', action='store_true')
    args = parser.parse_args()
    try:
        install(ROOT, args.backend, args.check, args.keep_archives)
        return 0
    except (SetupError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f'[LỖI] {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
