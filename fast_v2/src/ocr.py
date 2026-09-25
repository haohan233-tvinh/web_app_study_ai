"""V2 OCR: direct image input and a real 960-pixel detection limit."""
import io
import csv
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import unicodedata
from statistics import median
from PIL import Image, ImageEnhance, ImageOps


class OCR:
    def __init__(self, threads=2):
        from rapidocr_onnxruntime import RapidOCR
        from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess

        self.engine = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1,
                               det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False,
                               use_cls=False, text_score=.45, det_limit_side_len=960,
                               det_limit_type='max')
        detector = self.engine.text_det
        # RapidOCR 1.4.4 ignores det_limit_side_len for limit_type=max.
        # Override only this engine instance; do not patch the installed package.
        detector.get_preprocess = lambda max_wh: DetPreProcess(
            960, 'max', detector.mean, detector.std)
        self.quality_engine = None
        self.threads = threads
        bundled = Path(__file__).resolve().parents[2] / 'models' / 'ocr' / 'tessdata'
        tesseract = shutil.which('tesseract')
        if os.name == 'nt' and not tesseract:
            installed = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tesseract-OCR' / 'tesseract.exe'
            if installed.is_file():
                tesseract = str(installed)
        self.tesseract_cmd = tesseract
        self.vietnamese_cmd = tesseract if (bundled / 'vie.traineddata').is_file() else None
        self.vietnamese_data = bundled
        self.english_data = Path(tesseract).parent / 'tessdata' if tesseract else None

    @staticmethod
    def _plain(value):
        return ''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                       if unicodedata.category(c) != 'Mn').replace('đ', 'd')

    @classmethod
    def _needs_vietnamese(cls, value):
        if len(value) < 24 or re.search(r'[`$→{};=]|->|=>', value):
            return False
        words = set(re.findall(r'[a-z]+', cls._plain(value)))
        markers = {'trong', 'ngoai', 'chinh', 'dung', 'khong', 'nao', 'cau', 'dap',
                   'ung', 'mau', 'chu', 'cho', 'voi', 'cac', 'duoc', 'khi', 'neu',
                   'mot', 'phap', 'gom', 'nhom', 'thanh', 'phan', 'thu', 'biet',
                   'sau', 'day', 'nhung', 'loai', 'bien', 'hop', 'vao'}
        return len(words & markers) >= 2

    @staticmethod
    def _accent_count(value):
        return sum(unicodedata.category(c) == 'Mn'
                   for c in unicodedata.normalize('NFD', value))

    @classmethod
    def _safe_vietnamese(cls, original, candidate):
        candidate = ' '.join(candidate.split()).strip()
        if not candidate or cls._accent_count(candidate) <= cls._accent_count(original):
            return None
        if not .72 <= len(candidate) / max(len(original), 1) <= 1.35:
            return None
        old = cls._plain(original)
        new = cls._plain(candidate)
        if difflib.SequenceMatcher(None, old, new).ratio() < .82:
            return None
        # Keep exact option numbering and HTML/code tokens from the original OCR.
        number = re.match(r'^\s*\d+[.):]', original)
        if number:
            candidate = re.sub(r'^\s*[^\s]+', number.group().strip(), candidate, count=1)
        tags = re.findall(r'<[^<>]+>', original)
        if tags:
            found = list(re.finditer(r'<[^<>]+>', candidate))
            if len(tags) != len(found):
                return None
            for match, tag in reversed(list(zip(found, tags))):
                candidate = candidate[:match.start()] + tag + candidate[match.end():]
        ending = re.search(r'[.,?!:]$', original.rstrip())
        if ending:
            candidate = re.sub(r'[.,?!:]*$', '', candidate.rstrip()) + ending.group()
        return candidate

    @classmethod
    def _safe_code(cls, original, candidate):
        candidate = ' '.join(candidate.split()).strip()
        first = original.split()[0] if original.split() else ''
        if first and first in candidate:
            candidate = candidate[candidate.find(first):]
        if candidate.count('{') != candidate.count('}') or '{' not in candidate:
            return None
        if not .75 <= len(candidate) / max(len(original), 1) <= 1.25:
            return None
        if difflib.SequenceMatcher(None, original.casefold(), candidate.casefold()).ratio() < .82:
            return None
        return candidate

    def _recognize_crop(self, image, box, lang, tessdata, whitelist=None):
        left = max(0, int(box['left']) - 8)
        top = max(0, int(box['top']) - 8)
        right = min(image.width, int(box['right']) + 8)
        bottom = min(image.height, int(box['bottom']) + 8)
        if right <= left or bottom <= top:
            return ''
        crop = image.crop((left, top, right, bottom)).convert('RGB')
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
        crop = ImageOps.expand(crop, border=20, fill='white')
        buffer = io.BytesIO()
        crop.save(buffer, format='PNG')
        command = [self.tesseract_cmd, 'stdin', 'stdout', '--tessdata-dir',
                   str(tessdata), '-l', lang, '--oem', '1', '--psm', '7']
        if whitelist:
            command += ['-c', f'tessedit_char_whitelist={whitelist}']
        try:
            process = subprocess.run(
                command,
                input=buffer.getvalue(), capture_output=True, timeout=5,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                env={**os.environ, 'OMP_THREAD_LIMIT': str(self.threads)})
        except (OSError, subprocess.TimeoutExpired):
            return ''
        return process.stdout.decode('utf-8', 'replace') if process.returncode == 0 else ''

    def refine_vietnamese(self, image, lines, boxes):
        """Correct prose accents without replacing code/arrow answer strings."""
        if not self.vietnamese_cmd:
            return lines, boxes, 0.0
        start = time.perf_counter()
        changed = False
        attempted = False
        boxes = [dict(box) for box in boxes]
        ordered = sorted(boxes, key=lambda box: (box['cy'], box['left']))
        for index, box in enumerate(ordered):
            original = box['text']
            improved = None
            previous = next((other for other in reversed(ordered[:index])
                             if other['cy'] < box['cy'] - .4 * box['height']), None)
            continuation = bool(
                previous and 10 <= len(original) < 24 and
                box['top'] - previous['bottom'] <= 3 * max(box['height'], previous['height']) and
                self._needs_vietnamese(previous['text']) and
                not re.search(r'[`$→{};=<>]|->|=>', original) and
                (self._accent_count(original) or
                 set(re.findall(r'[a-z]+', self._plain(original))) &
                 {'trong', 'ngoai', 'dung', 'khong', 'voi', 'duoc', 'nhung', 'tren',
                  'sau', 'day', 'khi', 'neu', 'cho', 'cua'}))
            if self._needs_vietnamese(original) or continuation:
                attempted = True
                improved = self._safe_vietnamese(original, self._recognize_crop(
                    image, box, 'vie', self.vietnamese_data))
            elif (self.english_data and (self.english_data / 'eng.traineddata').is_file()
                  and original.count('{') != original.count('}')
                  and re.search(r'\b(?:color|background|margin|padding|display|font)\s*:', original, re.I)):
                attempted = True
                improved = self._safe_code(original, self._recognize_crop(
                    image, box, 'eng', self.english_data))
            if improved:
                box['text'] = improved
                changed = True
        if changed:
            lines = self._lines(boxes)
        return lines, boxes, round(time.perf_counter() - start, 3) if attempted else 0.0

    @staticmethod
    def _code_line(value):
        return bool(re.search(
            r'\b(?:const|let|var|function|return|if|else|for|while|class|def|'
            r'console|import|export)\b|[{};]|=>|===|\[[0-9]+\]|'
            r'</?[a-z][^>]{0,150}>|'
            r'^\s*[a-z_$][\w$]*\s*:\s*[^?]+[,;]\s*$', value, re.I))

    def refine_code(self, image, lines, boxes, region_bottom=None):
        """Re-read a multiline code run with English TSV OCR, retaining indentation."""
        if (not self.tesseract_cmd or not self.english_data or
                not (self.english_data / 'eng.traineddata').is_file()):
            return lines, boxes, 0.0, False
        eligible = [box for box in boxes if region_bottom is None or
                    box['cy'] < region_bottom]
        code_boxes = sorted((box for box in eligible if self._code_line(box['text'])),
                            key=lambda box: box['cy'])
        if len(code_boxes) < 2:
            return lines, boxes, 0.0, False
        line_height = median(box['height'] for box in code_boxes)
        runs = [[code_boxes[0]]]
        for box in code_boxes[1:]:
            if box['cy'] - runs[-1][-1]['cy'] > 2.7 * line_height:
                runs.append([])
            runs[-1].append(box)
        code = max(runs, key=len)
        if len(code) < 2 or code[-1]['cy'] - code[0]['cy'] < 1.3 * line_height:
            return lines, boxes, 0.0, False
        start = time.perf_counter()
        height = median(box['height'] for box in code)
        top = max(0, int(code[0]['top'] - (3 if len(code) == 2 else 1) * height))
        bottom = min(image.height, int(code[-1]['bottom'] + 6 * height))
        if region_bottom is not None:
            bottom = min(bottom, int(region_bottom))
        crop = image.crop((0, top, image.width, bottom)).convert('RGB')
        buffer = io.BytesIO()
        crop.save(buffer, format='PNG')
        try:
            process = subprocess.run(
                [self.tesseract_cmd, 'stdin', 'stdout', '--tessdata-dir',
                 str(self.english_data), '-l', 'eng', '--oem', '1', '--psm', '6',
                 '-c', 'preserve_interword_spaces=1', 'tsv'],
                input=buffer.getvalue(), capture_output=True, timeout=6,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                env={**os.environ, 'OMP_THREAD_LIMIT': str(self.threads)})
        except (OSError, subprocess.TimeoutExpired):
            return lines, boxes, round(time.perf_counter() - start, 3), False
        if process.returncode:
            return lines, boxes, round(time.perf_counter() - start, 3), False
        rows = {}
        for word in csv.DictReader(io.StringIO(process.stdout.decode('utf-8', 'replace')),
                                   delimiter='\t', quoting=csv.QUOTE_NONE):
            value = (word.get('text') or '').strip()
            if not value or word.get('level') != '5':
                continue
            try:
                key = (word['block_num'], word['par_num'], word['line_num'])
                item = (int(word['left']), int(word['top']) + top,
                        int(word['width']), int(word['height']),
                        max(0.0, float(word['conf']) / 100), value)
            except (KeyError, ValueError):
                continue
            rows.setdefault(key, []).append(item)
        if not rows:
            return lines, boxes, round(time.perf_counter() - start, 3), False
        cell_widths = [word[2] / len(word[5]) for words in rows.values()
                       for word in words if len(word[5]) >= 2 and word[5].isalpha()]
        cell = median(cell_widths) * 1.08 if cell_widths else max(5.0, height * .6)
        baseline = min(min(word[0] for word in words) for words in rows.values())
        candidates = []
        for words in rows.values():
            words.sort(key=lambda item: item[0])
            indent = min(24, max(0, round((words[0][0] - baseline) / cell)))
            parts, end = [' ' * indent], None
            for left, y, width, word_height, confidence, value in words:
                if end is not None:
                    gap = max(0, int((left - end + 1) / cell))
                    parts.append(' ' * min(12, gap))
                parts.append(value)
                end = left + width
            text = ''.join(parts).rstrip()
            candidates.append({'text': text, 'score': min(word[4] for word in words),
                               'left': words[0][0], 'right': max(w[0]+w[2] for w in words),
                               'top': min(w[1] for w in words),
                               'bottom': max(w[1]+w[3] for w in words)})
        candidates.sort(key=lambda box: box['top'])
        indexes = [i for i, box in enumerate(candidates) if self._code_line(box['text'])]
        if not indexes:
            return lines, boxes, round(time.perf_counter() - start, 3), False
        candidates = candidates[indexes[0]:indexes[-1]+1]
        # Tesseract may put an indented line into a separate TSV block. Its
        # first word then becomes that block's own baseline and loses spaces.
        # Rebase every line against the left edge of this code run instead.
        code_left = min(box['left'] for box in candidates)
        for candidate in candidates:
            indent = min(24, max(0, round((candidate['left'] - code_left) / cell)))
            candidate['text'] = ' ' * indent + candidate['text'].lstrip()
        # Tesseract's language model often changes a short punctuation-only
        # line such as `};` into `33`. A second pass limited to code punctuation
        # can recover the glyphs without rewriting identifiers or prose.
        for candidate in candidates:
            value = candidate['text'].strip()
            if len(value) > 4 or not re.fullmatch(r'[\d{}();\[\] ]+', value):
                continue
            if not any(char.isdigit() for char in value):
                continue
            glyphs = self._recognize_crop(image, candidate, 'eng', self.english_data,
                                          whitelist='{}();[]').strip()
            if glyphs and re.fullmatch(r'[{}();\[\]]+', glyphs) and (
                    any(char in glyphs for char in '{}()[]') or len(glyphs) >= 2):
                candidate['text'] = candidate['text'][:len(candidate['text']) -
                                                    len(candidate['text'].lstrip())] + glyphs
        old = '\n'.join(box['text'] for box in code)
        new = '\n'.join(box['text'] for box in candidates)
        similarity = difflib.SequenceMatcher(
            None, re.sub(r'\s+', '', old).casefold(),
            re.sub(r'\s+', '', new).casefold()).ratio()
        old_braces = old.count('{') + old.count('}')
        new_braces = new.count('{') + new.count('}')
        gained_indent = (any(line.startswith('  ') for line in new.splitlines()) and
                         not any(line.startswith('  ') for line in old.splitlines()))
        gained_index = (len(re.findall(r'\[[0-9]+\]', new)) >
                        len(re.findall(r'\[[0-9]+\]', old)))
        improved = (similarity >= .67 and len(candidates) >= len(code) and
                    new_braces >= old_braces and
                    new.count('"') >= old.count('"') and
                    new.count("'") >= old.count("'") and
                    new.count('=>') >= old.count('=>') and
                    new.count('<') >= old.count('<') and
                    new.count('>') >= old.count('>') and
                    (len(candidates) > len(code) or new_braces > old_braces or
                     gained_indent or gained_index))
        elapsed = round(time.perf_counter() - start, 3)
        if not improved:
            return lines, boxes, elapsed, False
        first, last = candidates[0]['top'], candidates[-1]['bottom']
        kept = [dict(box) for box in boxes if not first-height*.5 <= box['cy'] <= last+height*.5]
        for box in candidates:
            box['cy'] = (box['top'] + box['bottom']) / 2
            box['height'] = box['bottom'] - box['top']
        result = kept + candidates
        code_top = min(code[0]['top'], candidates[0]['top'])
        code_bottom = max(code[-1]['bottom'], candidates[-1]['bottom'])
        code_rows = [box for box in result if code_top <= box['cy'] <= code_bottom]
        if code_rows:
            base_left = min(box['left'] for box in code_rows)
            for box in code_rows:
                indent = min(24, max(0, round((box['left'] - base_left) / cell)))
                box['text'] = ' ' * indent + box['text'].lstrip()
        return self._lines(result), result, elapsed, True

    @staticmethod
    def preprocess(image):
        image = image.convert('RGB')
        image.thumbnail((1700, 1300), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image.convert('L')).enhance(2.0)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        return ImageOps.expand(image, border=32, fill=255)

    @staticmethod
    def _lines(boxes):
        rows = []
        for box in sorted(boxes, key=lambda b: (b['cy'], b['left'])):
            row = next((r for r in rows if abs(r[0]['cy'] - box['cy'])
                        < .42 * min(r[0]['height'], box['height'])), None)
            if row is None:
                rows.append([box])
            else:
                row.append(box)
        return [' '.join(b['text'] for b in sorted(row, key=lambda b: b['left']))
                for row in rows]

    @staticmethod
    def _rows(result, original_size=None, prepared_size=None, padding=0):
        if not result:
            return [], []
        boxes = []
        for box, value, score in result:
            if value.strip():
                xs, ys = [p[0] for p in box], [p[1] for p in box]
                boxes.append({'text': value.strip(), 'score': float(score),
                              'left': min(xs), 'right': max(xs),
                              'top': min(ys), 'bottom': max(ys),
                              'cy': (min(ys) + max(ys)) / 2,
                              'height': max(ys) - min(ys)})
        # The quality engine sometimes detects a whole answer and its last
        # character twice (for example ``B.2`` plus a second ``2`` inside the
        # same bounding box). Treat nested, identical text as one observation.
        boxes = [box for box in boxes if not any(
            other is not box and len(other['text']) > len(box['text']) and
            box['text'].casefold() in other['text'].casefold() and
            max(0, min(other['right'], box['right']) -
                max(other['left'], box['left'])) >= .5 * (box['right'] - box['left']) and
            max(0, min(other['bottom'], box['bottom']) -
                max(other['top'], box['top'])) >= .7 * box['height']
            for other in boxes)]
        lines = OCR._lines(boxes)
        if original_size and prepared_size:
            sx = original_size[0] / (prepared_size[0] - 2 * padding)
            sy = original_size[1] / (prepared_size[1] - 2 * padding)
            for box in boxes:
                for key in ('left', 'right'):
                    box[key] = max(0, min(original_size[0], (box[key] - padding) * sx))
                for key in ('top', 'bottom', 'cy'):
                    box[key] = max(0, min(original_size[1], (box[key] - padding) * sy))
                box['height'] *= sy
        return lines, boxes

    def read(self, image, enhanced=True):
        prepared = (self.preprocess(image) if enhanced else
                    ImageOps.expand(image.convert('RGB'), border=24, fill='white'))
        result, _ = self.engine(prepared, use_cls=False)
        return self._rows(result, image.size, prepared.size, 32 if enhanced else 24)

    def read_quality(self, image, enhanced=True):
        """Exact V1 image path for difficult captures; created only on demand."""
        if self.quality_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.quality_engine = RapidOCR(intra_op_num_threads=self.threads,
                inter_op_num_threads=1, det_use_cuda=False, cls_use_cuda=False,
                rec_use_cuda=False, use_cls=False, text_score=.45,
                det_limit_side_len=1280, det_limit_type='max')
        prepared = (self.preprocess(image) if enhanced else
                    ImageOps.expand(image.convert('RGB'), border=24, fill='white'))
        data = io.BytesIO()
        prepared.save(data, format='PNG')
        result, _ = self.quality_engine(data.getvalue(), use_cls=False)
        return self._rows(result, image.size, prepared.size, 32 if enhanced else 24)
