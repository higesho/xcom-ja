# ENGLISH.DAT の番号 n の文字列を参照する所を逆アセンブルで見る: python tools/strref.py geo 192 [前の命令数] [後の命令数]
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from x import get
k = sys.argv[1]; n = int(sys.argv[2]); pre = int(sys.argv[3]) if len(sys.argv) > 3 else 6; post = int(sys.argv[4]) if len(sys.argv) > 4 else 14
L = get(k)
tab = 0x6a974 if k == 'geo' else None
if tab is None:
    raise SystemExit('tac: give table')
v = tab + (n + 1) * 4
img = L.img[0]
for p in range(len(img) - 4):
    if struct.unpack_from('<I', img, p)[0] == v:
        r = 0x10000 + p
        print('== ref', hex(r))
        print(L.dis(r - 3 - pre * 4, pre + post))
