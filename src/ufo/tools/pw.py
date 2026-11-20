# 固有の窓の題名（XCOMJP-TEST <pid>）で窓を探し、PrintWindow で撮る
import sys, os, ctypes, ctypes.wintypes as W
from ctypes import windll
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import win
h, t = win.find_window()
r = W.RECT(); windll.user32.GetClientRect(h, ctypes.byref(r)); w, hh = r.right, r.bottom
hdc = windll.user32.GetDC(h); mdc = windll.gdi32.CreateCompatibleDC(hdc)
bmp = windll.gdi32.CreateCompatibleBitmap(hdc, w, hh); windll.gdi32.SelectObject(mdc, bmp)
windll.user32.PrintWindow(h, mdc, 3)
class BI(ctypes.Structure):
    _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD), ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('a', W.LONG), ('b', W.LONG), ('c', W.DWORD), ('d', W.DWORD)]
bi = BI(); bi.biSize = 40; bi.biWidth = w; bi.biHeight = -hh; bi.biPlanes = 1; bi.biBitCount = 32
buf = ctypes.create_string_buffer(w * hh * 4)
windll.gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bi), 0)
im = Image.frombuffer('RGBA', (w, hh), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
out = os.path.join(win.ROOT, 'capture', sys.argv[1] + '.png'); im.save(out); print(out, t)
