"""Small Windows low-level mouse hook for configurable X1/X2 and other buttons."""
import ctypes
from ctypes import wintypes
import threading


BUTTONS = ('mouse_left', 'mouse_right', 'mouse_middle', 'mouse_x1', 'mouse_x2')
_DOWN = {0x0201: 'mouse_left', 0x0204: 'mouse_right', 0x0207: 'mouse_middle',
         0x020B: 'mouse_x'}
_UP = {0x0202: 'mouse_left', 0x0205: 'mouse_right', 0x0208: 'mouse_middle',
       0x020C: 'mouse_x'}


class _MouseData(ctypes.Structure):
    _fields_ = [('pt', wintypes.POINT), ('mouseData', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


def mouse_chord(value):
    """Return (modifiers, mouse button) for a setting, or None."""
    parts = value.lower().split('+')
    if not parts or parts[-1] not in BUTTONS or any(
            part not in {'ctrl', 'alt', 'shift', 'windows'} for part in parts[:-1]):
        return None
    if len(set(parts)) != len(parts):
        return None
    return frozenset(parts[:-1]), parts[-1]


def current_modifiers():
    user = ctypes.windll.user32
    codes = ((0x11, 'ctrl'), (0x12, 'alt'), (0x10, 'shift'),
             (0x5B, 'windows'), (0x5C, 'windows'))
    return frozenset(name for vk, name in codes if user.GetAsyncKeyState(vk) & 0x8000)


class MouseHook:
    """Dispatch presses/releases on a dedicated message-loop thread.

    callback(button, pressed, modifiers) returns True to suppress the native
    mouse event. A matched down is also suppressed on release.
    """
    def __init__(self, callback, protected_buttons=()):
        self.callback = callback
        self.protected_buttons = frozenset(protected_buttons)
        self.thread = None
        self.thread_id = None
        self.hook = None
        self._proc = None
        self._ready = threading.Event()
        self._error = None
        self._consumed = set()

    def dispatch(self, button, pressed, modifiers):
        if pressed:
            try:
                consumed = bool(self.callback(button, True, modifiers))
            except Exception:
                # A Qt signal or logging failure must not leak an assigned
                # XBUTTON through to browser Back/Forward.
                if button not in self.protected_buttons:
                    raise
                consumed = True
            if consumed:
                self._consumed.add(button)
            return consumed
        was_consumed = button in self._consumed
        self._consumed.discard(button)
        try:
            return bool(self.callback(button, False, modifiers)) or was_consumed
        except Exception:
            if button not in self.protected_buttons:
                raise
            return True

    def is_running(self):
        return bool(self.thread and self.thread.is_alive() and self.hook)

    def start(self):
        if self.thread is not None:
            return
        self._ready.clear()
        self.thread = threading.Thread(target=self._run, name='v2-mouse-hotkeys', daemon=True)
        self.thread.start()
        if not self._ready.wait(3):
            raise RuntimeError('Không khởi động được bộ nhận phím chuột.')
        if self._error:
            raise RuntimeError('Không gắn được nút chuột: ' + self._error)

    def _run(self):
        user = ctypes.windll.user32
        kernel = ctypes.windll.kernel32
        CALLBACK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                      wintypes.WPARAM, wintypes.LPARAM)
        user.SetWindowsHookExW.argtypes = [ctypes.c_int, CALLBACK, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HHOOK
        user.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                        wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user.UnhookWindowsHookEx.restype = wintypes.BOOL
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                     wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = wintypes.BOOL
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE

        def handler(code, message, pointer):
            if code >= 0 and message in _DOWN | _UP:
                try:
                    data = ctypes.cast(pointer, ctypes.POINTER(_MouseData)).contents
                    button = (_DOWN | _UP)[message]
                    if button == 'mouse_x':
                        button = 'mouse_x1' if data.mouseData >> 16 == 1 else 'mouse_x2'
                    pressed = message in _DOWN
                    if self.dispatch(button, pressed, current_modifiers()):
                        return 1
                except Exception:
                    pass
            return user.CallNextHookEx(self.hook, code, message, pointer)

        self._proc = CALLBACK(handler)
        self.thread_id = kernel.GetCurrentThreadId()
        self.hook = user.SetWindowsHookExW(14, self._proc, kernel.GetModuleHandleW(None), 0)
        if not self.hook:
            self._error = str(ctypes.get_last_error() or kernel.GetLastError())
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            pass
        user.UnhookWindowsHookEx(self.hook)
        self.hook = None
        self.thread_id = None

    def stop(self):
        if self.thread is None:
            return
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        self.thread.join(timeout=2)
        if not self.thread.is_alive():
            self.thread = None
            self._proc = None
        self._consumed.clear()
