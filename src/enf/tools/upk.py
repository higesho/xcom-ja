# Unreal Engine 1 のパッケージ（.u / .utx / .xcm）を読む
#   名前の表・インポート・エクスポートと、エクスポートの中身のバイト列
import struct, sys

def ci(b, p):
    """圧縮された整数（compact index）を読む → (値, 次の位置)"""
    x = b[p]; p += 1
    neg = x & 0x80; v = x & 0x3f
    if x & 0x40:
        sh = 6
        while True:
            y = b[p]; p += 1
            v |= (y & 0x7f) << sh; sh += 7
            if not (y & 0x80): break
    return (-v if neg else v), p

def ci_bytes(v):
    neg = v < 0; v = abs(v)
    out = [(0x80 if neg else 0) | (v & 0x3f) | (0x40 if v >= 0x40 else 0)]
    v >>= 6
    while v:
        out.append((v & 0x7f) | (0x80 if v >= 0x80 else 0)); v >>= 7
    return bytes(out)

def fstring(b, p):
    n, p = ci(b, p)
    if n == 0: return '', p
    if n > 0:
        s = b[p:p + n].decode('latin-1'); p += n
    else:
        s = b[p:p - n * 2].decode('utf-16-le'); p += -n * 2
    return s.rstrip('\x00'), p

class Pkg:
    def __init__(self, path):
        self.path = path
        b = self.b = open(path, 'rb').read()
        tag, self.ver, self.lic, self.flags, nc, no, ec, eo, ic, io = struct.unpack_from('<IHHIIIIIII', b, 0)
        assert tag == 0x9E2A83C1, 'not a package'
        self.names = []
        p = no
        for i in range(nc):
            if self.ver >= 64:
                s, p = fstring(b, p)
            else:
                e = b.index(b'\0', p); s = b[p:e].decode('latin-1'); p = e + 1
            self.names.append(s); p += 4
        self.imports = []
        p = io
        for i in range(ic):
            cp, p = ci(b, p); cn, p = ci(b, p); pk = struct.unpack_from('<i', b, p)[0]; p += 4; on, p = ci(b, p)
            self.imports.append((self.names[cp], self.names[cn], pk, self.names[on]))
        self.exports = []
        p = eo
        for i in range(ec):
            cl, p = ci(b, p); su, p = ci(b, p); pk = struct.unpack_from('<i', b, p)[0]; p += 4
            on, p = ci(b, p); fl = struct.unpack_from('<I', b, p)[0]; p += 4
            sz, p = ci(b, p); off = 0
            if sz > 0: off, p = ci(b, p)
            self.exports.append(dict(cls=cl, sup=su, pkg=pk, name=self.names[on], flags=fl, size=sz, off=off, idx=i))
    def obj_name(self, ref):
        if ref == 0: return None
        if ref < 0: return self.imports[-ref - 1][3]
        return self.exports[ref - 1]['name']
    def cls_name(self, e):
        return self.obj_name(e['cls']) or 'Class'
    def data(self, e):
        return self.b[e['off']:e['off'] + e['size']]
    def full_name(self, e):
        parts = [e['name']]; pk = e['pkg']
        while pk > 0:
            o = self.exports[pk - 1]; parts.append(o['name']); pk = o['pkg']
        return '.'.join(reversed(parts))

if __name__ == '__main__':
    k = Pkg(sys.argv[1])
    print('ver', k.ver, 'names', len(k.names), 'imports', len(k.imports), 'exports', len(k.exports))
    from collections import Counter
    print(Counter(k.cls_name(e) for e in k.exports).most_common(25))
