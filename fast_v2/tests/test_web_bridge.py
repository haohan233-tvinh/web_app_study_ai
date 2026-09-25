import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_bridge import WebBridge


class WebBridgeTests(unittest.TestCase):
    def test_loopback_token_region_generation_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = WebBridge(port=0, config_file=Path(directory) / 'bridge-config.json')
            base = f'http://127.0.0.1:{bridge.port}'
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base + '/state', timeout=2)
                self.assertEqual(denied.exception.code, 403)
                config = json.loads(bridge.config_file.read_text(encoding='utf-8'))
                self.assertEqual(config['token'], bridge.token)
                headers = {'X-Web-MCQ-Token': bridge.token}
                bridge.set_regions([[100, 100, 500, 300]])
                request = urllib.request.Request(base + '/state', headers=headers)
                state = json.load(urllib.request.urlopen(request, timeout=2))
                self.assertEqual(state['regions'], [[100, 100, 500, 300]])
                boxes = [{'text': f'answer {i}', 'left': 10, 'top': i * 25,
                          'right': 200, 'bottom': i * 25 + 18} for i in range(5)]
                body = json.dumps({'generation': state['generation'], 'regions': state['regions'],
                                   'boxes': boxes, 'tab_url': 'https://example.test/quiz'}).encode()
                post = urllib.request.Request(base + '/snapshot', data=body,
                    headers={**headers, 'Content-Type': 'application/json'}, method='POST')
                self.assertEqual(urllib.request.urlopen(post, timeout=2).status, 200)
                self.assertEqual(len(bridge.get_snapshot(state['regions'])['boxes']), 5)
                self.assertIsNone(bridge.get_snapshot(state['regions'], max_age=-1))
                clear = urllib.request.Request(base + '/clear', data=b'',
                    headers=headers, method='POST')
                self.assertEqual(urllib.request.urlopen(clear, timeout=2).status, 200)
                self.assertIsNone(bridge.get_snapshot(state['regions']))
                with self.assertRaises(urllib.error.HTTPError) as invalidated:
                    urllib.request.urlopen(post, timeout=2)
                self.assertEqual(invalidated.exception.code, 409)
                bridge.set_regions([[200, 100, 600, 300]])
                with self.assertRaises(urllib.error.HTTPError) as stale:
                    urllib.request.urlopen(post, timeout=2)
                self.assertEqual(stale.exception.code, 409)
                self.assertIsNone(bridge.get_snapshot(state['regions']))
                manual_regions = [[i * 40, 0, i * 40 + 35, 30] for i in range(5)]
                bridge.set_regions(manual_regions)
                manual_state = json.load(urllib.request.urlopen(request, timeout=2))
                manual_body = json.dumps({
                    'generation': manual_state['generation'], 'regions': manual_regions,
                    'boxes': [], 'sections': [[f'text for {i}'] for i in range(5)]
                }).encode()
                manual_post = urllib.request.Request(base + '/snapshot', data=manual_body,
                    headers={**headers, 'Content-Type': 'application/json'}, method='POST')
                self.assertEqual(urllib.request.urlopen(manual_post, timeout=2).status, 200)
                self.assertEqual(bridge.get_snapshot(manual_regions)['sections'][4], ['text for 4'])
            finally:
                bridge.close()


if __name__ == '__main__':
    unittest.main()
