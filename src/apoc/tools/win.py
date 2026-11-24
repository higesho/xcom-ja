# Drive the test DOSBox window by its own process / unique title (never the foreground window).
#   python tools/win.py start [trace|jp|none]   launch DOSBox (DLL variant copied as winmm.dll)
#   python tools/win.py shot NAME               PrintWindow capture -> capture/NAME.png
#   python tools/win.py key KEY [KEY..]         post keys (names: enter esc space up down left right f1.. a..z 0..9, or 'text:HELLO')
#   python tools/win.py click X Y [right]       click at game coords (320x200)
#   python tools/win.py dclick X Y              double-click (opens a character sheet from a portrait)
#   python tools/win.py title | stop
import sys, os, time, ctypes, ctypes.wintypes as W, subprocess, shutil, struct
from ctypes import windll
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GAME = os.path.abspath(os.path.join(ROOT, '..'))
PIDF = os.path.join(ROOT, 'test', 'pid.txt')
u32 = windll.user32; g32 = windll.gdi32

WNDENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

def find_window(pid=None):
    if pid is None:
        pid = int(open(PIDF).read())
    found = []
    def cb(h, l):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            n = u32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, b, n + 1)
            if b.value.startswith('XCOMJP-TEST %d ' % pid):
                found.append((h, b.value))
        return True
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found:
        raise SystemExit('DOSBox window of pid %d not found' % pid)
    return found[0]

def client_size(h):
    if u32.IsIconic(h):
        u32.ShowWindow(h, 4)      # SW_SHOWNOACTIVATE: restore without stealing focus
        time.sleep(0.5)
    r = W.RECT()
    u32.GetClientRect(h, ctypes.byref(r))
    return r.right, r.bottom

def shot(name):
    # the DLL (XC_TEST=1) writes the SDL screen surface to a BMP; the window itself may not paint
    import mmap
    from PIL import Image
    m = mmap.mmap(-1, 16 + 260 + 40, tagname='XC_TESTIO')
    if struct.unpack_from('<I', m, 0)[0] != 0x54534554: raise SystemExit('test DLL not running')
    bmp = os.path.join(ROOT, 'test', 'shot.bmp')
    if os.path.exists(bmp): os.remove(bmp)
    p = bmp.encode('mbcs') + bytes(1); m[16:16 + len(p)] = p
    req = struct.unpack_from('<i', m, 4)[0] + 1; struct.pack_into('<i', m, 4, req)
    t = time.time()
    while struct.unpack_from('<i', m, 8)[0] != req:
        if time.time() - t > 10: raise SystemExit('shot timeout')
        time.sleep(0.05)
    im = Image.open(bmp).convert('RGB')
    out = os.path.join(ROOT, 'capture', name + '.png')
    im.save(out)
    print(out)

# キーは DLL のテスト機能（XC_TEST=1）が SDL_PushEvent で DOSBox に入れる（ウインドウを前面に出さない）
# 名前 -> (SDL の sym, PC のスキャンコード)
VK = {'enter': (13, 0x1c), 'esc': (27, 0x01), 'space': (32, 0x39), 'tab': (9, 0x0f), 'back': (8, 0x0e),
      'up': (273, 0x48), 'down': (274, 0x50), 'right': (275, 0x4d), 'left': (276, 0x4b),
      'home': (278, 0x47), 'end': (279, 0x4f), 'pgup': (280, 0x49), 'pgdn': (281, 0x51),
      'minus': (45, 0x0c), 'period': (46, 0x34), 'slash': (47, 0x35)}
for i in range(1, 13):
    VK['f%d' % i] = (281 + i, 0x3a + i if i <= 10 else 0x57 + i - 11)
for i in range(10):
    VK['kp%d' % i] = (256 + i, [0x52, 0x4f, 0x50, 0x51, 0x4b, 0x4c, 0x4d, 0x47, 0x48, 0x49][i])
ROWS = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']
SC0 = [0x02, 0x10, 0x1e, 0x2c]
for r, s0 in zip(ROWS, SC0):
    for k, ch in enumerate(r):
        VK[ch] = (ord(ch), s0 + k)


def _shm():
    import mmap
    m = mmap.mmap(-1, 16 + 260 + 40, tagname='XC_TESTIO')
    if struct.unpack_from('<I', m, 0)[0] != 0x54534554: raise SystemExit('test DLL not running')
    return m


def send_ev(m, t, a=0, b=0, c=0):
    struct.pack_into('<4i', m, 284, t, a, b, c)
    r = struct.unpack_from('<i', m, 276)[0] + 1
    struct.pack_into('<i', m, 276, r)
    t0 = time.time()
    while struct.unpack_from('<i', m, 280)[0] != r:
        if time.time() - t0 > 5: raise SystemExit('event timeout')
        time.sleep(0.01)


def post_key(m, name, hold=0.3):
    sym, sc = VK[name]
    send_ev(m, 2, sym, sc)
    time.sleep(hold)
    send_ev(m, 3, sym, sc)
    time.sleep(0.1)


def key(names):
    m = _shm()
    for n in names:
        if n.startswith('text:'):
            for ch in n[5:]:
                post_key(m, 'space' if ch == ' ' else ch.lower(), 0.12)
        elif n.startswith('wait:'):
            time.sleep(float(n[5:]))
        else:
            post_key(m, n.lower())


