"""Evaluate exact answer sets (abstentions count as incorrect), speed, GPU and offline use."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
from clipboard_solver import ExamSolver, ROOT


def gpu():
    try:
        line = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,temperature.gpu,power.draw,utilization.gpu',
                                        '--format=csv,noheader,nounits'], text=True,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).splitlines()[0]
        values = [float(v.strip()) for v in line.split(',')]
        return dict(zip(['memory_mib', 'temperature_c', 'power_w', 'utilization_percent'], values))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return {}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', type=Path, default=ROOT / 'tests/course_benchmark.json')
    ap.add_argument('--output', type=Path, default=ROOT / 'artifacts/benchmark.json')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--model')
    ap.add_argument('--cpu', action='store_true')
    args = ap.parse_args()
    questions = json.loads(args.dataset.read_text(encoding='utf-8'))
    if args.limit:
        questions = questions[:args.limit]
    # Python traffic is denied except loopback. The child server uses only local GGUF.
    original_connect = socket.socket.connect
    def offline_connect(sock, address):
        if address[0] not in {'127.0.0.1', '::1'}:
            raise RuntimeError(f'External network blocked during benchmark: {address[0]}')
        return original_connect(sock, address)
    socket.socket.connect = offline_connect
    settings = json.loads((ROOT / 'settings.json').read_text(encoding='utf-8'))
    if args.model:
        settings['model'] = args.model
    baseline = gpu()
    solver = ExamSolver(use_gpu=not args.cpu, settings=settings)
    started = time.perf_counter()
    solver.model.start()
    load_seconds = time.perf_counter() - started
    loaded = gpu()
    rows, seconds, by_topic = [], [], defaultdict(lambda: [0, 0])
    args.output.parent.mkdir(exist_ok=True, parents=True)
    partial = args.output.with_suffix('.partial.json')
    try:
        for i, q in enumerate(questions, 1):
            t = time.perf_counter()
            result = solver.solve(q['question'], q['choices'], q.get('multi', False))
            elapsed = time.perf_counter() - t
            expected = set(q['answer'].replace(' ', '').split(','))
            predicted = set(result.get('best_choice', '').replace(' ', '').split(','))
            correct = expected == predicted
            seconds.append(elapsed)
            topic = q.get('topic', q.get('module', 'unknown'))
            by_topic[topic][0] += int(correct)
            by_topic[topic][1] += 1
            row = {'id': q.get('id', str(i)), 'question': q['question'], 'expected': q['answer'],
                   'result': result, 'correct': correct, 'seconds': round(elapsed, 3),
                   'model_output': solver.last_diagnostic.get('model_output'), 'gpu': gpu()}
            rows.append(row)
            partial.write_text(json.dumps({'status':'running', 'completed':len(rows),
                'expected_total':len(questions), 'rows':rows}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"{i}/{len(questions)} {'OK' if correct else 'FAIL'} {row['id']}: {result.get('best_choice', result.get('error'))} expected={q['answer']} {elapsed:.2f}s", flush=True)
    finally:
        model_log = str(solver.model.log_path)
        solver.close()
        socket.socket.connect = original_connect
    n, successes = len(rows), sum(r['correct'] for r in rows)
    proportion, z = successes / n, 1.96
    center = (proportion + z*z/(2*n)) / (1 + z*z/n)
    margin = z * math.sqrt(proportion*(1-proportion)/n + z*z/(4*n*n)) / (1+z*z/n)
    report = {'dataset': str(args.dataset), 'dataset_sha256': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              'solver_sha256': hashlib.sha256((ROOT/'clipboard_solver.py').read_bytes()).hexdigest(),
              'knowledge_sha256': hashlib.sha256((ROOT/settings['knowledge']).read_bytes()).hexdigest(),
              'scope': 'Author-created course regression set, not an independent real-exam accuracy estimate',
              'settings': settings, 'total': n, 'correct': successes, 'accuracy': proportion,
              'wilson_95_interval': [center-margin, center+margin],
              'load_seconds': round(load_seconds, 3), 'median_seconds': round(statistics.median(seconds), 3),
              'p95_seconds': round(sorted(seconds)[math.ceil(.95*n)-1], 3), 'by_topic': dict(by_topic),
              'gpu_baseline': baseline, 'gpu_after_load': loaded, 'model_log': model_log,
              'python_external_network_blocked': True, 'rows': rows}
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    partial.unlink(missing_ok=True)
    print(json.dumps({k: report[k] for k in ['total','correct','accuracy','median_seconds','p95_seconds','gpu_baseline','gpu_after_load']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
