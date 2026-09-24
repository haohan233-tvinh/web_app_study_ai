"""Local OCR: bounded CPU threads, row geometry, and no fabricated missing labels."""
import io
from PIL import Image, ImageEnhance, ImageOps


class OCR:
    def __init__(self, threads=2):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=1,
                               det_use_cuda=False, cls_use_cuda=False, rec_use_cuda=False,
                               use_cls=False, text_score=.45, det_limit_side_len=1280, det_limit_type='max')

    @staticmethod
    def preprocess(image):
        image = image.convert('RGB')
        image.thumbnail((1700, 1300), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image.convert('L')).enhance(2.0)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        return ImageOps.expand(image, border=32, fill=255)

    def read(self, image, enhanced=True):
        image = self.preprocess(image) if enhanced else ImageOps.expand(image.convert('RGB'), border=24, fill='white')
        data = io.BytesIO()
        image.save(data, format='PNG')
        result, _ = self.engine(data.getvalue(), use_cls=False)
        if not result:
            return [], []
        boxes = []
        for box, text, score in result:
            if text.strip():
                xs, ys = [p[0] for p in box], [p[1] for p in box]
                boxes.append({'text': text.strip(), 'score': float(score), 'left': min(xs),
                              'cy': (min(ys) + max(ys)) / 2, 'height': max(ys) - min(ys)})
        rows = []
        for box in sorted(boxes, key=lambda b: (b['cy'], b['left'])):
            row = next((r for r in rows if abs(r[0]['cy'] - box['cy']) < .42 * min(r[0]['height'], box['height'])), None)
            if row is None:
                rows.append([box])
            else:
                row.append(box)
        return [' '.join(b['text'] for b in sorted(row, key=lambda b: b['left'])) for row in rows], boxes
