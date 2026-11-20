# UFO の関数を、絶対番地と call の飛び先を伏せた型にして、別の EXE で探す
import sys, re, os
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
UFO = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'XCom UFO Defense', '_jp', 'orig')
def mask(L, va, n):
    b = bytearray(L.read(va, n)); m = [True] * n
    o0 = L.objs[0]['base']
    fx = {off + L.objs[oi]['base'] for oi, off, st, to, tgt in L.fix if oi == 0}
    for i in range(n):
        if va + i in fx:
            for k in range(4):
                if i + k < n: m[i + k] = False
    # call/jmp rel32
    for ins in L.md.disasm(bytes(b), va):
        if ins.bytes[0] in (0xe8, 0xe9) and ins.size == 5:
            p = ins.address - va
            for k in range(1, 5):
                if p + k < n: m[p + k] = False
    return b, m
def pattern(b, m):
    return b''.join(re.escape(bytes([c])) if k else b'.' for c, k in zip(b, m))
def search(L, b, m):
    pat = re.compile(pattern(b, m), re.S)
    return [x.start() + L.objs[0]['base'] for x in pat.finditer(L.img[0])]
if __name__ == '__main__':
    U = LE(os.path.join(UFO, sys.argv[1]))
    T = LE(sys.argv[2])
    for a in sys.argv[3:]:
        a = int(a, 16)
        for n in (64, 48, 32, 24, 16):
            b, m = mask(U, a, n)
            h = search(T, b, m)
            if h: print(hex(a), n, [hex(x) for x in h]); break
        else: print(hex(a), 'none')
