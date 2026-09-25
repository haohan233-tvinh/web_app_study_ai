"""Measure both screen-image-to-result and Enter-to-result on real OCR and model."""
import json
from pathlib import Path
import queue
import statistics
import time

from PIL import Image
from clipboard_solver import ExamSolver, ROOT
from prefetch import PrefetchEngine
from tray_app import image_signature, system_snapshot


def event_for(engine, sequence, timeout=65):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = engine.events.get(timeout=min(.5, deadline-time.monotonic()))
        except queue.Empty:
            continue
        if event.get('type') == 'result' and event['sequence'] == sequence:
            return event
    raise TimeoutError('No result for current image')


def main():
    base = ROOT.parent
    questions = json.loads((base / 'tests/course_benchmark.json').read_text(encoding='utf-8'))
    solver = ExamSolver()
    engine = PrefetchEngine(solver)
    rows = []
    try:
        for index in range(0, 64, 4):
            q = questions[index]
            path = base / 'artifacts/ocr' / f"{q['id']}.png"
            with Image.open(path) as source:
                image = source.copy()
            image_at = time.perf_counter()
            signature = image_signature(image)
            sequence = engine.submit(image, signature, image_at)
            prepared = engine.wait_prepared(sequence)
            if not prepared:
                raise TimeoutError('OCR did not finish before Enter')
            sequence = engine.submit(image, signature, image_at, solve=True,
                                     mode='multi' if q.get('multi', False) else 'auto')
            event = event_for(engine, sequence)
            result = event['result']
            row = {'id': q['id'], 'expected': q['answer'], 'result': result,
                   'correct': result.get('best_choice') == q['answer'],
                   'image_to_answer_seconds': event['image_to_answer_seconds'],
                   'enter_to_answer_seconds': event['enter_to_answer_seconds'],
                   'ocr_seconds': result.get('ocr_seconds'),
                   'inference_seconds': result.get('inference_seconds'),
                   'cooling_seconds': result.get('cooling_seconds'),
                   'reread': result.get('reread'), 'hardware': system_snapshot()}
            rows.append(row)
            print(q['id'], row['correct'], row['enter_to_answer_seconds'], flush=True)
        def median(field):
            return round(statistics.median(row[field] for row in rows), 3)
        def p95(field):
            return sorted(row[field] for row in rows)[int(.95*len(rows)+.9999)-1]
        report = {'scope': 'Real V2 OCR prefetch plus local model, 16 synthetic fixed images',
                  'total': len(rows), 'correct': sum(row['correct'] for row in rows),
                  'median_image_to_answer_seconds': median('image_to_answer_seconds'),
                  'median_enter_to_answer_seconds': median('enter_to_answer_seconds'),
                  'p95_image_to_answer_seconds': p95('image_to_answer_seconds'),
                  'p95_enter_to_answer_seconds': p95('enter_to_answer_seconds'),
                  'reread_count': sum(bool(row['reread']) for row in rows),
                  'model_load_seconds': engine.model_load_seconds, 'rows': rows}
        (ROOT / 'artifacts/prefetch-benchmark.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Prefetch', report['correct'], '/', report['total'],
              report['median_enter_to_answer_seconds'], flush=True)
    finally:
        engine.close()
        solver.close()


if __name__ == '__main__':
    main()
