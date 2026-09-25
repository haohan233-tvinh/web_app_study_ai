"""The same frozen 16-image course subset used by the original OCR smoke test."""
import json
from pathlib import Path
import statistics
import time

from PIL import Image
from clipboard_solver import ExamSolver, ROOT


def main():
    base = ROOT.parent
    questions = json.loads((base / 'tests/course_benchmark.json').read_text(encoding='utf-8'))
    solver = ExamSolver()
    rows = []
    try:
        start = time.perf_counter()
        solver.warmup()
        load_seconds = round(time.perf_counter()-start, 3)
        for index in range(0, 64, 4):
            q = questions[index]
            path = base / 'artifacts/ocr' / f"{q['id']}.png"
            with Image.open(path) as image:
                start = time.perf_counter()
                result = solver.solve_image(image)
            row = {'id': q['id'], 'expected': q['answer'], 'result': result,
                   'correct': result.get('best_choice') == q['answer'],
                   'seconds': round(time.perf_counter()-start, 3)}
            rows.append(row)
            print(q['id'], row['correct'], row['seconds'], flush=True)
        with Image.open(base / 'tests/assets/html-lists.png') as image:
            original = solver.solve_image(image)
        report = {'scope': 'Same frozen 16 synthetic images as V1, plus original HTML lists screenshot',
                  'correct': sum(row['correct'] for row in rows), 'total': len(rows),
                  'median_seconds': statistics.median(row['seconds'] for row in rows),
                  'load_seconds': load_seconds, 'original_screenshot': original,
                  'reread_count': sum(row['result'].get('reread', False) for row in rows),
                  'rows': rows}
        target = ROOT / 'artifacts/ocr-benchmark.json'
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('OCR', report['correct'], '/', report['total'], flush=True)
    finally:
        solver.close()


if __name__ == '__main__':
    main()
