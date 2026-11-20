import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
from x import get
L = get(sys.argv[1]); tgt = int(sys.argv[2], 16)
img = L.img[0]; b = L.objs[0]['base']
for p in range(len(img) - 5):
    if img[p] in (0xe8, 0xe9):
        r = struct.unpack_from('<i', img, p + 1)[0]
        if b + p + 5 + r == tgt: print(hex(b + p), 'call' if img[p] == 0xe8 else 'jmp')
