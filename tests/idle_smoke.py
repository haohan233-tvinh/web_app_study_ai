"""Verify automatic idle sleep and reloading on the next local request."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipboard_solver import ExamSolver


if __name__ == '__main__':
    solver = ExamSolver()
    try:
        solver.model.start()
        print('Waiting for configured idle sleep...', flush=True)
        time.sleep(solver.settings['sleep_idle_seconds'] + 3)
        before = solver.model.log_path.read_text(encoding='utf-8', errors='replace')
        sleep_lines = [line for line in before.splitlines() if 'sleep' in line.lower()]
        start = time.perf_counter()
        raw = solver.model.chat([{'role':'user','content':'Return JSON {"ok":true}.'}],
            {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False})
        report = {'sleep_log_lines':sleep_lines, 'wake_response':raw,
                  'wake_seconds':round(time.perf_counter()-start,3)}
        (ROOT/'artifacts/idle-smoke.json').write_text(json.dumps(report, indent=2),encoding='utf-8')
        print(json.dumps(report, indent=2))
        assert sleep_lines, 'No server idle-sleep evidence'
        assert raw == {'ok':True}
    finally:
        solver.close()
