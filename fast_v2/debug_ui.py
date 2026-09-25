"""Visible diagnostics for testing capture, OCR, inference and answers."""
import ctypes
from ctypes import wintypes
import time

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QLabel, QPlainTextEdit, QVBoxLayout,
                             QWidget)


class _Rect(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', _Rect),
                ('rcWork', _Rect), ('dwFlags', wintypes.DWORD),
                ('szDevice', wintypes.WCHAR * 32)]


def region_to_qrect(region):
    """Map ImageGrab's physical desktop coordinates to Qt logical coordinates."""
    if not region:
        return None
    left, top, right, bottom = region
    user = ctypes.windll.user32
    user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user.MonitorFromPoint.restype = wintypes.HMONITOR
    user.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
    center = wintypes.POINT((left + right) // 2, (top + bottom) // 2)
    monitor = user.MonitorFromPoint(center, 2)
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)):
        device = info.szDevice.replace('\\\\.\\', '').casefold()
        for screen in QApplication.screens():
            if screen.name().replace('\\\\.\\', '').casefold() == device:
                geo = screen.geometry()
                scale = screen.devicePixelRatio()
                return QRect(geo.x() + round((left - info.rcMonitor.left) / scale),
                             geo.y() + round((top - info.rcMonitor.top) / scale),
                             max(1, round((right - left) / scale)),
                             max(1, round((bottom - top) / scale)))
    return QRect(left, top, right-left, bottom-top)


class CaptureBorder(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.NoDropShadowWindowHint |
                         Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.color = QColor('#00b4b9')
        self.opacity = .85

    def configure(self, color, opacity):
        self.color = QColor(color)
        self.opacity = opacity
        self.update()

    def set_region(self, region):
        rect = region_to_qrect(region)
        if rect is None:
            self.hide()
            return
        self.setGeometry(rect.x()-5, rect.y()-5, rect.width()+10, rect.height()+10)
        self.show()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.color)
        color.setAlphaF(self.opacity)
        painter.setPen(QPen(color, 2))
        # Border sits outside the exact ImageGrab bbox and never enters OCR.
        painter.drawRect(2, 2, self.width()-5, self.height()-5)
        painter.end()


class StatusDot(QWidget):
    COLORS = {
        'loading': '#8b929b',
        'waiting': '#4489e3',
        'ocr': '#28c4d4',
        'ready': '#a673e3',
        'solving': '#f1a23f',
        'done': '#42ca75',
        'recapture': '#ead34e',
        'error': '#ec5555',
    }

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.NoDropShadowWindowHint |
                         Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.state = 'loading'
        self.capture_excluded = False
        self.setFixedSize(5, 5)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            user = ctypes.windll.user32
            user.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
            user.SetWindowDisplayAffinity.restype = wintypes.BOOL
            self.capture_excluded = bool(user.SetWindowDisplayAffinity(int(self.winId()), 0x11))
        except (OSError, AttributeError, TypeError):
            self.capture_excluded = False

    def set_state(self, state, region=None):
        if state not in self.COLORS:
            raise ValueError(f'Unknown status: {state}')
        changed = self.state != state
        self.state = state
        rect = region_to_qrect(region)
        center = rect.center() if rect else QPoint()
        screen = QApplication.screenAt(center) if rect else QApplication.primaryScreen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            side = max(1, round(5 / screen.devicePixelRatio()))
            if self.width() != side:
                self.setFixedSize(side, side)
            x, y = geo.x() + geo.width() - side, geo.y() + geo.height() - side
            if self.pos() != QPoint(x, y):
                self.move(x, y)
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.COLORS[self.state]))
        painter.end()


