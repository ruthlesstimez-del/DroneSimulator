"""Small transparent, click-through reticle; no simulator image captures."""
import ctypes
from ctypes import wintypes
import tkinter as tk

from view_input import cursor_aim


def main():
    root = tk.Tk()
    root.withdraw()
    root.title('Drone aim reticle')
    root.overrideredirect(True)
    root.configure(bg='black')
    root.attributes('-transparentcolor', 'black')
    root.attributes('-topmost', True)
    canvas = tk.Canvas(root, width=64, height=64, bg='black', highlightthickness=0)
    canvas.pack()
    for coordinates in ((12, 32, 25, 32), (39, 32, 52, 32), (32, 12, 32, 25), (32, 39, 32, 52)):
        canvas.create_line(*coordinates, fill='white', width=3)
        canvas.create_line(*coordinates, fill='#53ffb0', width=1)
    canvas.create_oval(29, 29, 35, 35, outline='#53ffb0', width=1)
    root.update_idletasks()
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    window = user32.GetParent(root.winfo_id()) or root.winfo_id()
    style = user32.GetWindowLongW(window, -20)
    # Transparent to clicks, a tool window, and never takes keyboard focus.
    user32.SetWindowLongW(window, -20, style | 0x20 | 0x80 | 0x80000 | 0x08000000)

    def update():
        aim = cursor_aim()
        if aim:
            root.geometry(f'64x64{aim[2]-32:+d}{aim[3]-32:+d}')
            root.deiconify()
        else:
            root.withdraw()
        root.after(16, update)

    update()
    root.mainloop()


if __name__ == '__main__':
    main()
