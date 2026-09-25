"""V2 OCR: direct image input and a real 960-pixel detection limit."""
import io
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import unicodedata
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

    def _recognize_crop(self, image, box, lang, tessdata):
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
        try:
            process = subprocess.run(
                [self.vietnamese_cmd, 'stdin', 'stdout', '--tessdata-dir',
                 str(tessdata), '-l', lang, '--oem', '1', '--psm', '7'],
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
        for box in boxes:
            original = box['text']
            improved = None
            if self._needs_vietnamese(original):
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
