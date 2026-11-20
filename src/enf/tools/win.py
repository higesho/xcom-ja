# テスト用: Enforcer を窓で起動し、プロセスの窓だけを相手に撮影・操作する（前面の窓は使わない）
#   python tools/win.py start [jp|en]   build/winmm.dll を System に置き、test/XCom.ini（窓モード）・test/User.ini で起動
#   python tools/win.py shot NAME       PrintWindow で capture/NAME.png
#   python tools/win.py click X Y       窓の中の座標で押す（PostMessage）
#   python tools/win.py key NAME..      キー（PostMessage。esc enter up down left right や英字）
#   python tools/win.py stop            終了して、置いたファイルを消し、System の ini・log を元に戻す
import sys, os, time, ctypes, ctypes.wintypes as W, subprocess, shutil
from ctypes import windll
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GAME = os.path.abspath(os.path.join(ROOT, '..'))
SYS = os.path.join(GAME, 'System')
PIDF = os.path.join(ROOT, 'test', 'pid.txt')
ORIG = os.path.join(ROOT, 'test', 'orig_system')
u32 = windll.user32; g32 = windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

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
    u32.PrintWindow(h, mdc, 3)
    class BIH(ctypes.Structure):
        _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD),
                    ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('a', W.LONG), ('b', W.LONG), ('c', W.DWORD), ('d', W.DWORD)]
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = w; bi.biHeight = -hh; bi.biPlanes = 1; bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * hh * 4)
    g32.GetDIBits(mdc, bm, 0, hh, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bm); g32.DeleteDC(mdc); u32.ReleaseDC(h, hdc)
    im = Image.frombuffer('RGBA', (w, hh), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
    os.makedirs(os.path.join(ROOT, 'capture'), exist_ok=True)
    out = os.path.join(ROOT, 'capture', name + '.png'); im.save(out); print(out, im.size, t)

VK = {'esc': 0x1b, 'enter': 0x0d, 'space': 0x20, 'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'tab': 0x09, 'back': 0x08,
      'f1': 0x70, 'f2': 0x71, 'f10': 0x79, 'f12': 0x7b, 'tilde': 0xc0}
def key(names):
    h, t = find_window()
    for n in names:
        if n.startswith('wait:'): time.sleep(float(n[5:])); continue
        v = VK.get(n.lower(), ord(n.upper()[0]))
        sc = windll.user32.MapVirtualKeyW(v, 0)
        u32.PostMessageW(h, 0x100, v, 1 | (sc << 16)); time.sleep(0.08)
        if len(n) == 1: u32.PostMessageW(h, 0x102, ord(n), 1 | (sc << 16))
        u32.PostMessageW(h, 0x101, v, 0xC0000001 | (sc << 16)); time.sleep(0.25)

def click(x, y):
    h, t = find_window(); lp = (y << 16) | x
    u32.PostMessageW(h, 0x200, 0, lp); time.sleep(0.15)
    u32.PostMessageW(h, 0x201, 1, lp); time.sleep(0.15); u32.PostMessageW(h, 0x202, 0, lp); time.sleep(0.2)

def start(variant):
    stop(quiet=True)
    if variant != 'none': shutil.copy(os.path.join(ROOT, 'build', 'winmm.dll'), SYS)
    open(os.path.join(SYS, 'steam_appid.txt'), 'w').write('7770')
    # テスト用の ini を毎回ゲームの ini から作り直す（窓モード。前の回が落ちていても Recovery Mode にならないように）
    t = open(os.path.join(ORIG, 'XCom.ini'), encoding='latin-1', newline='').read().replace('StartupFullscreen=True', 'StartupFullscreen=False')
    if os.environ.get('XE_D3D'): t = t.replace('WindowedRenderDevice=SoftDrv.SoftwareRenderDevice', 'WindowedRenderDevice=D3DDrv.D3DRenderDevice')
    open(os.path.join(ROOT, 'test', 'XCom.ini'), 'w', encoding='latin-1', newline='').write(t)
    shutil.copy(os.path.join(ORIG, 'User.ini'), os.path.join(ROOT, 'test', 'User.ini'))
    if os.environ.get('XE_SEED'):   # 研究の画面を見るため、任務 1 まで進んだエンフォーサーを置く
        with open(os.path.join(ROOT, 'test', 'User.ini'), 'a', encoding='latin-1', newline='') as f:
            f.write('\r\n[XMenu.NewCharacterWindow]\r\nSavedEnforcers[0]=(Name="Test",Difficulty=1,CurrMap=%s,MaxHealth=100,Speed=1.000000,Targeting=1.000000,RepairRate=1.000000,Ammo=1.000000,Jump=1.000000,ResearchPoints=5000,FinishedGame=0,XBaseSkinName="EnforcerTrooperBaseSkins.Default")\r\n' % os.environ['XE_SEED'])
    env = dict(os.environ); env['XE_LOG'] = '1'; env['XE_TEST'] = '1'
    if variant == 'en': env['XE_NOJP'] = '1'
    args = [os.path.join(SYS, 'XCom.exe')] + ([os.environ['XE_MAP']] if os.environ.get('XE_MAP') else []) + ['ini=..\\_jp\\test\\XCom.ini', 'userini=..\\_jp\\test\\User.ini', 'log=..\\_jp\\test\\run.log']
    p = subprocess.Popen(args, cwd=SYS, env=env)
    open(PIDF, 'w').write(str(p.pid))
    for i in range(60):
        time.sleep(0.5)
        try:
            h, t = find_window(p.pid); print('pid', p.pid, 'window', repr(t)); return
        except SystemExit: pass
    print('pid', p.pid, 'no window yet')

def stop(quiet=False):
    try:   # まず窓を閉じて普通に終わらせる（強制終了すると次の起動が Recovery Mode になる）
        pid = int(open(PIDF).read().strip())
        try:
            h, t = find_window(pid); u32.PostMessageW(h, 0x10, 0, 0)
            for i in range(20):
                time.sleep(0.5)
                if subprocess.call(['tasklist', '/FI', 'PID eq %d' % pid], stdout=subprocess.PIPE) == 0 and str(pid) not in subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid], capture_output=True, text=True).stdout: break
        except SystemExit: pass
        subprocess.call(['taskkill', '/PID', str(pid), '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        if not quiet: print(e)
    time.sleep(1.5)
    for f in ('winmm.dll', 'steam_appid.txt'):
        p = os.path.join(SYS, f)
        if os.path.exists(p): os.remove(p)
    # System の ini・log を元に戻す（ゲームが書き換えることがある）
    for f in os.listdir(ORIG):
        a, b = os.path.join(ORIG, f), os.path.join(SYS, f)
        if not os.path.exists(b) or open(a, 'rb').read() != open(b, 'rb').read(): shutil.copy2(a, b)

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'start': start(sys.argv[2] if len(sys.argv) > 2 else 'jp')
    elif c == 'shot': shot(sys.argv[2])
    elif c == 'stop': stop()
    elif c == 'click': click(int(sys.argv[2]), int(sys.argv[3]))
    elif c == 'key': key(sys.argv[2:])
    elif c == 'type':      # 文字を WM_CHAR で打つ（コンソールなど）
        h, t = find_window()
        for ch in ' '.join(sys.argv[2:]): u32.PostMessageW(h, 0x102, ord(ch), 1); time.sleep(0.05)