def click(x, y, right=False, double=False, maxx=639, maxy=479, fb=False):
    # ゲームの座標（320x200）で押す。DOSBox はマウスを窓の位置の割合 × ゲームが決めた範囲の最大値で決めるので、
    # その最大値（maxx は 640 幅の単位）で割り戻す。手番のカードのように範囲を絞る画面では maxx, maxy を渡す
    m = _shm()
    X, Y = int(round(x * 639 / maxx)), int(round(y * 479 / maxy))      # アポカリプスは 640x480 のまま
    # アポカリプスは絶対位置で動く。左上へ寄せると地図がスクロールするので寄せない
    g0 = struct.unpack_from('<2i', m, 300)
    send_ev(m, 4, 0, X, Y); time.sleep(0.2)
    # ゲームが読んだマウスの位置（DLL が書く）を見て合わせる（窓ごとにマウスの範囲が変わるため）。
    # その変数を使わない画面（左上へ動かしても値が変わらない）では合わせない
    for it in range(12 if fb else 0):
        gx, gy, ok = struct.unpack_from('<3i', m, 300)
        if not ok or (abs(gx - x) <= 1 and abs(gy - y) <= 1): break
        X = max(0, min(639, X + int(round((x - gx)))))
        Y = max(0, min(479, Y + int(round((y - gy)))))
        send_ev(m, 4, 0, X, Y); time.sleep(0.2)
    b = 3 if right else 1
    for k in range(2 if double else 1):
        send_ev(m, 5, b, X, Y); time.sleep(0.35)
        send_ev(m, 6, b, X, Y); time.sleep(0.12)


def start(variant):
    # variant: jp（日本語）/ en（同じ DLL で英語のまま。XC_NOJP=1）。どちらもテスト機能（XC_TEST=1）付き
    dst = os.path.join(GAME, 'winmm.dll')
    if os.path.exists(dst): os.remove(dst)
    shutil.copy(os.path.join(ROOT, 'build', 'test', 'winmm.dll'), dst)
    env = dict(os.environ); env["XC_TEST"] = "1"; env.setdefault("XC_LOG", "1")
    if variant == 'en': env["XC_NOJP"] = "1"
    exe = os.path.join(GAME, 'dosbox.exe')
    p = subprocess.Popen([exe, '-noconsole', '-conf', os.path.join('_jp', 'test', os.environ.get('XC_CONF', 'test.conf'))], cwd=GAME, env=env)
    open(PIDF, 'w').write(str(p.pid))
    for i in range(50):
        time.sleep(0.2)
        try:
            h, t = find_window(p.pid)
            print('pid', p.pid, 'window', t)
            return
        except SystemExit:
            pass
    print('pid', p.pid, 'window not found yet')

def stop():
    try:
        pid = int(open(PIDF).read())
        subprocess.call(['taskkill', '/PID', str(pid), '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(e)
    time.sleep(1)
    dst = os.path.join(GAME, 'winmm.dll')
    if os.path.exists(dst): os.remove(dst)

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'start': start(sys.argv[2] if len(sys.argv) > 2 else 'jp')
    elif c == 'shot': shot(sys.argv[2])
    elif c == 'key': key(sys.argv[2:])
    elif c == 'click':
        nums = [int(a) for a in sys.argv[4:] if a.lstrip('-').isdigit()]
        click(int(sys.argv[2]), int(sys.argv[3]), 'right' in sys.argv[4:], False, *(nums[:2] if len(nums) >= 2 else []))
    elif c == 'fclick':     # 窓がマウスの範囲を絞る画面用: ゲームの読んだ位置を見て合わせる
        click(int(sys.argv[2]), int(sys.argv[3]), 'right' in sys.argv[4:], fb=True)
    elif c == 'dclick': click(int(sys.argv[2]), int(sys.argv[3]), double=True)
    elif c == 'rmove':
        m = _shm(); send_ev(m, 7, 0, int(sys.argv[2]), int(sys.argv[3]))
    elif c == 'press':      # 今のカーソルの位置でボタンを押す（right で右）
        m = _shm(); b = 3 if 'right' in sys.argv[2:] else 1
        send_ev(m, 5, b, 0, 0); time.sleep(0.15); send_ev(m, 6, b, 0, 0)
    elif c == 'snap':       # DOSBox の Ctrl+F5（原寸 320x200 の PNG）を撮り、release/img/NAME.png に移す
        import glob
        cap = os.path.join(GAME, 'capture')
        before = set(glob.glob(os.path.join(cap, '*.png')))
        m = _shm()
        send_ev(m, 2, 306, 0x1d); time.sleep(0.2); send_ev(m, 2, 286, 0x3f); time.sleep(0.2)
        send_ev(m, 3, 286, 0x3f); time.sleep(0.1); send_ev(m, 3, 306, 0x1d)
        for i in range(30):
            time.sleep(0.2)
            new = set(glob.glob(os.path.join(cap, '*.png'))) - before
            if new: break
        if not new: raise SystemExit('no capture')
        time.sleep(0.3)
        out = os.path.join(ROOT, 'release', 'img', sys.argv[2] + '.png')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.move(new.pop(), out); print(out)
    elif c == 'title': print(find_window())
    elif c == 'stop': stop()
