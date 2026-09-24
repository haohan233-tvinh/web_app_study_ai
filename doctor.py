"""Read-only installation check. Never installs/downloads anything."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--hash', action='store_true')
    args = ap.parse_args()
    settings = json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
    result = {'python': sys.executable, 'settings': settings, 'packages': {}, 'files': {}}
    import psutil
    result['available_ram_mib'] = round(psutil.virtual_memory().available / (1024 * 1024))
    result['enough_ram_to_start'] = result['available_ram_mib'] >= settings.get('min_available_ram_mib',1536)
    for package in ['Pillow','rapidocr-onnxruntime','onnxruntime','numpy','PyMuPDF','beautifulsoup4']:
        try:
            result['packages'][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result['packages'][package] = 'MISSING'
    for relative in [settings['model'], settings['server'], settings['knowledge']]:
        path = ROOT / relative
        value = {'exists': path.is_file(), 'bytes': path.stat().st_size if path.is_file() else 0}
        if args.hash and path.is_file():
            with path.open('rb') as f:
                value['sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
        result['files'][relative] = value
    import rapidocr_onnxruntime
    onnx_dir = Path(rapidocr_onnxruntime.__file__).parent / 'models'
    result['ocr_models'] = {p.name: p.stat().st_size for p in onnx_dir.glob('*.onnx')}
    try:
        proc = subprocess.run([str(ROOT/settings['server']), '--list-devices'], capture_output=True,
                              text=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result['devices'] = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        result['devices'] = str(error)
    ready = (all(f['exists'] for f in result['files'].values()) and
             all(v != 'MISSING' for v in result['packages'].values()) and len(result['ocr_models']) >= 3)
    result['ready'] = ready
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ready else 1


if __name__ == '__main__':
    raise SystemExit(main())
