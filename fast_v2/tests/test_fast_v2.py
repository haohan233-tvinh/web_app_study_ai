import os
from pathlib import Path
import queue
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PIL import Image
from clipboard_solver import ExamSolver, relevant_ocr_score
from debug_ui import CaptureBorder, DebugPanel, StatusDot, region_to_qrect
from prefetch import PrefetchEngine
from src.question_parser import parse_question
from src.layout import DomCapture, ManualCapture, group_auto
from src.ocr import OCR
from src.mouse_hotkeys import MouseHook, mouse_chord
from src.ordered_concepts import box_model_order
from src.question_parser import is_feedback_line
from tray_app import (DEFAULTS, KeyRecorder, Overlay, SettingsDialog, TrayApp,
                      bare_typing_key, migrate_typing_hotkeys, image_signature,
                      region_from_corners)


class FakeModel:
    def start(self):
        return None


class FakeSolver:
    def __init__(self):
        self.model = FakeModel()
        self.prepared = []
        self.solved = []

    def prepare_image(self, image):
        if image == 'old':
            time.sleep(.15)
        self.prepared.append(image)
        return {'value': image, 'ocr_seconds': .15, 'reread': False}

    def solve_prepared(self, prepared, mode):
        self.solved.append((prepared['value'], mode))
        return {'best_choice': 'B' if prepared['value'] == 'new' else 'A'}


class FastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_region_reuse_redraw_and_negative_monitor_coordinates(self):
        self.assertEqual(region_from_corners((200, 300), (-200, 50)), [-200, 50, 200, 300])
        with self.assertRaises(ValueError):
            region_from_corners((0, 0), (20, 20))

    def test_signature_ignores_identical_frames(self):
        image = Image.new('RGB', (800, 500), 'white')
        self.assertEqual(image_signature(image), image_signature(image.copy()))

    def test_dom_capture_uses_page_text_without_ocr(self):
        from PIL import ImageDraw
        image = Image.new('RGB', (600, 330), 'white')
        draw = ImageDraw.Draw(image)
        for top, bottom in ((50, 103), (108, 162), (167, 235), (240, 317)):
            draw.rectangle((12, top, 588, bottom), outline='#dbe5f2', width=1)
        def box(text, x, y):
            return {'text': text, 'score': 1.0, 'left': x, 'right': x+170,
                    'top': y, 'bottom': y+15, 'cy': y+7.5, 'height': 15}
        boxes = (box('17. Trong CSS Box Model, thứ tự nào đúng?', 16, 10),
                 box('Margin → Border → Padding → Content', 50, 70),
                 box('Padding → Border → Margin → Content', 50, 127),
                 box('Border → Margin → Padding → Content', 50, 180),
                 box('Content → Padding → Border → Margin', 50, 261))
        capture = DomCapture(image, boxes, 'https://example.test/quiz')
        solver = ExamSolver()
        try:
            prepared = solver.prepare_image(capture)
            self.assertEqual(prepared['capture_source'], 'DOM')
            self.assertEqual(prepared['ocr_seconds'], 0)
            self.assertEqual(prepared['structured'].options['A'],
                             'Margin → Border → Padding → Content')
            altered = DomCapture(image, boxes[:-1] + (box('changed answer', 50, 261),))
            self.assertNotEqual(image_signature(capture), image_signature(altered))
        finally:
            solver.close()

    def test_dom_manual_regions_keep_drawn_option_order(self):
        image = Image.new('RGB', (400, 250), 'white')
        sections = (('Trong CSS Box Model, thứ tự từ lớp ngoài vào lớp trong?',),
                    ('Margin → Border → Padding → Content',),
                    ('Padding → Border → Margin → Content',),
                    ('Border → Margin → Padding → Content',),
                    ('Content → Padding → Border → Margin',))
        regions = tuple((0, i*50, 400, i*50+50) for i in range(5))
        capture = DomCapture(image, (), 'https://example.test', sections, regions)
        solver = ExamSolver()
        try:
            prepared = solver.prepare_image(capture)
            self.assertEqual(prepared['capture_source'], 'DOM')
            self.assertEqual(prepared['layout_method'], 'dom_manual_regions')
            self.assertEqual(prepared['structured'].options['D'],
                             'Content → Padding → Border → Margin')
            self.assertEqual(prepared['ocr_seconds'], 0)
        finally:
            solver.close()

    def test_ocr_box_coordinates_map_back_to_original_capture(self):
        result = [([[42, 52], [142, 52], [142, 72], [42, 72]], 'example', .96)]
        _, boxes = OCR._rows(result, original_size=(200, 100),
                             prepared_size=(432, 232), padding=16)
        self.assertEqual((boxes[0]['left'], boxes[0]['top'],
                          boxes[0]['right'], boxes[0]['bottom']),
                         (13, 18, 63, 28))

    def test_manual_signature_includes_all_crops_and_regions(self):
        images = tuple(Image.new('RGB', (90, 50), color) for color in ('white', 'red', 'green'))
        a = ManualCapture(((0, 0, 90, 50), (0, 50, 90, 100), (0, 100, 90, 150)), images)
        b = ManualCapture(a.regions, (images[0], Image.new('RGB', (90, 50), 'blue'), images[2]))
        c = ManualCapture(((1, 0, 91, 50), *a.regions[1:]), images)
        self.assertNotEqual(image_signature(a), image_signature(b))
        self.assertNotEqual(image_signature(a), image_signature(c))

    def test_card_layout_ignores_missing_badge_and_wrapped_code(self):
        from PIL import ImageDraw
        image = Image.new('RGB', (600, 330), 'white')
        draw = ImageDraw.Draw(image)
        borders = [(50, 103), (108, 162), (167, 235), (240, 317)]
        for top, bottom in borders:
            draw.rectangle((12, top, 588, bottom), outline='#dbe5f2', width=1)
        def box(text, x, y, w=120):
            return {'text': text, 'score': .95, 'left': x, 'right': x+w,
                    'top': y, 'bottom': y+14, 'cy': y+7, 'height': 14}
        boxes = [box('Which snippet is valid?', 15, 10),
                 box('first answer', 50, 70), box('second answer', 50, 127),
                 box('long A) inside a code sample', 50, 180), box('continues on next line', 80, 204),
                 box('last answer', 50, 261)]
        layout = group_auto(image, boxes, 4)
        self.assertEqual(layout['method'], 'card_borders')
        self.assertFalse(layout['question'].errors)
        self.assertEqual(layout['question'].options['C'],
                         'long A) inside a code sample\ncontinues on next line')

    def test_unlabeled_line_layout_is_marked_weak(self):
        def box(text, x, y):
            return {'text': text, 'score': .95, 'left': x, 'right': x+180,
                    'top': y, 'bottom': y+14, 'cy': y+7, 'height': 14}
        boxes = [box('Which list is valid?', 10, 5), box('ordered list', 20, 60),
                 box('wrapped detail', 50, 78), box('unordered list', 20, 112),
                 box('definition list', 20, 164), box('fake list', 20, 216)]
        layout = group_auto(Image.new('RGB', (400, 270), 'white'), boxes, 4)
        self.assertTrue(layout['weak'])
        self.assertFalse(layout['question'].errors)
        self.assertEqual(layout['question'].options['A'], 'ordered list\nwrapped detail')

    def test_radio_markers_group_wrapped_answers(self):
        from PIL import ImageDraw
        image = Image.new('RGB', (500, 330), 'white')
        draw = ImageDraw.Draw(image)
        for cy in (80, 142, 204, 266):
            draw.ellipse((17, cy-11, 39, cy+11), fill='#e5e8ec')
        def box(text, x, y):
            return {'text': text, 'score': .95, 'left': x, 'right': x+180,
                    'top': y, 'bottom': y+14, 'cy': y+7, 'height': 14}
        boxes = [box('Which works?', 12, 10), box('First', 60, 74),
                 box('continues', 80, 97), box('Second', 60, 136),
                 box('Third', 60, 198), box('Fourth', 60, 260)]
        layout = group_auto(image, boxes, 4)
        self.assertEqual(layout['method'], 'radio_markers')
        self.assertEqual(layout['question'].options['A'], 'First\ncontinues')

    def test_unlabeled_wrapped_lines_with_same_indent_use_spacing(self):
        def box(text, y):
            return {'text': text, 'score': .95, 'left': 30, 'right': 230,
                    'top': y, 'bottom': y+14, 'cy': y+7, 'height': 14}
        boxes = [box('Choose the valid statement?', 10),
                 box('first line', 62), box('more first', 80),
                 box('second line', 120), box('more second', 138),
                 box('third line', 178), box('more third', 196),
                 box('fourth line', 236), box('more fourth', 254)]
        layout = group_auto(Image.new('RGB', (400, 300), 'white'), boxes, 4)
        self.assertTrue(layout['weak'])
        self.assertEqual(layout['question'].options['D'], 'fourth line\nmore fourth')

    def test_box_model_arrow_order_and_result_panel(self):
        def box(text, x, y):
            return {'text': text, 'score': .95, 'left': x, 'right': x+260,
                    'top': y, 'bottom': y+16, 'cy': y+8, 'height': 16}
        boxes = [box('CSS', 25, 5),
                 box('17. Trong CSS Box Model, thứ tự từ LỚP NGOÀI CÙNG vào LỚP TRONG CÙNG?', 28, 52),
                 box('A Margin → Border → Padding → Content', 48, 110),
                 box('B Padding → Border → Margin → Content', 48, 172),
                 box('C Border → Margin → Padding → Content', 48, 234),
                 box('D Content → Padding → Border → Margin', 48, 296),
                 box('CHƯA ĐÚNG! Đáp án chính xác là A', 45, 365),
                 box('Từ ngoài vào trong: Margin → Border → Padding → Content', 45, 390)]
        layout = group_auto(Image.new('RGB', (900, 440), 'white'), boxes, 4)
        question = layout['question']
        self.assertFalse(question.errors)
        self.assertTrue(question.text.startswith('Trong CSS Box Model'))
        self.assertEqual(question.options['A'], 'Margin → Border → Padding → Content')
        self.assertEqual(question.options['D'], 'Content → Padding → Border → Margin')
        self.assertEqual(box_model_order(question.text, question.options), 'A')
        self.assertTrue(is_feedback_line('❌ CHƯA ĐÚNG! Đáp án chính xác là A'))

    def test_box_model_direction_guardrails(self):
        options = {'A': 'Margin -> Border -> Padding -> Content',
                   'B': 'Padding -> Border -> Margin -> Content',
                   'C': 'Border -> Margin -> Padding -> Content',
                   'D': 'Content -> Padding -> Border -> Margin'}
        self.assertEqual(box_model_order('Trong CSS Box Model, từ lớp ngoài vào lớp trong?', options), 'A')
        self.assertEqual(box_model_order('CSS Box Model: from inner layer to outer layer?', options), 'D')
        self.assertIsNone(box_model_order('CSS Box Model có mấy lớp?', options))
        self.assertIsNone(box_model_order('CSS Box Model: thứ tự nào KHÔNG đúng từ ngoài vào trong?', options))
        self.assertIsNone(box_model_order('CSS Box Model: từ ngoài vào trong?', {**options, 'D': 'Content'}))

    def test_ocr_confidence_ignores_low_score_topic_badge(self):
        boxes = [{'text': 'CSS', 'score': .61},
                 {'text': '17. Trong CSS Box Model?', 'score': .93},
                 {'text': 'Margin → Border → Padding → Content', 'score': .97},
                 {'text': 'X CHUA DUNG! Dap an chinh xac la A', 'score': .4}]
        self.assertEqual(relevant_ocr_score(boxes), .93)

    def test_vietnamese_ocr_keeps_number_html_and_arrow_chain(self):
        original = '16. De ap dung cung mot mau cht xanh cho ca <hl>, <h2> va <p>, cu phap gom nhom nao dung?'
        recognized = '1ó. Để áp dụng cùng một màu chữ xanh cho cả <h]>, <h2> và <p>, cú pháp gom nhóm nào đúng?'
        corrected = OCR._safe_vietnamese(original, recognized)
        self.assertTrue(corrected.startswith('16. Để áp dụng cùng một màu chữ xanh'))
        self.assertIn('<hl>, <h2> và <p>', corrected)
        self.assertFalse(OCR._needs_vietnamese('Margin → Border → Padding → Content'))
        self.assertIsNone(OCR._safe_vietnamese(original, 'Đáp án hoàn toàn khác'))

    def test_secondary_ocr_repairs_only_damaged_css_brace(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'eng.traineddata').write_bytes(b'test')
            engine = OCR.__new__(OCR)
            engine.vietnamese_cmd = 'mock-tesseract'
            engine.vietnamese_data = data
            engine.english_data = data
            engine.threads = 2
            boxes = [
                {'text': 'Trong CSS Box Model, thu tu tu lop ngoai vao lop trong?',
                 'left': 0, 'top': 10, 'right': 400, 'bottom': 30, 'cy': 20, 'height': 20},
                {'text': 'Margin → Border → Padding → Content',
                 'left': 0, 'top': 60, 'right': 400, 'bottom': 80, 'cy': 70, 'height': 20},
                {'text': 'h1, h2, p f color: blue; }',
                 'left': 0, 'top': 110, 'right': 400, 'bottom': 130, 'cy': 120, 'height': 20},
            ]
            answers = {'vie': 'Trong CSS Box Model, thứ tự từ lớp ngoài vào lớp trong?',
                       'eng': '| h1, h2, p { color: blue; }'}
            with patch.object(engine, '_recognize_crop', side_effect=lambda _, __, lang, ___: answers[lang]) as call:
                lines, refined, elapsed = engine.refine_vietnamese(
                    Image.new('RGB', (500, 150), 'white'), [], boxes)
            self.assertEqual(call.call_count, 2)
            self.assertIn('thứ tự từ lớp ngoài', lines[0])
            self.assertEqual(lines[1], 'Margin → Border → Padding → Content')
            self.assertEqual(lines[2], 'h1, h2, p { color: blue; }')
            self.assertEqual(boxes[2]['text'], 'h1, h2, p f color: blue; }')
            self.assertGreaterEqual(elapsed, 0)

    def test_key_recorder_captures_chord(self):
        recorder = KeyRecorder('f8')
        recorder.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R,
                                       Qt.KeyboardModifier.ControlModifier |
                                       Qt.KeyboardModifier.AltModifier))
        self.assertEqual(recorder.text(), 'ctrl+alt+r')
        recorder._record_mouse('mouse_x2')
        self.assertEqual(recorder.text(), 'mouse_x2')

    def test_typing_keys_cannot_be_global_hotkeys(self):
        self.assertTrue(bare_typing_key('2'))
        self.assertTrue(bare_typing_key('grave'))
        self.assertFalse(bare_typing_key('ctrl+alt+2'))
        settings = {**DEFAULTS, 'show_key': '2', 'corner_key': 'grave'}
        self.assertTrue(migrate_typing_hotkeys(settings))
        self.assertEqual(settings['show_key'], 'f7')
        self.assertEqual(settings['corner_key'], 'ctrl+alt+grave')
        dialog = SettingsDialog(DEFAULTS)
        dialog.show_key.setText('2')
        with self.assertRaisesRegex(ValueError, 'chặn việc gõ'):
            dialog.values()

    def test_mouse_chords_and_hold_release(self):
        self.assertEqual(mouse_chord('ctrl+mouse_x1'), (frozenset({'ctrl'}), 'mouse_x1'))
        self.assertIsNone(mouse_chord('mouse_x3'))
        seen = []
        hook = MouseHook(lambda button, pressed, mods: seen.append((button, pressed)) or pressed)
        self.assertTrue(hook.dispatch('mouse_x2', True, frozenset()))
        self.assertTrue(hook.dispatch('mouse_x2', False, frozenset()))
        self.assertEqual(seen, [('mouse_x2', True), ('mouse_x2', False)])

    def test_code_reread_restores_braces_index_and_indent(self):
        from PIL import ImageDraw, ImageFont
        if not Path(r'C:\Windows\Fonts\consola.ttf').is_file():
            self.skipTest('Consolas is unavailable')
        image = Image.new('RGB', (650, 330), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 22)
        source = ['Question: what is returned?', 'const names = ["A", "B"];',
                  'function pick(value) {', '    if (value === "A") {',
                  '        return names[0];', '    }', '    return null;', '}',
                  'Choose one answer.']
        for index, line in enumerate(source):
            draw.text((15, 8 + index * 34), line, font=font, fill='black')
        reader = OCR()
        if not reader.tesseract_cmd:
            self.skipTest('Tesseract is unavailable')
        old, boxes = reader.read(image)
        fixed, _, seconds, improved = reader.refine_code(image, old, boxes)
        self.assertTrue(improved)
        self.assertIn('    if (value === "A") {', fixed)
        self.assertIn('        return names[0];', fixed)
        self.assertIn('}', fixed)
        self.assertGreater(seconds, 0)
        self.assertTrue(any('Question:' in line for line in fixed))
        self.assertTrue(any('Choose one' in line for line in fixed))
        html = Image.new('RGB', (650, 220), 'white')
        draw = ImageDraw.Draw(html)
        for index, line in enumerate(('<div class="card">', '    <h1>Hello</h1>',
                                      '    <p>Web</p>', '</div>')):
            draw.text((15, 15 + index * 34), line, font=font, fill='black')
        html_lines, html_boxes = reader.read(html)
        html_fixed, _, _, html_improved = reader.refine_code(html, html_lines, html_boxes)
        self.assertTrue(html_improved)
        self.assertTrue(any(line.lstrip() == '<h1>Hello</h1>' and line != line.lstrip()
                            for line in html_fixed))
        crops = [image]
        for label in ('First answer', 'Second answer', 'Third answer', 'Fourth answer'):
            option = Image.new('RGB', (300, 80), 'white')
            ImageDraw.Draw(option).text((15, 15), label, font=font, fill='black')
            crops.append(option)
        solver = ExamSolver()
        try:
            prepared = solver.prepare_image(ManualCapture(
                tuple((0, 0, crop.width, crop.height) for crop in crops),
                tuple(crops)))
            self.assertTrue(prepared['code_reread'])
            self.assertIn('        return names[0];', prepared['structured'].text)
            self.assertEqual(prepared['structured'].errors, [])
        finally:
            solver.close()

    def test_auto_region_rereads_code_without_losing_answer_cards(self):
        from PIL import ImageDraw, ImageFont
        if not Path(r'C:\Windows\Fonts\consola.ttf').is_file():
            self.skipTest('Consolas is unavailable')
        image = Image.new('RGB', (850, 670), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf', 22)
        question = ('17. What does this code return?', 'const names = ["A", "B"];',
                    'function pick(value) {', '    if (value === "A") {',
                    '        return names[0];', '    }', '    return null;', '}')
        for index, line in enumerate(question):
            draw.text((25, 14 + index * 35), line, font=font, fill='black')
        for index, line in enumerate(('A. A', 'B. B', 'C. null', 'D. undefined')):
            top = 310 + index * 85
            draw.rectangle((20, top, 820, top + 70), outline=(208, 221, 245), width=2)
            draw.text((55, top + 20), line, font=font, fill='black')
        solver = ExamSolver()
        try:
            if not solver._ocr().tesseract_cmd:
                self.skipTest('Tesseract is unavailable')
            prepared = solver.prepare_image(image)
            self.assertTrue(prepared['code_reread'])
            self.assertEqual(prepared['layout_method'], 'card_borders')
            self.assertIn('        return names[0];', prepared['structured'].text)
            self.assertEqual(set(prepared['structured'].options), {'A', 'B', 'C', 'D'})
            for letter, value in (('A', 'A'), ('B', 'B'), ('C', 'null'),
                                  ('D', 'undefined')):
                self.assertTrue(prepared['structured'].options[letter].endswith(value))
        finally:
            solver.close()

    def test_assigned_side_button_never_navigates_browser(self):
        emitted = []
        signal = SimpleNamespace(emit=lambda *args: emitted.append(args))
        fake = SimpleNamespace(mouse_bindings={'ctrl+mouse_x2': ('action', signal)},
                               mouse_held={})
        fake._mouse_event = TrayApp._mouse_event.__get__(fake)
        fake._report_mouse = lambda *args: None
        hook = MouseHook(fake._mouse_event)
        self.assertTrue(hook.dispatch('mouse_x2', True, frozenset()))
        self.assertTrue(hook.dispatch('mouse_x2', False, frozenset()))
        self.assertEqual(emitted, [])
        self.assertTrue(hook.dispatch('mouse_x2', True, frozenset({'ctrl'})))
        self.assertEqual(emitted, [()])

    def test_bare_badge_labels_need_complete_ordered_run(self):
        question = '28. Tên biến nào KHÔNG hợp lệ trong JavaScript?'
        lines = [question, 'A $price', 'B _total', 'c 2students', 'D userName']
        parsed = parse_question(lines)
        self.assertFalse(parsed.errors)
        self.assertEqual(parsed.options, {'A': '$price', 'B': '_total',
                                          'C': '2students', 'D': 'userName'})
        missing = parse_question([question, 'A $price', 'B _total',
                                  'c 2students', 'userName'])
        self.assertTrue(missing.errors)
        self.assertNotIn('D', missing.options)
        mixed = parse_question([question, 'A) $price', 'B _total',
                                'c) 2students', 'D userName'])
        self.assertFalse(mixed.errors)
        self.assertEqual(mixed.options['C'], '2students')

    def test_badge_screenshot_recovers_all_options(self):
        path = Path(__file__).parent / 'assets' / 'badge-labels-identifier.png'
        solver = ExamSolver()
        try:
            with Image.open(path) as image:
                prepared = solver.prepare_image(image)
            parsed = parse_question(prepared['lines'])
            self.assertFalse(parsed.errors, prepared['lines'])
            self.assertEqual(parsed.options, {'A': '$price', 'B': '_total',
                                              'C': '2students', 'D': 'userName'})
            self.assertIn('KHÔNG HỢP LỆ', parsed.text)
        finally:
            solver.close()

    def test_badge_manual_regions_recover_without_labels(self):
        path = Path(__file__).parent / 'assets' / 'badge-labels-identifier.png'
        regions = ((0, 0, 840, 42), (15, 50, 827, 102), (15, 112, 827, 164),
                   (15, 174, 827, 226), (15, 236, 827, 288))
        solver = ExamSolver()
        try:
            with Image.open(path) as image:
                capture = ManualCapture(regions, tuple(image.crop(region) for region in regions))
                prepared = solver.prepare_image(capture)
            self.assertEqual(prepared['structured'].options,
                             {'A': '$price', 'B': '_total', 'C': '2students', 'D': 'userName'})
            self.assertEqual(len(prepared['section_ocr_seconds']), 5)
            self.assertFalse(prepared['structured'].errors)
        finally:
            solver.close()

    def test_manual_two_column_order_and_missing_option(self):
        class OCR:
            def read(self, image):
                lines = image.info['lines']
                return lines, ([{'score': .99, 'text': lines[0]}] if lines else [])

            def read_quality(self, image, enhanced=True):
                return self.read(image)

            def refine_vietnamese(self, image, lines, boxes):
                return lines, boxes, 0.0

            def refine_code(self, image, lines, boxes):
                return lines, boxes, 0.0, False

        solver = ExamSolver()
        solver.ocr = OCR()
        try:
            sections = [['Which code works?'], ['const x = 1;', 'A) is literal content'],
                        ['return x;'], ['let y = 2;'], ['bad syntax']]
            crops = []
            for lines in sections:
                image = Image.new('RGB', (200, 80), 'white')
                image.info['lines'] = lines
                crops.append(image)
            # Two-column positions deliberately differ from letter order.
            regions = ((0, 0, 200, 80), (500, 80, 700, 160),
                       (0, 80, 200, 160), (500, 170, 700, 250), (0, 170, 200, 250))
            prepared = solver.prepare_image(ManualCapture(regions, tuple(crops)))
            self.assertEqual(prepared['structured'].options['A'],
                             'const x = 1;\nA) is literal content')
            self.assertEqual(prepared['structured'].options['B'], 'return x;')
            crops[3].info['lines'] = []
            missing = solver.prepare_image(ManualCapture(regions, tuple(crops)))
            self.assertTrue(missing['structured'].errors)
        finally:
            solver.close()

    def test_visible_capture_border_and_preview(self):
        region = [601, -582, 1338, -392]
        rect = region_to_qrect(region)
        self.assertEqual((rect.width(), rect.height()), (737, 190))
        border = CaptureBorder()
        panel = DebugPanel()
        dot = StatusDot()
        try:
            border.set_region(region)
            border.configure('#ff0000', .4)
            panel.show_region(region)
            panel.show_image(Image.new('RGB', (737, 190), 'white'))
            panel.set_stage('OCR xong')
            dot.set_state('ocr', region)
            self.assertTrue(border.isVisible())
            self.assertEqual(border.color.name(), '#ff0000')
            self.assertEqual(dot.state, 'ocr')
            self.assertEqual((dot.width(), dot.height()), (5, 5))
            self.assertIn('737 × 190', panel.region.text())
            self.assertIsNotNone(panel.preview.pixmap())
            self.assertIn('OCR xong', panel.history.toPlainText())
        finally:
            border.hide()
            panel.hide()
            dot.hide()

    def test_capture_keeps_nonoverlapping_status_square_visible(self):
        dot = StatusDot()
        dot.set_state('ready', [100, 100, 300, 200])
        dot.show()
        fake = SimpleNamespace(settings={**DEFAULTS, 'region': [100, 100, 300, 200]},
            overlay=Overlay(.4), debug_panel=DebugPanel(), status_dot=dot,
            redraw_active=False,
            capture_border=CaptureBorder(), extra_borders=[],
            active_regions=lambda: [[100, 100, 300, 200]],
            update_border_visibility=lambda: None,
            update_answer_visibility=lambda: None)
        def grab(**kwargs):
            self.assertTrue(dot.isVisible())
            self.assertEqual(kwargs['bbox'], (100, 100, 300, 200))
            return Image.new('RGB', (200, 100), 'white')
        with patch('PIL.ImageGrab.grab', side_effect=grab):
            result = TrayApp.capture(fake)
        self.assertEqual(result.size, (200, 100))
        self.assertTrue(dot.isVisible())
        dot.hide()

    def test_capture_prefers_fresh_dom_only_with_browser_foreground(self):
        region = [100, 100, 500, 300]
        bridge = MagicMock()
        bridge.get_snapshot.return_value = {'boxes': [
            {'text': f'line {i}', 'score': 1.0, 'left': 10, 'top': i*20,
             'right': 200, 'bottom': i*20+15, 'cy': i*20+7.5, 'height': 15}
            for i in range(5)], 'tab_url': 'https://example.test/quiz'}
        fake = SimpleNamespace(settings={**DEFAULTS, 'region': region},
            overlay=Overlay(.4), debug_panel=DebugPanel(), status_dot=StatusDot(),
            redraw_active=False, capture_border=CaptureBorder(), extra_borders=[],
            active_regions=lambda: [region], update_border_visibility=lambda: None,
            update_answer_visibility=lambda: None, web_bridge=bridge)
        with (patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (400, 200), 'white')),
              patch('tray_app.foreground_browser', return_value=True)):
            capture = TrayApp.capture(fake)
        self.assertIsInstance(capture, DomCapture)
        bridge.set_regions.assert_called_with([region])
        with (patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (400, 200), 'white')),
              patch('tray_app.foreground_browser', return_value=False)):
            fallback = TrayApp.capture(fake)
        self.assertIsInstance(fallback, Image.Image)

    def test_capture_hides_overlapping_dot_only_when_affinity_unavailable(self):
        dot = StatusDot()
        dot.set_state('ready', [100, 100, 300, 200])
        dot.show()
        dot.move(150, 150)
        dot.capture_excluded = False
        fake = SimpleNamespace(settings={**DEFAULTS, 'region': [100, 100, 300, 200]},
            overlay=Overlay(.4), debug_panel=DebugPanel(), status_dot=dot,
            redraw_active=False, capture_border=CaptureBorder(), extra_borders=[],
            active_regions=lambda: [[100, 100, 300, 200]],
            update_border_visibility=lambda: None,
            update_answer_visibility=lambda: None)
        with patch('PIL.ImageGrab.grab', side_effect=lambda **_: self.assertFalse(dot.isVisible())
                   or Image.new('RGB', (200, 100), 'white')):
            TrayApp.capture(fake)
        self.assertTrue(dot.isVisible())
        dot.capture_excluded = True
        with patch('PIL.ImageGrab.grab', side_effect=lambda **_: self.assertTrue(dot.isVisible())
                   or Image.new('RGB', (200, 100), 'white')):
            TrayApp.capture(fake)
        dot.hide()

    def test_visible_panel_stays_shown_during_repeated_capture(self):
        panel = DebugPanel()
        panel.setGeometry(120, 120, 450, 640)
        panel.show()
        panel.capture_excluded = True
        border = CaptureBorder()
        border.set_region([100, 100, 700, 700])
        border.capture_excluded = True
        fake = SimpleNamespace(settings={**DEFAULTS, 'region': [100, 100, 700, 700]},
            overlay=Overlay(.4), debug_panel=panel, status_dot=StatusDot(),
            redraw_active=False, capture_border=border, extra_borders=[],
            active_regions=lambda: [[100, 100, 700, 700]],
            update_border_visibility=lambda: None,
            update_answer_visibility=lambda: None)
        try:
            with (patch.object(panel, 'hide', wraps=panel.hide) as hide_panel,
                  patch.object(border, 'hide', wraps=border.hide) as hide_border,
                  patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (600, 600), 'white'))):
                for _ in range(3):
                    TrayApp.capture(fake)
                    self.assertTrue(panel.isVisible())
                hide_panel.assert_not_called()
                hide_border.assert_not_called()
        finally:
            panel.hide()
            border.hide()

    def test_manual_capture_uses_one_union_screenshot_and_crop_order(self):
        regions = [[100, 100, 190, 160], [310, 100, 400, 160]]
        canvas = Image.new('RGB', (300, 60), 'white')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, 0, 89, 59), fill='red')
        draw.rectangle((210, 0, 299, 59), fill='blue')
        fake = SimpleNamespace(settings={**DEFAULTS, 'reading_mode': 'manual'},
            overlay=Overlay(.4), debug_panel=DebugPanel(), status_dot=StatusDot(),
            redraw_active=False, capture_border=CaptureBorder(), extra_borders=[],
            active_regions=lambda: regions, update_border_visibility=lambda: None,
            update_answer_visibility=lambda: None)
        with patch('PIL.ImageGrab.grab', return_value=canvas) as grab:
            capture = TrayApp.capture(fake)
        grab.assert_called_once_with(bbox=(100, 100, 400, 160), all_screens=True)
        self.assertEqual(len(capture.crops), 2)
        self.assertEqual(capture.crops[0].getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(capture.crops[1].getpixel((0, 0)), (0, 0, 255))

    def test_clipboard_lock_returns_failure_without_clearing_clipboard(self):
        fake_user = MagicMock()
        fake_user.OpenClipboard.return_value = 0
        with (patch('clipboard_solver.ctypes.windll.user32', fake_user),
              patch('clipboard_solver.time.sleep')):
            self.assertFalse(ExamSolver.copy_to_clipboard('A'))
        self.assertEqual(fake_user.OpenClipboard.call_count, 8)
        fake_user.EmptyClipboard.assert_not_called()

    def test_new_image_replaces_stale_ocr(self):
        fake = FakeSolver()
        engine = PrefetchEngine(fake)
        try:
            engine.submit('old', b'old')
            time.sleep(.025)
            engine.submit('new', b'new', solve=True, mode='multi')
            deadline = time.monotonic() + 2
            result = None
            seen = []
            while time.monotonic() < deadline:
                try:
                    event = engine.events.get(timeout=.05)
                except queue.Empty:
                    continue
                seen.append(event['type'])
                if event['type'] == 'result':
                    result = event
                    break
            self.assertIsNotNone(result)
            self.assertEqual(result['result']['best_choice'], 'B')
            self.assertEqual(fake.solved, [('new', 'multi')])
            self.assertGreaterEqual(result['enter_to_answer_seconds'], 0)
            self.assertIn('ocr_started', seen)
            self.assertIn('ocr_ready', seen)
            self.assertIn('solve_started', seen)
        finally:
            engine.close()

    def test_invalidated_result_is_not_emitted(self):
        fake = FakeSolver()
        engine = PrefetchEngine(fake)
        try:
            engine.submit('old', b'old', solve=True)
            engine.invalidate()
            time.sleep(.25)
            events = []
            while not engine.events.empty():
                events.append(engine.events.get_nowait())
            self.assertFalse(any(event['type'] == 'result' for event in events))
        finally:
            engine.close()

    def test_hotkey_conflicts_and_overlay_visibility(self):
        settings = {**DEFAULTS, 'startup': False}
        dialog = SettingsDialog(settings)
        self.assertEqual(dialog.values()['solve_key'], 'ctrl+enter')
        dialog.answer_mode.setCurrentIndex(dialog.answer_mode.findData('always'))
        dialog.border_mode.setCurrentIndex(dialog.border_mode.findData('hold'))
        dialog.answer_color.setText('#112233')
        dialog.border_color.setText('#445566')
        self.assertEqual(dialog.values()['answer_mode'], 'always')
        self.assertEqual(dialog.values()['border_mode'], 'hold')
        self.assertEqual(dialog.values()['answer_color'], '#112233')
        dialog.answer_color.setText('not-a-color')
        with self.assertRaises(ValueError):
            dialog.values()
        dialog.answer_color.setText('#112233')
        dialog.border_key.setText('backslash')
        with self.assertRaises(ValueError):
            dialog.values()
        dialog.border_key.setText('f8')
        dialog.solve.setText('grave')
        with self.assertRaises(ValueError):
            dialog.values()
        dialog.solve.setText('ctrl+grave')
        self.assertEqual(dialog.values()['solve_key'], 'ctrl+grave')
        dialog.corner.setText('mouse_x2')
        dialog.solve.setText('ctrl+tab')
        dialog.redraw_key.setText('mouse_x1')
        dialog.toggle_reading_key.setText('ctrl+q')
        dialog.quit_key.setText('ctrl+alt+q')
        self.assertEqual(dialog.values()['toggle_reading_key'], 'ctrl+q')
        self.assertEqual(dialog.values()['quit_key'], 'ctrl+alt+q')
        dialog.corner.setText('ctrl+alt+grave')
        dialog.redraw_key.setText('ctrl+alt+r')
        dialog.toggle_reading_key.setText('ctrl+alt+m')
        dialog.solve.setText('mouse_x1')
        self.assertEqual(dialog.values()['solve_key'], 'mouse_x1')
        dialog.solve.setText('mouse_left')
        with self.assertRaises(ValueError):
            dialog.values()
        dialog.solve.setText('ctrl+mouse_left')
        self.assertEqual(dialog.values()['solve_key'], 'ctrl+mouse_left')
        dialog.restart_key.setText('mouse_x2')
        with self.assertRaises(ValueError):
            dialog.values()
        overlay = Overlay(.42)
        overlay.answer = 'A, B'
        overlay.show_answer()
        self.assertTrue(overlay.isVisible())
        overlay.hide()
        self.assertFalse(overlay.isVisible())

    def test_global_hotkeys_are_suppressed(self):
        emitter = SimpleNamespace(emit=lambda *args: None)
        fake = SimpleNamespace(settings={**DEFAULTS}, hooks=[], redraw_active=False,
                               mouse_hook=None, mouse_bindings={}, mouse_held={},
                               signals=SimpleNamespace(corner=emitter, solve=emitter, hold=emitter,
                                   redraw=emitter, toggle_reading=emitter,
                                   settings=emitter, quit=emitter, border_hold=emitter),
                               unbind_keys=lambda: None)
        fake._bind_action = TrayApp._bind_action.__get__(fake)
        fake._bind_hold = TrayApp._bind_hold.__get__(fake)
        with (patch('keyboard.add_hotkey', return_value='hotkey') as add,
              patch('keyboard.on_press_key', return_value='press') as press,
              patch('keyboard.on_release_key', return_value='release') as release):
            TrayApp.bind_keys(fake)
        self.assertEqual(add.call_count, 6)
        self.assertTrue(all(call.kwargs['suppress'] for call in add.call_args_list))
        self.assertTrue(press.call_args.kwargs['suppress'])
        self.assertTrue(release.call_args.kwargs['suppress'])
        border_only = SimpleNamespace(settings={**fake.settings, 'answer_mode': 'always',
                                       'border_mode': 'hold', 'border_key': 'f8'}, hooks=[],
                                       mouse_hook=None, mouse_bindings={}, mouse_held={},
                                       redraw_active=False,
                                       signals=fake.signals, unbind_keys=lambda: None)
        border_only._bind_action = TrayApp._bind_action.__get__(border_only)
        border_only._bind_hold = TrayApp._bind_hold.__get__(border_only)
        with (patch('keyboard.add_hotkey', return_value='hotkey') as add,
              patch('keyboard.on_press_key', return_value='press') as press,
              patch('keyboard.on_release_key', return_value='release') as release):
            TrayApp.bind_keys(border_only)
        self.assertEqual(add.call_count, 6)
        self.assertEqual(press.call_args.args[0], 'f8')
        self.assertEqual(release.call_args.args[0], 'f8')

    def test_tray_flow_keeps_old_answer_until_new_result(self):
        class Solver:
            def __init__(self):
                self.settings = {'expected_options': 4}
                self.copied = []

            def copy_to_clipboard(self, value):
                self.copied.append(value)
                return True

            def close(self):
                pass

        class Engine:
            def __init__(self, solver):
                self.events = queue.Queue()
                self.signature = None
                self.sequence = 0

            def invalidate(self):
                self.signature = None
                self.sequence += 1

            def submit(self, image, signature, *args, **kwargs):
                self.signature = signature
                self.sequence += 1
                return self.sequence

            def close(self):
                pass

        options = {**DEFAULTS, 'corner_key': 'grave', 'solve_key': 'ctrl+enter',
                   'show_key': 'backslash', 'opacity': .42, 'startup': False,
                   'expected_options': 4, 'region': None, 'mode': 'auto'}
        with (patch('tray_app.ExamSolver', Solver), patch('tray_app.PrefetchEngine', Engine),
              patch('tray_app.WebBridge', return_value=MagicMock()),
              patch('tray_app.load_ui_settings', return_value=options.copy()),
              patch('tray_app.save_ui_settings'), patch('tray_app.set_restart_shortcut'),
              patch.object(TrayApp, 'bind_keys'),
              patch.object(TrayApp, 'unbind_keys'), patch.object(TrayApp, 'record'),
              patch('tray_app.system_snapshot', return_value={})):
            controller = TrayApp(self.app)
            try:
                controller.set_debug_mode(True, persist=False)
                self.assertTrue(controller.debug_panel.isVisible())
                with patch('tray_app.current_cursor', side_effect=[(100, 100), (500, 300)]):
                    controller.corner()
                    controller.corner()
                self.assertEqual(controller.settings['region'], [100, 100, 500, 300])
                controller.toggle_reading_mode()
                self.assertEqual(controller.settings['reading_mode'], 'manual')
                controller.toggle_reading_mode()
                self.assertEqual(controller.settings['reading_mode'], 'auto')
                self.assertTrue(controller.capture_border.isVisible())
                controller.capture = lambda: Image.new('RGB', (400, 200), 'white')
                controller.solve()
                self.assertEqual(controller.overlay.status, 'busy')
                self.assertEqual(controller.status_state, 'solving')
                controller.engine.events.put({'type': 'result', 'sequence': controller.engine.sequence,
                                              'result': {'best_choice': 'A, B', 'matched_source': 'HTML'},
                                              'image_to_answer_seconds': 2.0,
                                              'enter_to_answer_seconds': 1.0})
                controller.tick()
                self.assertEqual(controller.solver.copied, ['A, B'])
                self.assertEqual(controller.status_state, 'done')
                self.assertTrue(controller.status_dot.isVisible())
                self.assertEqual(controller.debug_panel.answer.text(), 'Đáp án: A, B')
                self.assertIn('1.00s', controller.debug_panel.timing.text())
                controller.hold(True)
                self.assertTrue(controller.overlay.isVisible())
                controller.hold(False)
                self.assertFalse(controller.overlay.isVisible())
                controller.solve()
                self.assertEqual(controller.overlay.answer, 'A, B')
                controller.engine.events.put({'type': 'result', 'sequence': controller.engine.sequence,
                                              'result': {'error': 'missing C'},
                                              'image_to_answer_seconds': 2.0,
                                              'enter_to_answer_seconds': 1.0})
                with patch.object(controller, 'notify'):
                    controller.tick()
                self.assertEqual(controller.overlay.answer, 'A, B')
                self.assertEqual(controller.overlay.status, 'error')
                self.assertEqual(controller.debug_panel.answer.text(), 'Đáp án trước: A, B')
                controller.settings['border_mode'] = 'hold'
                controller.set_debug_mode(False, persist=False)
                self.assertFalse(controller.capture_border.isVisible())
                controller.border_hold(True)
                self.assertTrue(controller.capture_border.isVisible())
                controller.border_hold(False)
                self.assertFalse(controller.capture_border.isVisible())
                controller.settings['answer_mode'] = 'always'
                controller.update_answer_visibility()
                self.assertTrue(controller.overlay.isVisible())
                controller.settings['status_dot_visible'] = False
                controller.set_status('done')
                self.assertFalse(controller.status_dot.isVisible())
                self.assertFalse(hasattr(controller, 'tray'))
            finally:
                controller.quit()

    def test_manual_redraw_is_atomic_and_cancel_restores_old_boxes(self):
        old = [[i*100, 0, i*100+90, 60] for i in range(5)]
        settings = {**DEFAULTS, 'startup': False, 'reading_mode': 'manual',
                    'manual_regions': old, 'manual_display': None}
        # The display fingerprint is part of saved-region validity.
        from tray_app import display_signature
        settings['manual_display'] = display_signature()
        solver = MagicMock()
        solver.settings = {'expected_options': 4}
        engine = MagicMock()
        engine.events = queue.Queue()
        engine.sequence = 2
        with (patch('tray_app.ExamSolver', return_value=solver),
              patch('tray_app.PrefetchEngine', return_value=engine),
              patch('tray_app.WebBridge', return_value=MagicMock()),
              patch('tray_app.load_ui_settings', return_value=settings.copy()),
              patch('tray_app.save_ui_settings') as save,
              patch('tray_app.set_restart_shortcut'),
              patch.object(TrayApp, 'bind_keys'), patch.object(TrayApp, 'unbind_keys')):
            controller = TrayApp(self.app)
            try:
                controller.start_redraw()
                self.assertEqual(controller.active_regions(), [])
                self.assertEqual(controller.settings['manual_regions'], old)
                engine.events.put({'type': 'result', 'sequence': 1,
                                   'result': {'best_choice': 'A'},
                                   'image_to_answer_seconds': 1.0,
                                   'enter_to_answer_seconds': .5})
                controller.tick()
                solver.copy_to_clipboard.assert_not_called()
                with patch('tray_app.current_cursor', side_effect=[(0, 0), (200, 100)]):
                    controller.corner()
                    controller.corner()
                self.assertEqual(len(controller.draft_regions), 1)
                controller.undo_redraw()
                self.assertEqual(controller.draft_regions, [])
                controller.cancel_redraw()
                self.assertEqual(controller.active_regions(), old)
                self.assertEqual(save.call_count, 0)
                controller.start_redraw()
                points = []
                for i in range(5):
                    points.extend([(i*210, 0), (i*210+200, 100)])
                with patch('tray_app.current_cursor', side_effect=points):
                    for _ in points:
                        controller.corner()
                self.assertFalse(controller.redraw_active)
                self.assertNotEqual(controller.settings['manual_regions'], old)
                self.assertEqual(len(controller.active_regions()), 5)
                self.assertEqual(save.call_count, 1)
            finally:
                controller.quit()


if __name__ == '__main__':
    unittest.main()
