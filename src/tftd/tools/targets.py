# list call targets in [lo,hi) with number of callers
import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(__file__))
from x import get
L = get(sys.argv[1]); lo = int(sys.argv[2], 16); hi = int(sys.argv[3], 16)
img = L.img[0]; b = L.objs[0]['base']; c = collections.defaultdict(list)
for p in range(len(img) - 5):
    if img[p] == 0xe8:
        t = b + p + 5 + struct.unpack_from('<i', img, p + 1)[0]
        if lo <= t < hi: c[t].append(b + p)
for t in sorted(c): print(hex(t), len(c[t]), ' '.join(hex(x) for x in c[t][:8]))
