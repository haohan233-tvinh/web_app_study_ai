"""End-to-end image tests with local OCR/model and actual Windows clipboard verification."""
import ctypes
from ctypes import wintypes
import io
import json
from pathlib import Path
import statistics
import sys
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from clipboard_solver import ExamSolver
from PIL import Image, ImageDraw, ImageFont


def render(q, number, font_size):
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', font_size)
    lines = textwrap.wrap(f'{number}. ' + q['question'], width=70)
    for label, value in q['choices'].items():
        lines += textwrap.wrap(label + ') ' + value, width=70, subsequent_indent='    ')
    image = Image.new('RGB', (1000, (font_size + 16) * len(lines) + 70), 'white')
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((28, 25 + i * (font_size + 16)), line, font=font, fill='#171717')
    return image


def set_clipboard_image(image):
    data = io.BytesIO()
    image.convert('RGB').save(data, format='BMP')
    payload = data.getvalue()[14:]
    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    handle = kernel.GlobalAlloc(0x42, len(payload))
    pointer = kernel.GlobalLock(handle)
    ctypes.memmove(pointer, payload, len(payload))
    kernel.GlobalUnlock(handle)
    assert user.OpenClipboard(None), 'Clipboard locked'
    try:
        assert user.EmptyClipboard()
        assert user.SetClipboardData(8, handle)
    finally:
        user.CloseClipboard()


def read_clipboard_text():
    user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    user.GetClipboardData.argtypes = [wintypes.UINT]
    user.GetClipboardData.restype = wintypes.HANDLE
    assert user.OpenClipboard(None)
    try:
        handle = user.GetClipboardData(13)
        pointer = kernel.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel.GlobalUnlock(handle)
    finally:
        user.CloseClipboard()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    questions = json.loads((ROOT / 'tests/course_benchmark.json').read_text(encoding='utf-8'))
    target = ROOT / 'artifacts/ocr'
    target.mkdir(exist_ok=True, parents=True)
    solver = ExamSolver()
    solver.warmup()
    results = []
    try:
        # Evenly spaced subset covers all eight subject chapters; fixed before results.
        for i in range(0, 64, 4):
            q = questions[i]
            image = render(q, i + 1, 19 if i % 8 == 0 else 23)
            path = target / f"{q['id']}.png"
            image.save(path)
            result = solver.solve_image(image)
            correct = result.get('best_choice') == q['answer']
            row = {'id': q['id'], 'expected': q['answer'], 'result': result, 'correct': correct,
                   'ocr_lines': solver.last_diagnostic.get('ocr_lines')}
            results.append(row)
            print(q['id'], correct, result, flush=True)
        # Original screenshot is kept separate from the synthetic course-score set.
        reference = ROOT / 'tests/assets/html-lists.png'
        if reference.exists():
            with Image.open(reference) as image:
                set_clipboard_image(image)
            captured = solver.grab_clipboard_image()
            assert captured is not None
            result = solver.solve_image(captured)
            assert 'best_choice' in result, result
            assert solver.copy_to_clipboard(result['best_choice'])
            copied = read_clipboard_text()
            assert copied == result['best_choice']
            clipboard = {'passed': True, 'result': result, 'read_back': copied,
                         'ocr_lines': solver.last_diagnostic['ocr_lines']}
        else:
            clipboard = {'passed': False, 'error': 'Original screenshot missing'}
        # Incomplete captures must produce an error rather than invent C.
        malformed = {'question': 'Which is an HTML tag?', 'choices': {'A':'<p>', 'B':'<x>', 'D':'<z>'}}
        error_result = solver.solve_image(render(malformed, 1, 22))
        assert 'error' in error_result, error_result
        report = {'scope': '16 synthetic images, fixed evenly spaced course subset; not real Moodle validation',
                  'correct': sum(r['correct'] for r in results), 'total': len(results),
                  'median_total_seconds': statistics.median(r['result'].get('total_seconds', 0) for r in results),
                  'clipboard_roundtrip': clipboard, 'missing_option_rejected': True, 'rows': results}
        (ROOT / 'artifacts/ocr-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('OCR', report['correct'], '/', report['total'], 'clipboard', clipboard['passed'])
    finally:
        solver.close()


if __name__ == '__main__':
    main()
