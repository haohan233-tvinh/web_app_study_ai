import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from setup_assets import SetupError, download_verified, extract_archives, set_backend


class _Response(io.BytesIO):
    def __init__(self, data, status, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class SetupAssetsTests(unittest.TestCase):
    def test_download_resumes_and_checks_hash_before_publishing(self):
        data = b'web-mcq-test-content' * 200
        item = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'model.gguf'
            (Path(directory) / 'model.gguf.part').write_bytes(data[:100])
            response = _Response(data[100:], 206,
                                 {'Content-Range': f'bytes 100-{len(data)-1}/{len(data)}'})
            with patch('urllib.request.urlopen', return_value=response) as open_url:
                self.assertTrue(download_verified('https://example.invalid/model', target, item))
            self.assertEqual(open_url.call_args.args[0].headers['Range'], 'bytes=100-')
            self.assertEqual(target.read_bytes(), data)
            self.assertFalse(target.with_name(target.name + '.part').exists())

    def test_bad_hash_does_not_replace_existing_model(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'model.gguf'
            target.write_bytes(b'original')
            item = {'bytes': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
            with patch('urllib.request.urlopen', return_value=_Response(b'evil', 200)):
                with self.assertRaises(SetupError):
                    download_verified('https://example.invalid/model', target, item)
            self.assertEqual(target.read_bytes(), b'original')

    def test_archive_rejects_paths_outside_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'runtime.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('../escape.txt', 'bad')
            with self.assertRaises(SetupError):
                extract_archives([archive], root / 'runtime' / 'cuda')
            self.assertFalse((root / 'escape.txt').exists())

    def test_cpu_configuration_uses_cpu_runtime_in_both_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'fast_v2').mkdir()
            for path in (root / 'settings.json', root / 'fast_v2' / 'settings.json'):
                path.write_text(json.dumps({'server': 'old', 'device': 'CUDA0',
                                            'expected_options': 4}), encoding='utf-8')
            set_backend('cpu', root)
            one = json.loads((root / 'settings.json').read_text(encoding='utf-8'))
            two = json.loads((root / 'fast_v2' / 'settings.json').read_text(encoding='utf-8'))
            self.assertEqual(one['server'], 'runtime/cpu/llama-server.exe')
            self.assertEqual(two['server'], '../runtime/cpu/llama-server.exe')
            self.assertEqual((one['device'], two['device']), ('CPU', 'CPU'))
            self.assertEqual(one['expected_options'], 4)


if __name__ == '__main__':
    unittest.main()
