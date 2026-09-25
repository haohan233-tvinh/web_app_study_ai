"""Cold start, continuous use, 20-second idle and 65-second wake probe."""
import json
import time

from clipboard_solver import ExamSolver, ROOT
from tray_app import system_snapshot


def main():
    questions = json.loads((ROOT.parent / 'tests/course_benchmark.json').read_text(encoding='utf-8'))
    solver = ExamSolver()
    rows = []
    try:
        started = time.perf_counter()
        solver.model.start()
        load_seconds = round(time.perf_counter()-started, 3)
        for label, pause, q in zip(('first', 'consecutive', 'idle20', 'idle65'),
                                   (0, 0, 20, 65), questions[:4]):
            if pause:
                time.sleep(pause)
            started = time.perf_counter()
            result = solver.solve(q['question'], q['choices'], q.get('multi', False))
            row = {'case': label, 'idle_seconds': pause,
                   'seconds': round(time.perf_counter()-started, 3),
                   'correct': result.get('best_choice') == q['answer'],
                   'result': result, 'hardware': system_snapshot()}
            rows.append(row)
            print(label, row['seconds'], row['correct'], flush=True)
        report = {'model_load_seconds': load_seconds, 'rows': rows}
        (ROOT / 'artifacts/idle-benchmark.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        solver.close()


if __name__ == '__main__':
    main()
