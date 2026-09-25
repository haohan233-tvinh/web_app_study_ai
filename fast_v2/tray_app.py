"""Quiet Windows UI for the offline V2 region solver."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QKeySequence, QCursor
from PyQt6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QWidget)

from clipboard_solver import ExamSolver, ROOT
from debug_ui import CaptureBorder, DebugPanel, StatusDot, region_to_qrect
from prefetch import PrefetchEngine
from src.layout import ManualCapture
from src.mouse_hotkeys import MouseHook, mouse_chord

UI_FILE = ROOT / 'ui_settings.json'
DEFAULTS = {'corner_key': 'grave', 'solve_key': 'ctrl+enter',
            'redraw_key': 'ctrl+alt+r', 'undo_key': 'backspace',
            'cancel_key': 'esc', 'settings_key': 'ctrl+alt+s',
            'quit_key': 'ctrl+alt+q', 'toggle_reading_key': 'ctrl+alt+m',
            'restart_key': 'ctrl+alt+w',
            'show_key': 'backslash', 'border_key': 'f8',
            'opacity': .42, 'border_opacity': .85,
            'answer_color': '#b82020', 'border_color': '#00b4b9',
            'answer_mode': 'hold', 'border_mode': 'test_only',
            'status_dot_visible': True, 'startup': True,
            'region': None, 'manual_regions': None, 'reading_mode': 'auto',
            'mode': 'auto', 'expected_options': 4,
            'debug_mode': False}


def load_ui_settings():
    try:
        loaded = json.loads(UI_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        loaded = {}
    return {**DEFAULTS, **loaded}


def save_ui_settings(settings):
    UI_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')


def startup_link():
    return (Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Startup'
            / 'Web MCQ Fast.lnk')


def set_startup(enabled):
    link = startup_link()
    if not enabled:
        link.unlink(missing_ok=True)
        return
    import win32com.client
    link.parent.mkdir(parents=True, exist_ok=True)
    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortcut(str(link))
    packaged = ROOT / 'Web MCQ Fast.exe'
    if getattr(sys, 'frozen', False) or packaged.is_file():
        shortcut.TargetPath = str(packaged)
        shortcut.Arguments = ''
    else:
        shortcut.TargetPath = str(Path(sys.executable).with_name('pythonw.exe'))
        shortcut.Arguments = f'"{ROOT / "tray_app.py"}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.Description = 'Offline Web MCQ Fast V2'
    shortcut.Save()


def restart_link():
    return (Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs'
            / 'Web MCQ Fast Start.lnk')


def set_restart_shortcut(hotkey):
    """Explorer owns this shortcut, so its keyboard hotkey works after app exit."""
    import win32com.client
    link = restart_link()
    link.parent.mkdir(parents=True, exist_ok=True)
    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortcut(str(link))
    packaged = ROOT / 'Web MCQ Fast.exe'
    if getattr(sys, 'frozen', False) or packaged.is_file():
        shortcut.TargetPath = str(packaged)
        shortcut.Arguments = ''
    else:
        shortcut.TargetPath = str(Path(sys.executable).with_name('pythonw.exe'))
        shortcut.Arguments = f'"{ROOT / "tray_app.py"}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.Description = 'Start offline Web MCQ Fast V2'
    shortcut.Hotkey = hotkey.upper()
    shortcut.Save()
    # Explorer does not always register a newly written .lnk hotkey until a
    # shell change notification (otherwise it may require sign-out).
    ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005,
                                        ctypes.c_wchar_p(str(link)), None)


def current_cursor():
    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError('Không đọc được vị trí chuột.')
    return point.x, point.y


def region_from_corners(a, b, min_width=80, min_height=50):
    left, top, right, bottom = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
    if right-left < min_width or bottom-top < min_height:
        raise ValueError(f'Vùng chụp quá nhỏ; cần ít nhất {min_width} × {min_height} px.')
    return [left, top, right, bottom]


def image_signature(image):
    # Full-resolution hash: a one-letter change must invalidate prefetched OCR.
    digest = hashlib.blake2b(digest_size=16)
    if isinstance(image, ManualCapture):
        for region, crop in zip(image.regions, image.crops):
            digest.update(bytes(str(region), 'ascii'))
            digest.update(crop.convert('L').tobytes())
    else:
        digest.update(image.convert('L').tobytes())
    return digest.digest()


def display_signature():
    return sorted([screen.name(), screen.geometry().x(), screen.geometry().y(),
                   screen.geometry().width(), screen.geometry().height(),
                   round(screen.devicePixelRatio(), 3)] for screen in QApplication.screens())


def system_snapshot():
    import psutil
    data = {'ram_available_mib': round(psutil.virtual_memory().available / 1048576)}
    try:
        line = subprocess.check_output(['nvidia-smi',
            '--query-gpu=temperature.gpu,memory.used,power.draw',
            '--format=csv,noheader,nounits'], text=True, timeout=3,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).splitlines()[0]
        values = [float(v.strip()) for v in line.split(',')]
        data.update(zip(['gpu_temperature_c', 'vram_used_mib', 'gpu_power_w'], values))
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        pass
    return data


class Overlay(QWidget):
    def __init__(self, opacity, color='#b82020'):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.answer = ''
        self.status = ''
        self.opacity = opacity
        self.color = QColor(color)
        self.anchor = None
        self.resize(330, 55)

    def show_answer(self):
        if not self.answer:
            return
        screen = QApplication.screenAt(self.anchor) if self.anchor else QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        self.move(geo.x() + (geo.width()-self.width())//2,
                  geo.y() + int(geo.height()*.78))
        self.show()
        # Exclude from screen capture where supported; capture also hides it.
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
        except (OSError, AttributeError):
            pass
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setOpacity(self.opacity)
        painter.setPen(self.color)
        painter.setFont(QFont('Arial', 18, QFont.Weight.DemiBold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                         self.answer + ('  …' if self.status == 'busy' else
                                        '  !' if self.status == 'error' else ''))
        painter.end()


class Signals(QObject):
    corner = pyqtSignal()
    solve = pyqtSignal()
    hold = pyqtSignal(bool)
    border_hold = pyqtSignal(bool)
    redraw = pyqtSignal()
    undo = pyqtSignal()
    cancel = pyqtSignal()
    settings = pyqtSignal()
    quit = pyqtSignal()
    toggle_reading = pyqtSignal()


class KeyRecorder(QLineEdit):
    """Capture a physical key chord instead of asking users to type a key name."""
    mouse_recorded = pyqtSignal(str)

    def __init__(self, value):
        super().__init__(value)
        self.setReadOnly(True)
        self.setPlaceholderText('Nhấp rồi bấm phím hoặc nút chuột')
        self.mouse_hook = None
        self.mouse_recorded.connect(self._record_mouse)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()
        QTimer.singleShot(100, self._arm_mouse)

    def _arm_mouse(self):
        if not self.hasFocus() or self.mouse_hook is not None:
            return
        self.mouse_hook = MouseHook(self._mouse_event)
        try:
            self.mouse_hook.start()
        except RuntimeError:
            self.mouse_hook = None

    def _mouse_event(self, button, pressed, modifiers):
        if not pressed:
            return False
        order = ('ctrl', 'alt', 'shift', 'windows')
        value = '+'.join([part for part in order if part in modifiers] + [button])
        self.mouse_recorded.emit(value)
        return True

    def _record_mouse(self, value):
        self.setText(value)
        QTimer.singleShot(150, self._stop_mouse)

    def _stop_mouse(self):
        if self.mouse_hook:
            self.mouse_hook.stop()
            self.mouse_hook = None

    def focusOutEvent(self, event):
        self._stop_mouse()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.isAutoRepeat() or event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt,
                Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            return
        aliases = {Qt.Key.Key_QuoteLeft: 'grave', Qt.Key.Key_Backslash: 'backslash',
                   Qt.Key.Key_Escape: 'esc', Qt.Key.Key_Return: 'enter',
                   Qt.Key.Key_Enter: 'enter', Qt.Key.Key_Backspace: 'backspace'}
        key = aliases.get(Qt.Key(event.key()))
        if key is None:
            key = QKeySequence(event.key()).toString().lower()
        modifiers = []
        for flag, label in ((Qt.KeyboardModifier.ControlModifier, 'ctrl'),
                            (Qt.KeyboardModifier.AltModifier, 'alt'),
                            (Qt.KeyboardModifier.ShiftModifier, 'shift'),
                            (Qt.KeyboardModifier.MetaModifier, 'windows')):
            if event.modifiers() & flag:
                modifiers.append(label)
        self.setText('+'.join(modifiers + [key]))
        self._stop_mouse()


class SettingsDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.validated_values = None
        self.setWindowTitle('Web MCQ Fast — Cài đặt')
        self.corner = KeyRecorder(settings['corner_key'])
        self.solve = KeyRecorder(settings['solve_key'])
        self.redraw_key = KeyRecorder(settings['redraw_key'])
        self.toggle_reading_key = KeyRecorder(settings['toggle_reading_key'])
        self.undo_key = KeyRecorder(settings['undo_key'])
        self.cancel_key = KeyRecorder(settings['cancel_key'])
        self.settings_key = KeyRecorder(settings['settings_key'])
        self.quit_key = KeyRecorder(settings['quit_key'])
        self.restart_key = KeyRecorder(settings['restart_key'])
        self.show_key = KeyRecorder(settings['show_key'])
        self.border_key = KeyRecorder(settings.get('border_key', 'f8'))
        self.opacity = QLineEdit(str(settings['opacity']))
        self.border_opacity = QLineEdit(str(settings.get('border_opacity', .85)))
        self.answer_color = QLineEdit(settings.get('answer_color', '#b82020'))
        self.border_color = QLineEdit(settings.get('border_color', '#00b4b9'))
        self.answer_mode = QComboBox()
        self.answer_mode.addItem('Giữ phím để hiện', 'hold')
        self.answer_mode.addItem('Luôn hiện sau khi giải', 'always')
        self.answer_mode.addItem('Luôn ẩn chữ nổi', 'never')
        self.answer_mode.setCurrentIndex(max(0, self.answer_mode.findData(settings.get('answer_mode', 'hold'))))
        self.border_mode = QComboBox()
        self.border_mode.addItem('Chỉ khi mở cửa sổ kiểm thử', 'test_only')
        self.border_mode.addItem('Giữ phím để hiện', 'hold')
        self.border_mode.addItem('Luôn hiện', 'always')
        self.border_mode.addItem('Luôn ẩn', 'never')
        self.border_mode.setCurrentIndex(max(0, self.border_mode.findData(settings.get('border_mode', 'test_only'))))
        self.reading_mode = QComboBox()
        self.reading_mode.addItem('Tự đọc cả vùng', 'auto')
        self.reading_mode.addItem('Vẽ từng ô Đề / A–H', 'manual')
        self.reading_mode.setCurrentIndex(max(0, self.reading_mode.findData(settings.get('reading_mode', 'auto'))))
        self.selection_mode = QComboBox()
        for name, label in [('auto', 'Tự nhận một / nhiều'), ('single', 'Một đáp án'),
                            ('multi', 'Nhiều đáp án')]:
            self.selection_mode.addItem(label, name)
        self.selection_mode.setCurrentIndex(max(0, self.selection_mode.findData(settings['mode'])))
        self.status_dot = QCheckBox('Hiện chấm trạng thái ở góc dưới phải')
        self.status_dot.setChecked(settings.get('status_dot_visible', True))
        self.option_count = QSpinBox()
        self.option_count.setRange(2, 8)
        self.option_count.setValue(settings['expected_options'])
        self.startup = QCheckBox('Tự mở khi đăng nhập Windows')
        self.startup.setChecked(settings['startup'])
        form = QFormLayout(self)
        form.addRow('Phím chọn góc:', self.corner)
        form.addRow('Phím giải:', self.solve)
        form.addRow('Phím vẽ lại bộ ô:', self.redraw_key)
        form.addRow('Phím đổi chế độ đọc:', self.toggle_reading_key)
        form.addRow('Phím hoàn tác khi vẽ:', self.undo_key)
        form.addRow('Phím hủy khi vẽ:', self.cancel_key)
        form.addRow('Phím mở Cài đặt:', self.settings_key)
        form.addRow('Phím thoát:', self.quit_key)
        form.addRow('Phím bật lại (Ctrl+Alt+chữ/số):', self.restart_key)
        form.addRow('Chế độ đọc ảnh:', self.reading_mode)
        form.addRow('Chế độ chọn đáp án:', self.selection_mode)
        form.addRow('Cách hiện đáp án:', self.answer_mode)
        form.addRow('Phím giữ đáp án:', self.show_key)
        form.addRow('Màu đáp án:', self.color_row(self.answer_color))
        form.addRow('Độ mờ đáp án (0.1–1):', self.opacity)
        form.addRow('Cách hiện khung:', self.border_mode)
        form.addRow('Phím giữ khung:', self.border_key)
        form.addRow('Màu khung:', self.color_row(self.border_color))
        form.addRow('Độ mờ khung (0.1–1):', self.border_opacity)
        form.addRow('Số phương án (2–8):', self.option_count)
        form.addRow(self.status_dot)
        legend = QLabel('Chấm: xám nạp model · xanh dương chờ vùng · xanh ngọc OCR · '
                        'tím sẵn sàng · cam đang giải · xanh lá xong · '
                        'vàng cần giải lại · đỏ lỗi')
        legend.setWordWrap(True)
        form.addRow(legend)
        form.addRow(self.startup)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def color_row(self, field):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field)
        button = QPushButton('Chọn…')
        button.clicked.connect(lambda: self.pick_color(field))
        layout.addWidget(button)
        return row

    def pick_color(self, field):
        color = QColorDialog.getColor(QColor(field.text()), self, 'Chọn màu')
        if color.isValid():
            field.setText(color.name())

    def accept(self):
        try:
            self.validated_values = self.values()
        except (ValueError, KeyError) as error:
            QMessageBox.warning(self, 'Cài đặt chưa hợp lệ', str(error))
            return
        super().accept()

    def done(self, result):
        for recorder in self.findChildren(KeyRecorder):
            recorder._stop_mouse()
        super().done(result)

    def values(self):
        import keyboard
        names = ('corner_key', 'solve_key', 'redraw_key', 'toggle_reading_key',
                 'undo_key', 'cancel_key', 'settings_key', 'quit_key',
                 'restart_key', 'show_key', 'border_key')
        fields = (self.corner, self.solve, self.redraw_key, self.toggle_reading_key,
                  self.undo_key, self.cancel_key, self.settings_key, self.quit_key,
                  self.restart_key, self.show_key, self.border_key)
        keys = dict(zip(names, (field.text().strip().lower() for field in fields)))
        parsed = []
        for value in keys.values():
            mouse = mouse_chord(value)
            if mouse:
                if mouse[1] in {'mouse_left', 'mouse_right'} and not mouse[0]:
                    raise ValueError('Chuột trái/phải cần thêm Ctrl, Alt hoặc Shift để không khóa thao tác chuột.')
                parsed.append(('mouse', tuple(sorted(mouse[0])), mouse[1]))
            elif 'mouse_' in value:
                raise ValueError('Nút chuột không hợp lệ; hãy nhấp vào ô rồi bấm nút muốn dùng.')
            else:
                parsed.append(('key', repr(keyboard.parse_hotkey(value))))
        if len(set(parsed)) != len(keys):
            raise ValueError('Các phím chức năng không được trùng nhau.')
        if not re.fullmatch(r'ctrl\+alt\+[a-z0-9]', keys['restart_key']):
            raise ValueError('Phím bật lại cần Ctrl+Alt+chữ hoặc số; Windows giữ phím này khi app đã thoát.')
        chords = [set(key.split('+')) for key in keys.values()]
        for i, first in enumerate(chords):
            if any(first < other or other < first for other in chords[i+1:]):
                raise ValueError('Hai phím tắt đang chồng nhau; hãy chọn tổ hợp khác.')
        show, border_key = keys['show_key'], keys['border_key']
        if '+' in show or '+' in border_key:
            raise ValueError('Phím giữ đáp án và khung phải là một phím đơn.')
        for hold_key in (show, border_key):
            if not mouse_chord(hold_key):
                keyboard.key_to_scan_codes(hold_key)
        opacity = float(self.opacity.text().strip())
        border_opacity = float(self.border_opacity.text().strip())
        if not (.1 <= opacity <= 1 and .1 <= border_opacity <= 1):
            raise ValueError('Độ mờ phải từ 0.1 đến 1.')
        answer_color = QColor(self.answer_color.text().strip())
        border_color = QColor(self.border_color.text().strip())
        if not answer_color.isValid() or not border_color.isValid():
            raise ValueError('Màu phải là mã hợp lệ, ví dụ #b82020.')
        return {**keys,
                'opacity': opacity, 'border_opacity': border_opacity,
                'answer_color': answer_color.name(), 'border_color': border_color.name(),
                'answer_mode': self.answer_mode.currentData(),
                'border_mode': self.border_mode.currentData(),
                'reading_mode': self.reading_mode.currentData(),
                'mode': self.selection_mode.currentData(),
                'status_dot_visible': self.status_dot.isChecked(),
                'startup': self.startup.isChecked(),
                'expected_options': self.option_count.value()}


class TrayApp(QObject):
    STATE_LABELS = {
        'loading': 'Đang nạp model',
        'waiting': 'Chờ chọn vùng hoặc ảnh mới',
        'ocr': 'Đang đọc chữ OCR',
        'ready': 'OCR xong; bấm phím giải',
        'solving': 'Đang giải câu hỏi',
        'done': 'Đã có đáp án',
        'recapture': 'Ảnh đã đổi; bấm phím giải lại',
        'error': 'Có lỗi; xem cửa sổ kiểm thử hoặc log',
    }

    def __init__(self, app, visible_test=False, visible_switch=None):
        super().__init__()
        self.app = app
        self.settings = load_ui_settings()
        if (self.settings.get('manual_regions') and
                self.settings.get('manual_display') != display_signature()):
            self.settings['manual_regions'] = None
        self.overlay = Overlay(self.settings['opacity'], self.settings['answer_color'])
        self.debug_panel = DebugPanel()
        self.debug_panel.set_answer_color(self.settings['answer_color'])
        self.capture_border = CaptureBorder()
        self.capture_border.configure(self.settings['border_color'], self.settings['border_opacity'])
        self.extra_borders = [CaptureBorder() for _ in range(8)]
        self.status_dot = StatusDot()
        self.debug_panel.closed.connect(lambda: self.set_debug_mode(False))
        self.visible_switch = visible_switch
        self.signals = Signals()
        self.signals.corner.connect(self.corner)
        self.signals.solve.connect(self.solve)
        self.signals.hold.connect(self.hold)
        self.signals.border_hold.connect(self.border_hold)
        self.signals.redraw.connect(self.start_redraw)
        self.signals.undo.connect(self.undo_redraw)
        self.signals.cancel.connect(self.cancel_redraw)
        self.signals.settings.connect(self.open_settings)
        self.signals.quit.connect(self.quit)
        self.signals.toggle_reading.connect(self.toggle_reading_mode)
        self.first_corner = None
        self.draft_regions = []
        self.redraw_active = False
        self.held = False
        self.border_held = False
        self.editing = False
        self.needs_resolve = False
        self.solve_pending = False
        self.status_state = 'loading'
        self.hooks = []
        self.mouse_hook = None
        self.mouse_bindings = {}
        self.mouse_held = {}
        self.latest_signature = None
        self.latest_image = None
        self.changed_at = 0
        self.last_display_check = 0
        self.prefetched_signature = None
        self.log_path = ROOT / 'logs' / 'fast-v2.jsonl'
        self.log_path.parent.mkdir(exist_ok=True)
        self.solver = ExamSolver()
        self.solver.settings['expected_options'] = self.settings['expected_options']
        self.engine = PrefetchEngine(self.solver)
        self.set_status('loading')
        self.update_border_visibility()
        try:
            self.bind_keys()
        except Exception as error:
            self.notify('Không gắn được phím: ' + str(error))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        if visible_test:
            self.set_debug_mode(True, persist=False)
        if self.settings['startup']:
            try:
                set_startup(True)
            except Exception as error:
                self.notify('Không đặt được tự khởi động: ' + str(error))
        try:
            set_restart_shortcut(self.settings['restart_key'])
        except Exception as error:
            self.notify('Không đặt được phím bật lại: ' + str(error))

    def record(self, item):
        item['at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        with self.log_path.open('a', encoding='utf-8') as out:
            out.write(json.dumps(item, ensure_ascii=False) + '\n')

    def notify(self, message, state='error'):
        self.set_status(state, message)
        self.record({'event': 'notice', 'message': message})
        if self.debug_panel.isVisible():
            self.debug_panel.set_stage(message)

    def set_debug_mode(self, enabled, persist=True):
        if persist:
            self.settings['debug_mode'] = enabled
            save_ui_settings(self.settings)
        if enabled:
            region = self.active_region()
            self.debug_panel.show_region(region)
            self.debug_panel.show()
            self.debug_panel.raise_()
        else:
            self.debug_panel.hide()
        self.update_border_visibility()

    def set_status(self, state, detail=None):
        self.status_state = state
        self.status_dot.set_state(state, self.active_region())
        if self.settings.get('status_dot_visible', True):
            if not self.status_dot.isVisible():
                self.status_dot.show()
        elif self.status_dot.isVisible():
            self.status_dot.hide()
        if detail and self.debug_panel.isVisible():
            self.debug_panel.set_stage(detail)

    def active_regions(self):
        if self.redraw_active:
            return self.draft_regions
        if self.settings.get('reading_mode') == 'manual':
            return self.settings.get('manual_regions') or []
        return [self.settings['region']] if self.settings.get('region') else []

    def active_region(self):
        regions = self.active_regions()
        return regions[0] if regions else self.settings.get('region')

    def update_border_visibility(self):
        mode = self.settings.get('border_mode', 'test_only')
        visible = (mode == 'always' or
                   mode == 'test_only' and self.debug_panel.isVisible() or
                   mode == 'hold' and self.border_held)
        regions = self.active_regions() if visible else []
        for widget, region in zip([self.capture_border] + self.extra_borders,
                                  regions + [None] * (9 - len(regions))):
            widget.set_region(region) if region else widget.hide()

    def update_answer_visibility(self):
        mode = self.settings.get('answer_mode', 'hold')
        if self.overlay.answer and (mode == 'always' or mode == 'hold' and self.held):
            self.overlay.show_answer()
        else:
            self.overlay.hide()

    def bind_keys(self):
        import keyboard
        self.unbind_keys()
        try:
            self._bind_action('corner_key', self.signals.corner)
            self._bind_action('solve_key', self.signals.solve)
            for name, signal in (('redraw_key', self.signals.redraw),
                                 ('toggle_reading_key', self.signals.toggle_reading),
                                 ('settings_key', self.signals.settings),
                                 ('quit_key', self.signals.quit)):
                self._bind_action(name, signal)
            if self.redraw_active:
                self.bind_redraw_keys()
            if self.settings.get('answer_mode', 'hold') == 'hold':
                self._bind_hold('show_key', self.signals.hold)
            if self.settings.get('border_mode', 'test_only') == 'hold':
                self._bind_hold('border_key', self.signals.border_hold)
            if self.mouse_bindings:
                self.mouse_hook = MouseHook(self._mouse_event)
                self.mouse_hook.start()
        except Exception:
            self.unbind_keys()
            raise

    def _bind_action(self, name, signal):
        value = self.settings[name]
        if mouse_chord(value):
            self.mouse_bindings[value] = ('action', signal)
        else:
            import keyboard
            self.hooks.append(('hotkey', keyboard.add_hotkey(value,
                lambda target=signal: target.emit(), suppress=True)))

    def _bind_hold(self, name, signal):
        value = self.settings[name]
        if mouse_chord(value):
            self.mouse_bindings[value] = ('hold', signal)
        else:
            import keyboard
            self.hooks.append(('hook', keyboard.on_press_key(value,
                lambda event, target=signal: target.emit(True), suppress=True)))
            self.hooks.append(('hook', keyboard.on_release_key(value,
                lambda event, target=signal: target.emit(False), suppress=True)))

    def _mouse_event(self, button, pressed, modifiers):
        if not pressed:
            signal = self.mouse_held.pop(button, None)
            if signal:
                signal.emit(False)
                return True
            return False
        for setting, (kind, signal) in self.mouse_bindings.items():
            if mouse_chord(setting) == (modifiers, button):
                if kind == 'hold':
                    self.mouse_held[button] = signal
                    signal.emit(True)
                else:
                    signal.emit()
                return True
        return False

    def bind_redraw_keys(self):
        for name, signal in (('undo_key', self.signals.undo),
                             ('cancel_key', self.signals.cancel)):
            self._bind_action(name, signal)

    def unbind_keys(self):
        import keyboard
        if self.mouse_hook:
            self.mouse_hook.stop()
            self.mouse_hook = None
        self.mouse_bindings.clear()
        self.mouse_held.clear()
        for kind, handle in self.hooks:
            try:
                (keyboard.remove_hotkey if kind == 'hotkey' else keyboard.unhook)(handle)
            except (KeyError, ValueError):
                pass
        self.hooks.clear()

    def corner(self):
        if self.editing:
            return
        if self.settings.get('reading_mode') == 'manual' and not self.redraw_active:
            self.notify('Chế độ Vẽ từng ô: bấm phím vẽ lại trước.', state='waiting')
            return
        point = current_cursor()
        if self.first_corner is None:
            self.first_corner = point
            self.set_status('waiting', 'Góc 1 đã chọn; bấm phím chọn góc ở góc 2')
            if self.debug_panel.isVisible():
                self.debug_panel.set_stage(f'Góc 1: {point}. Di chuột đến góc đối diện rồi bấm ` lần nữa.')
            return
        try:
            region = region_from_corners(self.first_corner, point,
                                         40 if self.redraw_active else 80,
                                         20 if self.redraw_active else 50)
        except ValueError as error:
            self.notify(str(error))
            return
        self.first_corner = None
        if self.redraw_active:
            self.draft_regions.append(region)
            count = self.settings['expected_options'] + 1
            if len(self.draft_regions) == count:
                self.settings['manual_regions'] = list(self.draft_regions)
                self.settings['manual_display'] = display_signature()
                self.settings['reading_mode'] = 'manual'
                self.redraw_active = False
                self.draft_regions = []
                save_ui_settings(self.settings)
                self.bind_keys()
                self.engine.invalidate()
                self.latest_signature = None
                self.prefetched_signature = None
                self.needs_resolve = True
                self.set_status('waiting', 'Đã lưu đủ bộ ô; đang OCR câu hiện tại.')
            else:
                next_label = 'Đề' if not self.draft_regions else chr(64 + len(self.draft_regions))
                self.set_status('waiting', f'Đã lưu ô {len(self.draft_regions)}/{count}; vẽ ô {next_label}.')
            self.update_border_visibility()
            if self.debug_panel.isVisible():
                self.debug_panel.show_region(self.active_region())
            return
        self.settings['region'] = region
        save_ui_settings(self.settings)
        self.solve_pending = False
        self.needs_resolve = True
        self.engine.invalidate()
        self.latest_signature = None
        self.prefetched_signature = None
        # Qt cursor positions are in display coordinates; capture coordinates are physical.
        self.overlay.anchor = QCursor.pos()
        self.set_status('waiting', 'Đã chọn vùng; đang chuẩn bị OCR')
        self.update_border_visibility()
        if self.debug_panel.isVisible():
            self.debug_panel.show_region(region)
            self.debug_panel.set_stage('Đã chọn vùng. Đang chờ ảnh ổn định để OCR…')
            self.debug_panel.ocr.clear()

    def start_redraw(self):
        if self.editing:
            return
        self.redraw_active = True
        self.first_corner = None
        self.draft_regions = []
        self.engine.invalidate()
        self.latest_signature = None
        self.prefetched_signature = None
        self.solve_pending = False
        self.bind_keys()
        self.set_status('waiting', 'Vẽ ô Đề: đưa chuột tới hai góc và bấm phím chọn góc.')
        self.update_border_visibility()

    def undo_redraw(self):
        if not self.redraw_active:
            return
        if self.first_corner is not None:
            self.first_corner = None
        elif self.draft_regions:
            self.draft_regions.pop()
        target = 'Đề' if not self.draft_regions else chr(64 + len(self.draft_regions))
        self.set_status('waiting', f'Đã hoàn tác; vẽ ô {target}.')
        self.update_border_visibility()

    def cancel_redraw(self):
        if not self.redraw_active:
            return
        self.redraw_active = False
        self.first_corner = None
        self.draft_regions = []
        self.bind_keys()
        self.set_status('waiting', 'Đã hủy vẽ lại; bộ ô trước vẫn được giữ.')
        self.update_border_visibility()

    def toggle_reading_mode(self):
        if self.editing:
            return
        if self.redraw_active:
            self.cancel_redraw()
        target = 'manual' if self.settings.get('reading_mode') == 'auto' else 'auto'
        self.settings['reading_mode'] = target
        self.engine.invalidate()
        self.latest_signature = None
        self.latest_image = None
        self.prefetched_signature = None
        self.solve_pending = False
        self.needs_resolve = True
        self.overlay.status = ''
        self.overlay.update()
        save_ui_settings(self.settings)
        self.update_border_visibility()
        if target == 'manual':
            if len(self.settings.get('manual_regions') or []) != self.settings['expected_options'] + 1:
                self.set_status('waiting', 'Vẽ từng ô: chưa có đủ bộ ô; bấm phím vẽ lại.')
            else:
                self.set_status('waiting', 'Đã chuyển sang Vẽ từng ô; đang đọc ảnh mới.')
        else:
            self.set_status('waiting', 'Đã chuyển sang Tự đọc cả vùng.' if self.settings.get('region')
                            else 'Tự đọc: hãy chọn lại hai góc vùng câu hỏi.')
        if self.debug_panel.isVisible():
            self.debug_panel.show_region(self.active_region())

    def capture(self):
        from PIL import ImageGrab
        regions = self.active_regions()
        if not regions or self.redraw_active:
            return None
        visible = self.overlay.isVisible()
        panel_visible = self.debug_panel.isVisible()
        left = min(region[0] for region in regions)
        top = min(region[1] for region in regions)
        right = max(region[2] for region in regions)
        bottom = max(region[3] for region in regions)
        capture_rect = region_to_qrect((left, top, right, bottom))
        dot_hidden = (self.status_dot.isVisible() and
                      not self.status_dot.capture_excluded and
                      self.status_dot.geometry().intersects(capture_rect))
        visible_borders = [border for border in [self.capture_border] + self.extra_borders
                           if border.isVisible()]
        if visible:
            self.overlay.hide()
        if panel_visible:
            self.debug_panel.hide()
        if dot_hidden:
            self.status_dot.hide()
        for border in visible_borders:
            border.hide()
        try:
            if self.settings.get('reading_mode') == 'manual':
                image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
                crops = tuple(image.crop((r[0]-left, r[1]-top, r[2]-left, r[3]-top))
                              for r in regions)
                return ManualCapture(tuple(tuple(r) for r in regions), crops)
            return ImageGrab.grab(bbox=tuple(regions[0]), all_screens=True)
        finally:
            if dot_hidden and self.settings.get('status_dot_visible', True):
                self.status_dot.show()
            if panel_visible:
                self.debug_panel.show()
            if visible:
                self.update_answer_visibility()
            self.update_border_visibility()

    def solve(self):
        if self.editing:
            return
        if self.redraw_active:
            self.notify('Đang vẽ bộ ô mới; hoàn tất hoặc hủy lượt vẽ trước.', state='waiting')
            return
        if not self.active_regions() or (self.settings.get('reading_mode') == 'manual' and
            len(self.active_regions()) != self.settings['expected_options'] + 1):
            self.notify('Chưa có đủ vùng chụp; hãy chọn vùng hoặc vẽ lại bộ ô.', state='waiting')
            return
        try:
            image = self.capture()
            signature = image_signature(image)
            self.engine.submit(image, signature, time.perf_counter(), solve=True,
                               mode=self.settings['mode'])
            self.latest_signature = signature
            self.prefetched_signature = signature
            self.needs_resolve = False
            self.solve_pending = True
            self.set_status('solving')
            self.overlay.status = 'busy'
            self.overlay.update()
            if self.debug_panel.isVisible():
                self.debug_panel.show_capture(image)
                self.debug_panel.set_stage('Đã chụp ảnh. Đang chờ OCR / model…')
        except Exception as error:
            self.notify('Không chụp được vùng: ' + str(error))

    def hold(self, visible):
        if self.editing:
            return
        self.held = visible
        self.update_answer_visibility()

    def border_hold(self, visible):
        if self.editing:
            return
        self.border_held = visible
        self.update_border_visibility()

    def tick(self):
        now_display = time.monotonic()
        if now_display - self.last_display_check > 2:
            self.last_display_check = now_display
            if (self.settings.get('manual_regions') and
                    self.settings.get('manual_display') != display_signature()):
                self.settings['manual_regions'] = None
                self.engine.invalidate()
                self.latest_signature = None
                self.prefetched_signature = None
                self.set_status('error', 'Màn hình hoặc DPI đã đổi; hãy vẽ lại bộ ô.')
                self.update_border_visibility()
        if self.visible_switch is not None and ctypes.windll.kernel32.WaitForSingleObject(self.visible_switch, 0) == 0:
            self.set_debug_mode(True, persist=False)
        while not self.engine.events.empty():
            event = self.engine.events.get_nowait()
            if event['type'] == 'ready':
                self.record({'event': 'model_ready', **event, **system_snapshot()})
                if self.status_state == 'loading':
                    self.set_status('waiting')
                if self.debug_panel.isVisible():
                    self.debug_panel.set_stage(f'Model đã nạp ({event["model_load_seconds"]:.2f} giây). Chờ câu hỏi…')
            elif event['type'] == 'warm_error':
                self.notify('Model chưa nạp: ' + event['error'])
            elif event['type'] in ('ocr_started', 'ocr_ready', 'solve_started'):
                if event['sequence'] != self.engine.sequence:
                    continue
                if event['type'] == 'ocr_started':
                    self.set_status('ocr')
                    if self.debug_panel.isVisible():
                        self.debug_panel.set_stage('Đang nhận diện chữ (OCR)…')
                elif event['type'] == 'ocr_ready':
                    self.record({'event': 'ocr_ready', **event})
                    self.set_status('error' if event.get('error') else
                                    'solving' if self.solve_pending else
                                    'recapture' if self.needs_resolve else 'ready')
                    if self.debug_panel.isVisible():
                        self.debug_panel.ocr.setPlainText('\n'.join(event['lines']) if event['lines'] else
                                                          event.get('error', 'Không đọc được chữ.'))
                        self.debug_panel.sections.setPlainText('\n\n'.join(event.get('lines', [])))
                        suffix = ' · đã đọc lại chất lượng cao' if event['reread'] else ''
                        parts = event.get('section_ocr_seconds')
                        if parts:
                            suffix += ' · từng ô: ' + ', '.join(f'{x:.2f}s' for x in parts)
                        if event.get('weak_layout'):
                            suffix += ' · ranh giới cần kiểm tra'
                        self.debug_panel.set_stage(f'OCR xong ({event["ocr_seconds"]:.2f} giây){suffix}.')
                else:
                    self.set_status('solving')
                    if self.debug_panel.isVisible():
                        self.debug_panel.set_stage('AI đang suy luận, có thể chờ GPU nguội…')
            elif event['type'] == 'result':
                if event['sequence'] != self.engine.sequence or self.redraw_active:
                    continue
                result = event['result']
                try:
                    current = self.capture()
                    if image_signature(current) != self.engine.signature:
                        self.engine.submit(current, image_signature(current), time.perf_counter())
                        self.latest_signature = image_signature(current)
                        self.prefetched_signature = self.latest_signature
                        self.solve_pending = False
                        self.needs_resolve = True
                        self.set_status('recapture')
                        if self.debug_panel.isVisible():
                            self.debug_panel.set_stage('Ảnh đã đổi trong lúc giải. Đang OCR ảnh mới; bấm Ctrl+Enter lại.')
                        continue
                except Exception:
                    self.engine.invalidate()
                    self.solve_pending = False
                    self.needs_resolve = True
                    self.set_status('recapture')
                    self.notify('Vùng chụp đã thay đổi; hãy giải lại câu hiện tại.', state='recapture')
                    continue
                if 'best_choice' in result:
                    self.solve_pending = False
                    self.needs_resolve = False
                    self.overlay.answer = result['best_choice']
                    self.overlay.status = ''
                    copied = self.solver.copy_to_clipboard(result['best_choice'])
                    copied_at = time.perf_counter()
                    if not copied:
                        self.notify('Có đáp án nhưng không copy được Clipboard.')
                    self.set_status('done' if copied else 'error')
                    self.overlay.update()
                    self.update_answer_visibility()
                    machine = system_snapshot()
                    key_to_clipboard = (round(copied_at - event['entered_at'], 3)
                                        if copied and event.get('entered_at') else None)
                    self.record({'event': 'result', **event, **machine,
                                 'key_to_clipboard_seconds': key_to_clipboard})
                    if self.debug_panel.isVisible():
                        self.debug_panel.answer.setText('Đáp án: ' + result['best_choice'])
                        self.debug_panel.source.setText('Slide: ' + result.get('matched_source', '—'))
                        breakdown = (f'OCR: {result.get("ocr_seconds", 0):.2f}s · '
                                     f'AI: {result.get("inference_seconds", 0):.2f}s · '
                                     f'Chờ nhiệt: {result.get("cooling_seconds", 0):.2f}s')
                        if 'gpu_temperature_c' in machine:
                            breakdown += f' · GPU: {machine["gpu_temperature_c"]:.0f}°C'
                        self.debug_panel.timing.setText(
                            f'Ảnh → đáp án: {event["image_to_answer_seconds"]:.2f}s · '
                            f'Phím giải → AI: {event["enter_to_answer_seconds"]:.2f}s'
                            + (f' · → Clipboard: {key_to_clipboard:.2f}s' if key_to_clipboard is not None else '')
                            + '\n'
                            + breakdown)
                        self.debug_panel.set_stage('Hoàn tất. ' +
                            ('Đã copy đáp án.' if copied else 'Clipboard đang bị khóa.'))
                        if result.get('weak_layout'):
                            self.debug_panel.set_stage('Cần kiểm tra: ranh giới phương án được suy từ dòng/lề.')
                else:
                    self.record({'event': 'result', **event, **system_snapshot()})
                    self.solve_pending = False
                    self.overlay.status = 'error'
                    self.overlay.update()
                    if self.debug_panel.isVisible():
                        self.debug_panel.answer.setText('Đáp án trước: ' + (self.overlay.answer or '—'))
                    self.notify(result.get('error', 'Không giải được câu này.'))
        if not self.active_regions() or self.editing or self.redraw_active:
            return
        try:
            image = self.capture()
            signature = image_signature(image)
        except Exception as error:
            self.record({'event': 'capture_error', 'message': str(error)})
            self.set_status('error', 'Không chụp được vùng: ' + str(error))
            return
        now = time.perf_counter()
        if signature != self.latest_signature:
            if self.overlay.answer or self.solve_pending:
                self.needs_resolve = True
                self.solve_pending = False
            self.latest_signature = signature
            self.latest_image = image
            self.changed_at = now
            self.set_status('ocr')
            if self.debug_panel.isVisible():
                self.debug_panel.show_capture(image)
                self.debug_panel.set_stage('Ảnh mới trong vùng chụp. Chuẩn bị OCR…', record=False)
        if self.latest_image is not None and self.prefetched_signature != signature and now-self.changed_at >= .45:
            self.engine.submit(self.latest_image, signature, self.changed_at)
            self.prefetched_signature = signature

    def set_mode(self, mode):
        self.settings['mode'] = mode
        save_ui_settings(self.settings)

    def open_settings(self):
        if self.editing:
            return
        if self.redraw_active:
            self.cancel_redraw()
        self.editing = True
        self.unbind_keys()
        self.held = False
        self.border_held = False
        self.overlay.hide()
        self.update_border_visibility()
        dialog = SettingsDialog(self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            old = dict(self.settings)
            try:
                values = dialog.validated_values or dialog.values()
                self.settings.update(values)
                self.solver.settings['expected_options'] = self.settings['expected_options']
                if (old['expected_options'] != self.settings['expected_options'] or
                    old.get('reading_mode') != self.settings['reading_mode'] or
                    old.get('mode') != self.settings['mode']):
                    self.engine.invalidate()
                    self.prefetched_signature = None
                    self.latest_signature = None
                if (self.settings['reading_mode'] == 'manual' and
                    len(self.settings.get('manual_regions') or []) != self.settings['expected_options'] + 1):
                    self.settings['manual_regions'] = None
                    self.set_status('waiting', 'Bộ ô không phù hợp số phương án; hãy vẽ lại.')
                self.overlay.opacity = self.settings['opacity']
                self.overlay.color = QColor(self.settings['answer_color'])
                self.bind_keys()
                set_startup(self.settings['startup'])
                set_restart_shortcut(self.settings['restart_key'])
                save_ui_settings(self.settings)
                self.held = False
                self.border_held = False
                self.capture_border.configure(self.settings['border_color'],
                                              self.settings['border_opacity'])
                self.debug_panel.set_answer_color(self.settings['answer_color'])
                self.update_border_visibility()
                self.set_status(self.status_state)
            except Exception as error:
                self.settings = old
                self.solver.settings['expected_options'] = self.settings['expected_options']
                self.overlay.opacity = self.settings['opacity']
                self.overlay.color = QColor(self.settings['answer_color'])
                self.capture_border.configure(self.settings['border_color'],
                                              self.settings['border_opacity'])
                self.debug_panel.set_answer_color(self.settings['answer_color'])
                self.bind_keys()
                try:
                    set_startup(self.settings['startup'])
                    set_restart_shortcut(self.settings['restart_key'])
                except Exception:
                    pass
                self.update_border_visibility()
                self.set_status(self.status_state)
                self.notify('Cài đặt không hợp lệ: ' + str(error))
        else:
            self.bind_keys()
        self.editing = False
        self.update_answer_visibility()

    def quit(self):
        self.timer.stop()
        self.unbind_keys()
        self.engine.close()
        self.solver.close()
        self.debug_panel.hide()
        self.capture_border.hide()
        for border in self.extra_borders:
            border.hide()
        self.status_dot.hide()
        self.app.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install-startup', action='store_true')
    parser.add_argument('--remove-startup', action='store_true')
    parser.add_argument('--self-test-ocr', action='store_true')
    parser.add_argument('--visible-test', action='store_true')
    args = parser.parse_args()
    if args.install_startup or args.remove_startup:
        set_startup(args.install_startup)
        return 0
    if args.self_test_ocr:
        from PIL import Image
        from src.question_parser import parse_question
        target = ROOT / 'artifacts/package-ocr-smoke.json'
        target.parent.mkdir(exist_ok=True)
        try:
            solver = ExamSolver()
            with Image.open(ROOT.parent / 'tests/assets/html-lists.png') as image:
                prepared = solver.prepare_image(image)
                question = prepared.get('structured') or parse_question(prepared['lines'], 4)
                passed = not question.errors and set(question.options) == set('ABCD')
            with Image.open(ROOT / 'tests/assets/badge-labels-identifier.png') as image:
                badge_prepared = solver.prepare_image(image)
                badge_question = badge_prepared.get('structured') or parse_question(badge_prepared['lines'], 4)
                badge_passed = (not badge_question.errors and badge_question.options ==
                                {'A': '$price', 'B': '_total', 'C': '2students', 'D': 'userName'})
                regions = ((0, 0, 840, 42), (15, 50, 827, 102), (15, 112, 827, 164),
                           (15, 174, 827, 226), (15, 236, 827, 288))
                manual = solver.prepare_image(ManualCapture(regions,
                    tuple(image.crop(region) for region in regions)))
                manual_passed = not manual['structured'].errors and manual['structured'].options == badge_question.options
            solver.close()
            target.write_text(json.dumps({'passed': passed and badge_passed and manual_passed,
                'legacy': {'passed': passed, 'lines': prepared['lines'],
                           'ocr_seconds': prepared['ocr_seconds'], 'errors': question.errors},
                'badge_layout': {'passed': badge_passed, 'lines': badge_prepared['lines'],
                                 'options': badge_question.options,
                                 'ocr_seconds': badge_prepared['ocr_seconds'],
                                 'errors': badge_question.errors},
                'manual_regions': {'passed': manual_passed,
                                   'ocr_seconds': manual['ocr_seconds'],
                                   'section_ocr_seconds': manual['section_ocr_seconds'],
                                   'options': manual['structured'].options}},
                ensure_ascii=False, indent=2), encoding='utf-8')
            return 0 if passed and badge_passed and manual_passed else 1
        except Exception as error:
            target.write_text(json.dumps({'passed': False, 'error': str(error)},
                ensure_ascii=False, indent=2), encoding='utf-8')
            return 1
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    visible_switch = kernel.CreateEventW(None, False, False, 'Local\\WebMCQFastV2Visible')
    mutex = kernel.CreateMutexW(None, False, 'Local\\WebMCQFastV2')
    if kernel.GetLastError() == 183:
        if args.visible_test:
            kernel.SetEvent(visible_switch)
        kernel.CloseHandle(mutex)
        kernel.CloseHandle(visible_switch)
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = TrayApp(app, visible_test=args.visible_test, visible_switch=visible_switch)
    try:
        return app.exec()
    finally:
        controller.quit()
        kernel.CloseHandle(mutex)
        kernel.CloseHandle(visible_switch)


if __name__ == '__main__':
    raise SystemExit(main())
