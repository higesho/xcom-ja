# テスト用: Interceptor を窓（cnc-ddraw）で起動し、プロセスの窓だけを相手に撮影・操作する（前面の窓は使わない）
#   python tools/win.py start [jp|en]    ddraw.dll/ddraw.ini（テスト用）と build/winmm.dll をゲームのフォルダに置いて起動
#   python tools/win.py shot NAME         PrintWindow で capture/NAME.png
#   python tools/win.py click X Y [right] ゲームの座標（640x480）で押す（DLL のテスト機能が DirectInput に入れる）
#   python tools/win.py key NAME..        キー（DLL のテスト機能）
#   python tools/win.py stop              終了して、置いたファイルを消す
import sys, os, time, ctypes, ctypes.wintypes as W, subprocess, shutil, struct
from ctypes import windll
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GAME = os.path.abspath(os.path.join(ROOT, '..'))
PIDF = os.path.join(ROOT, 'test', 'pid.txt')
u32 = windll.user32; g32 = windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
PLACED = ['ddraw.dll', 'ddraw.ini', 'winmm.dll']

def find_window(pid=None):
    if pid is None: pid = int(open(PIDF).read())
    found = []
    def cb(h, l):
        p = W.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            n = u32.GetWindowTextLengthW(h); b = ctypes.create_unicode_buffer(n + 1); u32.GetWindowTextW(h, b, n + 1)
            r = W.RECT(); u32.GetClientRect(h, ctypes.byref(r))
            found.append((r.right * r.bottom, h, b.value))
        return True
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found: raise SystemExit('window of pid %d not found' % pid)
    found.sort(reverse=True)
    return found[0][1], found[0][2]

def shot(name):
    from PIL import Image
    h, t = find_window()
    r = W.RECT(); u32.GetClientRect(h, ctypes.byref(r)); w, hh = r.right, r.bottom
    hdc = u32.GetDC(h); mdc = g32.CreateCompatibleDC(hdc); bm = g32.CreateCompatibleBitmap(hdc, w, hh)
    g32.SelectObject(mdc, bm)
    u32.PrintWindow(h, mdc, 3)   # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    class BIH(ctypes.Structure):
        _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD),
                    ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('a', W.LONG), ('b', W.LONG), ('c', W.DWORD), ('d', W.DWORD)]
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = w; bi.biHeight = -hh; bi.biPlanes = 1; bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * hh * 4)
    g32.GetDIBits(mdc, bm, 0, hh, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bm); g32.DeleteDC(mdc); u32.ReleaseDC(h, hdc)
    im = Image.frombuffer('RGBA', (w, hh), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
    out = os.path.join(ROOT, 'capture', name + '.png'); im.save(out); print(out, im.size, t)

def _shm():
    import mmap
    m = mmap.mmap(-1, 64, tagname='XI_TESTIO')
    if struct.unpack_from('<I', m, 0)[0] != 0x54534554: raise SystemExit('test DLL not running')
    return m

def send(m, t, a=0, b=0, c=0):
    struct.pack_into('<4i', m, 12, t, a, b, c)
    r = struct.unpack_from('<i', m, 4)[0] + 1; struct.pack_into('<i', m, 4, r)
    t0 = time.time()
    while struct.unpack_from('<i', m, 8)[0] != r:
        if time.time() - t0 > 5: raise SystemExit('event timeout')
        time.sleep(0.01)

# DirectInput のキーの番号（DIK）
DIK = {'esc': 1, 'enter': 0x1c, 'space': 0x39, 'tab': 0x0f, 'back': 0x0e, 'up': 0xc8, 'down': 0xd0, 'left': 0xcb, 'right': 0xcd,
       'f1': 0x3b, 'f2': 0x3c, 'f3': 0x3d, 'f4': 0x3e, 'f5': 0x3f, 'f6': 0x40, 'f7': 0x41, 'f8': 0x42, 'f9': 0x43, 'f10': 0x44}
for i, ch in enumerate('1234567890'): DIK[ch] = 2 + i
for row, base in (('qwertyuiop', 0x10), ('asdfghjkl', 0x1e), ('zxcvbnm', 0x2c)):
    for i, ch in enumerate(row): DIK[ch] = base + i

def start(variant):
    for f in PLACED:
        p = os.path.join(GAME, f)
        if os.path.exists(p): os.remove(p)
    shutil.copy(os.path.join(ROOT, 'test', 'ddraw.dll'), GAME); shutil.copy(os.path.join(ROOT, 'test', 'ddraw.ini'), GAME)
    if variant != 'none' and os.path.exists(os.path.join(ROOT, 'build', 'winmm.dll')): shutil.copy(os.path.join(ROOT, 'build', 'winmm.dll'), GAME)
    env = dict(os.environ); env['XI_TEST'] = '1'; env.setdefault('XI_LOG', '1')
    if variant == 'en': env['XI_NOJP'] = '1'
    p = subprocess.Popen([os.path.join(GAME, 'Interceptor.exe')], cwd=GAME, env=env)
    open(PIDF, 'w').write(str(p.pid))
    for i in range(60):
        time.sleep(0.5)
        try:
            h, t = find_window(p.pid); print('pid', p.pid, 'window', repr(t)); return
        except SystemExit: pass
    print('pid', p.pid, 'no window yet')

def stop():
    try: subprocess.call(['taskkill', '/PID', open(PIDF).read().strip(), '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e: print(e)
    time.sleep(1.5)
    for f in PLACED:
        p = os.path.join(GAME, f)
        if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'start': start(sys.argv[2] if len(sys.argv) > 2 else 'jp')
    elif c == 'shot': shot(sys.argv[2])
    elif c == 'stop': stop()
    elif c == 'click':
        m = _shm(); b = 1 if 'right' in sys.argv[4:] else 0
        send(m, 4, int(sys.argv[2]), int(sys.argv[3])); time.sleep(0.15)
        send(m, 5, b, 1); time.sleep(0.15); send(m, 5, b, 0); time.sleep(0.1)
    elif c == 'move':
        m = _shm(); send(m, 4, int(sys.argv[2]), int(sys.argv[3]))
    elif c == 'key':
        m = _shm()
        for n in sys.argv[2:]:
            if n.startswith('wait:'): time.sleep(float(n[5:])); continue
            send(m, 2, DIK[n.lower()], 1); time.sleep(0.12); send(m, 2, DIK[n.lower()], 0); time.sleep(0.1)