class DebugPanel(QWidget):
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Web MCQ Fast — Kiểm thử')
        self.setMinimumWidth(440)
        self.set_answer_color('#b82020')
        self.setup_contents()

    def set_answer_color(self, answer_color):
        self.setStyleSheet('''
            QWidget { background: #111820; color: #eef5f8; font-family: Segoe UI; }
            QLabel#status { color: #6ce0d9; font-size: 14px; font-weight: 600; }
            QLabel#answer { color: COLOR; font-size: 24px; font-weight: 700; }
            QPlainTextEdit { background: #1d2832; border: 1px solid #3d515e; }
        '''.replace('COLOR', QColor(answer_color).name()))

    def setup_contents(self):
        layout = QVBoxLayout(self)
        self.status = QLabel('Chưa chọn vùng. Bấm ` tại hai góc câu hỏi.')
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumBlockCount(100)
        self.history.setFixedHeight(80)
        self.history.setPlaceholderText('Các bước xử lý sẽ hiện ở đây.')
        self.preview = QLabel('Ảnh sẽ hiện ở đây sau khi chọn vùng.')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(420, 150)
        self.preview.setStyleSheet('border: 1px solid #3d515e; background: #1d2832;')
        self.region = QLabel('Vùng: chưa chọn')
        self.ocr = QPlainTextEdit()
        self.ocr.setReadOnly(True)
        self.ocr.setPlaceholderText('Văn bản OCR sẽ hiện ở đây.')
        self.ocr.setFixedHeight(94)
        self.sections = QPlainTextEdit()
        self.sections.setReadOnly(True)
        self.sections.setPlaceholderText('Ảnh và OCR riêng cho Đề / từng đáp án sẽ hiện ở đây.')
        self.sections.setFixedHeight(150)
        self.answer = QLabel('Đáp án: —')
        self.answer.setObjectName('answer')
        self.source = QLabel('Slide: —')
        self.source.setWordWrap(True)
        self.timing = QLabel('Thời gian: —')
        self.timing.setWordWrap(True)
        for item in (self.status, self.history, self.preview, self.region, self.ocr, self.sections,
                     self.answer, self.source, self.timing):
            layout.addWidget(item)
        self.resize(450, 640)

    def set_stage(self, message, record=True):
        self.status.setText(message)
        if record:
            self.history.appendPlainText(f'{time.strftime("%H:%M:%S")}  {message}')

    def place_away_from(self, region):
        blocked = region_to_qrect(region)
        choices = []
        for screen in QApplication.screens():
            geo = screen.availableGeometry()
            for x in (geo.left()+12, geo.right()-self.width()-12):
                for y in (geo.top()+12, geo.bottom()-self.height()-12):
                    candidate = QRect(x, y, self.width(), self.height())
                    overlap = candidate.intersected(blocked) if blocked else QRect()
                    choices.append((overlap.width()*overlap.height(), x, y))
        if choices:
            _, x, y = min(choices)
            self.move(x, y)

    def show_region(self, region):
        if not region:
            self.region.setText('Vùng: chưa chọn')
            return
        left, top, right, bottom = region
        self.region.setText(f'Vùng: ({left}, {top}) → ({right}, {bottom}) · {right-left} × {bottom-top} px')
        self.place_away_from(region)

    def show_image(self, image):
        rgb = image.convert('RGB')
        raw = rgb.tobytes()
        qimage = QImage(raw, rgb.width, rgb.height, rgb.width*3,
                        QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimage).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)

    def show_capture(self, capture):
        if not hasattr(capture, 'crops'):
            self.preview.setFixedHeight(150)
            self.show_image(capture)
            return
        from PIL import Image, ImageDraw
        thumbnails = []
        for index, crop in enumerate(capture.crops):
            item = crop.convert('RGB')
            item.thumbnail((360, 85), Image.Resampling.LANCZOS)
            thumbnails.append(item)
        montage = Image.new('RGB', (420, 100 * len(thumbnails)), '#16222b')
        draw = ImageDraw.Draw(montage)
        for index, item in enumerate(thumbnails):
            draw.text((4, index * 100 + 4), 'Q' if index == 0 else chr(64 + index), fill='white')
            montage.paste(item, (40, index * 100 + 4))
        self.preview.setFixedHeight(min(600, montage.height))
        self.show_image(montage)

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()
