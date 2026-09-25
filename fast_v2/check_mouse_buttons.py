"""Visible, model-free check for what the physical side buttons send to Windows."""
import sys

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from src.mouse_hotkeys import MouseHook


NAV_KEYS = {'tab', 'left', 'right', 'page up', 'page down',
            'browser back', 'browser forward', 'back', 'forward'}


class Events(QObject):
    mouse = pyqtSignal(str)
    keyboard = pyqtSignal(str)


class MouseCheck(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Kiểm tra nút hông chuột — không chạy OCR/model')
        self.resize(470, 230)
        self.events = Events(self)
        self.events.mouse.connect(self.show_mouse)
        self.events.keyboard.connect(self.show_keyboard)
        self.mouse_hook = MouseHook(self.on_mouse,
                                    protected_buttons={'mouse_x1', 'mouse_x2'})
        self.keyboard_hook = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Bấm lần lượt hai nút hông khi cửa sổ này đang mở.'))
        layout.addWidget(QLabel('Không mở trang bài tập để thử; cửa sổ này chặn X1/X2.'))
        self.mouse_result = QLabel('XBUTTON: chưa nhận')
        self.keyboard_result = QLabel('Phím điều hướng: chưa nhận')
        self.verdict = QLabel('Nếu chỉ thấy phím điều hướng, phần mềm chuột đã đổi nút hông thành phím.')
        self.verdict.setWordWrap(True)
        layout.addWidget(self.mouse_result)
        layout.addWidget(self.keyboard_result)
        layout.addWidget(self.verdict)
        close = QPushButton('Đóng')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.mouse_seen = set()
        self.keyboard_seen = []
        try:
            self.mouse_hook.start()
            import keyboard
            self.keyboard_hook = keyboard.hook(self.on_keyboard, suppress=False)
        except Exception as error:
            self.verdict.setText('Không gắn được bộ kiểm tra: ' + str(error))

    def on_mouse(self, button, pressed, modifiers):
        if pressed and button in {'mouse_x1', 'mouse_x2'}:
            self.events.mouse.emit(button)
            return True
        return button in {'mouse_x1', 'mouse_x2'}

    def on_keyboard(self, event):
        if event.event_type == 'down' and event.name in NAV_KEYS:
            import keyboard
            modifiers = [name for name in ('ctrl', 'alt', 'shift')
                         if keyboard.is_pressed(name)]
            self.events.keyboard.emit('+'.join(modifiers + [event.name]))

    def show_mouse(self, button):
        self.mouse_seen.add(button)
        self.mouse_result.setText('XBUTTON: ' + ', '.join(sorted(self.mouse_seen)))
        self.update_verdict()

    def show_keyboard(self, chord):
        self.keyboard_seen.append(chord)
        self.keyboard_result.setText('Phím điều hướng: ' + chord)
        self.update_verdict()

    def update_verdict(self):
        if self.mouse_seen and self.keyboard_seen:
            self.verdict.setText('Nút hông gửi cả XBUTTON và phím điều hướng. Chặn '
                                 'XBUTTON chưa đủ; hãy đổi cấu hình trong phần mềm chuột.')
        elif self.mouse_seen:
            self.verdict.setText('Đã nhận XBUTTON. V2 có thể chặn nút này trước trình duyệt. '
                                 'Nếu Brave vẫn chuyển trang, hãy báo cả hai dòng kết quả.')
        elif self.keyboard_seen:
            self.verdict.setText('Chưa nhận XBUTTON. Có thể nút hông đang được đổi thành '
                                 'phím điều hướng; hãy gán đúng tổ hợp này trong V2 hoặc '
                                 'đổi cấu hình ở phần mềm chuột.')

    def closeEvent(self, event):
        if self.keyboard_hook is not None:
            import keyboard
            keyboard.unhook(self.keyboard_hook)
            self.keyboard_hook = None
        self.mouse_hook.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MouseCheck()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
