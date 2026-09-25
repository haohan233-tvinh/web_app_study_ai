"""Latest-image-only OCR prefetch and serialized local inference."""
import queue
import threading
import time


class PrefetchEngine:
    def __init__(self, solver):
        self.solver = solver
        self.cv = threading.Condition()
        self.events = queue.Queue()
        self.sequence = 0
        self.signature = None
        self.image_time = None
        self.pending = None
        self.prepared = None
        self.requested = None
        self.closed = False
        self.model_load_seconds = None
        self.warm_ready = threading.Event()
        self.threads = [
            threading.Thread(target=self._warm, name='v2-model-warm', daemon=True),
            threading.Thread(target=self._ocr_loop, name='v2-ocr', daemon=True),
            threading.Thread(target=self._solve_loop, name='v2-solve', daemon=True),
        ]
        for thread in self.threads:
            thread.start()

    def _warm(self):
        start = time.perf_counter()
        try:
            self.solver.model.start()
            self.events.put({'type': 'ready', 'model_load_seconds': round(time.perf_counter()-start, 3)})
        except Exception as error:
            self.events.put({'type': 'warm_error', 'error': str(error)})
        finally:
            self.model_load_seconds = round(time.perf_counter()-start, 3)
            self.warm_ready.set()

    def submit(self, image, signature, captured_at=None, solve=False, mode='auto'):
        """Replace pending OCR; equal frames reuse its result. Enter binds to this frame."""
        now = time.perf_counter()
        with self.cv:
            if self.closed:
                return None
            if signature != self.signature:
                self.sequence += 1
                self.signature = signature
                self.image_time = captured_at or now
                self.pending = (self.sequence, image)
                self.prepared = None
                self.requested = None
            if solve:
                self.requested = (self.sequence, now, mode)
            self.cv.notify_all()
            return self.sequence

    def invalidate(self):
        with self.cv:
            self.sequence += 1
            self.signature = None
            self.pending = None
            self.prepared = None
            self.requested = None
            self.cv.notify_all()

    def wait_prepared(self, sequence, timeout=15):
        """Wait for OCR of a specific frame; false if superseded or timed out."""
        deadline = time.monotonic() + timeout
        with self.cv:
            while not self.closed and self.sequence == sequence:
                if self.prepared is not None and self.prepared[0] == sequence:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self.cv.wait(timeout=remaining)
        return False

    def _ocr_loop(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                seq, image = self.pending
                self.pending = None
                if seq == self.sequence:
                    self.events.put({'type': 'ocr_started', 'sequence': seq})
            try:
                value = self.solver.prepare_image(image)
            except Exception as error:
                value = {'error': 'OCR: ' + str(error), 'ocr_seconds': 0, 'reread': False}
            with self.cv:
                if not self.closed and seq == self.sequence:
                    self.prepared = (seq, value)
                    self.events.put({'type': 'ocr_ready', 'sequence': seq,
                                     'lines': value.get('lines', []),
                                     'error': value.get('error'),
                                     'ocr_seconds': value.get('ocr_seconds'),
                                     'vietnamese_ocr_seconds': value.get('vietnamese_ocr_seconds', 0),
                                     'code_ocr_seconds': value.get('code_ocr_seconds', 0),
                                     'code_reread': value.get('code_reread', False),
                                     'reread': value.get('reread', False),
                                     'section_ocr_seconds': value.get('section_ocr_seconds'),
                                     'layout_method': value.get('layout_method'),
                                     'capture_source': value.get('capture_source', 'OCR'),
                                     'weak_layout': value.get('weak_layout', False)})
                    self.cv.notify_all()

    def _solve_loop(self):
        while True:
            with self.cv:
                self.cv.wait_for(lambda: self.closed or (self.requested is not None and
                    self.prepared is not None and self.requested[0] == self.prepared[0]))
                if self.closed:
                    return
                seq, entered_at, mode = self.requested
                prepared = self.prepared[1]
                image_time = self.image_time
                self.requested = None
            self.warm_ready.wait()
            with self.cv:
                if self.closed or seq != self.sequence:
                    continue
                self.events.put({'type': 'solve_started', 'sequence': seq})
            try:
                result = (prepared if 'error' in prepared else
                          self.solver.solve_prepared(prepared, mode))
            except Exception as error:
                result = {'error': str(error)}
            finished = time.perf_counter()
            with self.cv:
                if not self.closed and seq == self.sequence:
                    self.events.put({'type': 'result', 'sequence': seq, 'result': result,
                                     'entered_at': entered_at, 'image_at': image_time,
                                     'image_to_answer_seconds': round(finished-image_time, 3),
                                     'enter_to_answer_seconds': round(finished-entered_at, 3),
                                     'model_load_seconds': self.model_load_seconds})

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()
        # ONNX work may be in flight. Daemon workers exit with the parent process.
        for thread in self.threads:
            thread.join(timeout=.1)
