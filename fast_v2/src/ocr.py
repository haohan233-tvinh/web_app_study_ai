"""V2 OCR: direct image input and a real 960-pixel detection limit."""
import io
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

    @staticmethod
    def preprocess(image):
        image = image.convert('RGB')
        image.thumbnail((1700, 1300), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image.convert('L')).enhance(2.0)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        return ImageOps.expand(image, border=32, fill=255)

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
        rows = []
        for box in sorted(boxes, key=lambda b: (b['cy'], b['left'])):
            row = next((r for r in rows if abs(r[0]['cy'] - box['cy'])
                        < .42 * min(r[0]['height'], box['height'])), None)
            if row is None:
                rows.append([box])
            else:
                row.append(box)
        lines = [' '.join(b['text'] for b in sorted(row, key=lambda b: b['left']))
                 for row in rows]
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
