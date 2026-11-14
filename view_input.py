"""Windows client-area coordinates shared by mouse aiming and its overlay."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


def cursor_aim():
    window = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(window, title, len(title))
    if not title.value.startswith(('CityEnviron', 'Blocks', 'AbandonedPark')):
        return None
    rect, origin, cursor = wintypes.RECT(), wintypes.POINT(), wintypes.POINT()
    if not user32.GetClientRect(window, ctypes.byref(rect)):
        return None
    user32.ClientToScreen(window, ctypes.byref(origin))
    user32.GetCursorPos(ctypes.byref(cursor))
    width, height = rect.right, rect.bottom
    x, y = cursor.x - origin.x, cursor.y - origin.y
    if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
        return None
    return x / width, y / height, cursor.x, cursor.y
