"""Live loopback/auth/idle/cleanup checks. Does not send anything off the machine."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipboard_solver import ExamSolver


def main():
    solver = ExamSolver()
    solver.model.start()
    proc = psutil.Process(solver.model.process.pid)
    report = {'pid': proc.pid, 'url': solver.model.url, 'health': solver.model.request('/health')}
    try:
        report['idle_cpu_percent_over_3_seconds'] = proc.cpu_percent(interval=3)
        connections = proc.net_connections(kind='inet')
        report['connections'] = [{'local': list(c.laddr), 'remote': list(c.raddr), 'status': c.status} for c in connections]
        report['only_loopback_connections'] = all(
            (not c.raddr or c.raddr.ip in {'127.0.0.1','::1'}) and
            (not c.laddr or c.laddr.ip in {'127.0.0.1','::1'}) for c in connections)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            request = urllib.request.Request(solver.model.url + '/v1/chat/completions',
                data=b'{"messages":[{"role":"user","content":"hello"}]}',
                headers={'Content-Type':'application/json'})
            opener.open(request, timeout=5)
            report['unauthenticated_request_rejected'] = False
        except urllib.error.HTTPError as error:
            report['unauthenticated_request_rejected'] = error.code in {401,403}
    finally:
        pid = proc.pid
        solver.close()
    report['normal_close_terminates_model'] = not psutil.pid_exists(pid)
    code = (
        'from clipboard_solver import ExamSolver;import os;'
        's=ExamSolver();s.model.start();'
        'print(s.model.process.pid,flush=True);os._exit(0)')
    run = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=90)
    if run.returncode != 0:
        raise RuntimeError(run.stderr)
    child_pid = int(run.stdout.strip().splitlines()[-1])
    deadline = time.monotonic() + 5
    while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(.1)
    report['abrupt_parent_exit_terminates_model'] = not psutil.pid_exists(child_pid)
    (ROOT/'artifacts/runtime-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    assert report['only_loopback_connections']
    assert report['unauthenticated_request_rejected']
    assert report['normal_close_terminates_model']
    assert report['abrupt_parent_exit_terminates_model']


if __name__ == '__main__':
    main()
