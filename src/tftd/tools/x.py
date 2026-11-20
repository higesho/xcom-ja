# helpers: python tools/x.py geo|tac  ... loaded as module
import sys, os, struct, re
sys.path.insert(0, os.path.dirname(__file__))
from le import LE, va_of_file
X = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'XCOM'))
EXES = {'geo': X + '/UFOEXE/GEOSCAPE.EXE', 'tac': X + '/UFO2EXE/TACTICAL.EXE', 'intro': X + '/INTRO.EXE'}
_c = {}
def get(k):
    if k not in _c: _c[k] = LE(EXES[k])
    return _c[k]
def find_str(L, s):
    out = []
    for i, img in enumerate(L.img):
        for m in re.finditer(re.escape(s), img): out.append(L.objs[i]['base'] + m.start())
    return out
def refs(L, va):
    pat = struct.pack('<I', va); out = []
    img = L.img[0]
    for m in re.finditer(re.escape(pat), img): out.append(L.objs[0]['base'] + m.start())
    return out
def func_start(L, va):
    # scan back for common prologue after ret/int3/padding
    img = L.img[0]; b = L.objs[0]['base']
    p = va - b
    while p > 0:
        if img[p-1] in (0xc3, 0xc2) or img[p-1:p] == b'\x00' and False: return b + p
        p -= 1
    return b
if __name__ == '__main__':
    L = get(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == 'dis': print(L.dis(int(sys.argv[3], 16), int(sys.argv[4]) if len(sys.argv) > 4 else 60))
    elif cmd == 'str':
        for va in find_str(L, sys.argv[3].encode()): print(hex(va), [hex(r) for r in refs(L, va)])
    elif cmd == 'refs':
        for r in refs(L, int(sys.argv[3], 16)): print(hex(r))
