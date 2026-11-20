# fixup の参照先にある、表示用らしい文字列を集める
import sys, os, re, json
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
def strings(L):
    out = {}
    o1 = L.objs[1]; img = L.img[1]
    for k, (oi, off, st, to, tgt) in enumerate(L.fix):
        if to != 1 or off < 0: continue
        if tgt >= o1['vsize']: continue
        e = img.find(b'\x00', tgt)
        s = bytes(img[tgt:e])
        if len(s) < 2 or len(s) > 2000: continue
        if any(c < 0x20 and c not in (10, 13, 9) for c in s) or any(c > 0x7e for c in s): continue
        if not re.search(rb'[A-Za-z]{2}', s): continue
        out.setdefault(tgt, []).append((oi, off))
    return out
if __name__ == '__main__':
    L = LE(sys.argv[1])
    st = strings(L)
    img = L.img[1]
    tot = 0
    for t in sorted(st):
        s = bytes(img[t:img.find(b'\x00', t)]); tot += len(s)
    print(len(st), tot)
