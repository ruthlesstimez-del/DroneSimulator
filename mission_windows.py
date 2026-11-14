"""Arrange the simulator and route view so a live mission can be watched."""
import ctypes
from ctypes import wintypes


def arrange(native_view=True):
    user = ctypes.windll.user32
    user.SetProcessDPIAware()
    user.GetWindowTextW.argtypes = [wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.MoveWindow.argtypes = [wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.BOOL]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    windows = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(window, parameter):
        text = ctypes.create_unicode_buffer(512)
        user.GetWindowTextW(window,text,len(text))
        if user.IsWindowVisible(window):
            if text.value.startswith(('CityEnviron','Blocks','AbandonedPark')):
                windows['game'] = window
            elif text.value.startswith(('RL Mission Path', 'Drone Duel')):
                windows['route'] = window
        return True
    user.EnumWindows(callback_type(visit),0)
    area = wintypes.RECT()
    user.SystemParametersInfoW(0x30,0,ctypes.byref(area),0)
    width, height = area.right-area.left, area.bottom-area.top
    game_width = min(1280,int(width*.62))
    outer = wintypes.RECT(0,0,game_width,round(game_width*9/16))
    user.AdjustWindowRect(ctypes.byref(outer),0x00CF0000,False)
    game_width, game_height = outer.right-outer.left, outer.bottom-outer.top
    if 'route' in windows:
        user.MoveWindow(windows['route'],area.left+game_width+16,area.top+20,
                        max(300,width-game_width-26),min(780,height-30),True)
    if 'game' in windows:
        user.MoveWindow(windows['game'],area.left+6,area.top+20,game_width,game_height,True)
        user.SetForegroundWindow(windows['game'])
        # Select native third-person follow view, without touching flight input.
        if native_view:
            user.PostMessageW(windows['game'],0x100,ord('B'),0)
            user.PostMessageW(windows['game'],0x101,ord('B'),0)


if __name__ == '__main__':
    import sys
    arrange(native_view='--keep-view' not in sys.argv)
