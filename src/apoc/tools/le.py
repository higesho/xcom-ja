# Minimal LE loader for INTERP.EXE: objects laid out at BASE[i], fixups applied.
import struct, os, capstone
EXE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'XCOM', 'UFOEXE', 'GEOSCAPE.EXE'))
class LE:
    def __init__(self, fn=EXE):
        d = self.d = open(fn, 'rb').read()
        self.le = le = struct.unpack_from('<I', d, 0x3c)[0]
        self.mz = 0
        if le >= len(d) or d[le:le+2] != b'LE':      # DOS/4GW で結合された EXE: 中の MZ を探す
            import re as _re
            for m in _re.finditer(b'MZ', d[:0x100000]):
                q = m.start()
                if q and q + 0x40 < len(d):
                    l2 = q + struct.unpack_from('<I', d, q + 0x3c)[0]
                    if l2 < len(d) and d[l2:l2+4] == b'LE\x00\x00': self.mz = q; le = self.le = l2; break
        assert d[le:le+2] == b'LE', d[le:le+2]
        H = lambda o, f='<I': struct.unpack_from(f, d, le + o)[0]
        self.pagesize = H(0x28); self.lastpage = H(0x2c)
        self.npages = H(0x14)
        self.eip_obj = H(0x18); self.eip = H(0x1c); self.esp_obj = H(0x20); self.esp = H(0x24)
        objtab = le + H(0x40); nobj = H(0x44)
        pagemap = le + H(0x48)
        fixpage = le + H(0x68); fixrec = le + H(0x6c)
        pages, last = struct.unpack_from('<HH', d, 4)[0], struct.unpack_from('<H', d, 2)[0]
        self.B = (pages - 1) * 512 + last          # DOS/16M stub size: offsets in the LE are relative to the BW part
        datapages = (self.mz + H(0x80)) if self.mz else len(d) - ((self.npages - 1) * self.pagesize + self.lastpage)
        self.objs = []
        base = 0x10000
        for i in range(nobj):
            vsize, reloc, flags, pmi, pmn, _ = struct.unpack_from('<6I', d, objtab + i * 24)
            self.objs.append(dict(vsize=vsize, reloc=reloc, flags=flags, pmi=pmi, pmn=pmn, base=reloc))
        self.img = []
        self.pageoff = {}
        for i, o in enumerate(self.objs):
            buf = bytearray(o['vsize'] + 16)
            for k in range(o['pmn']):
                pn = o['pmi'] + k  # 1-based
                e = d[pagemap + (pn - 1) * 4: pagemap + pn * 4]
                num = (e[0] << 16) | (e[1] << 8) | e[2]
                off = datapages + (num - 1) * self.pagesize
                ln = self.pagesize if pn != self.npages else self.lastpage
                self.pageoff[pn] = (i, k * self.pagesize, off, ln)
                chunk = d[off:off + ln]
                buf[k * self.pagesize:k * self.pagesize + len(chunk)] = chunk
            self.img.append(buf)
        self.raw = [bytes(b) for b in self.img]
        # fixups
        self.fix = []
        self.fixpos = []          # (fixup の添字, 目標の位置フィールドのファイル上の位置, その大きさ)
        for pn in range(1, self.npages + 1):
            a = struct.unpack_from('<I', d, fixpage + (pn - 1) * 4)[0]
            b = struct.unpack_from('<I', d, fixpage + pn * 4)[0]
            p = fixrec + a; end = fixrec + b
            oi, pbase, foff, ln = self.pageoff[pn]
            while p < end:
                src = d[p]; flg = d[p + 1]; p += 2
                assert not (src & 0x20), 'src list'
                srcoff = struct.unpack_from('<h', d, p)[0]; p += 2
                if flg & 0x40: tobj = struct.unpack_from('<H', d, p)[0]; p += 2
                else: tobj = d[p]; p += 1
                assert flg & 3 == 0, flg
                if (src & 0xf) == 2:
                    tgt = 0
                else:
                    if flg & 0x10: tgt = struct.unpack_from('<I', d, p)[0]; self.fixpos.append((len(self.fix), p, 4)); p += 4
                    else: tgt = struct.unpack_from('<H', d, p)[0]; self.fixpos.append((len(self.fix), p, 2)); p += 2
                self.fix.append((oi, pbase + srcoff, src & 0xf, tobj - 1, tgt))
        for oi, off, st, to, tgt in self.fix:
            if off < 0: continue
            v = self.objs[to]['base'] + tgt
            if st == 7:
                struct.pack_into('<I', self.img[oi], off, v)
            elif st == 8:  # 32-bit self-relative
                struct.pack_into('<I', self.img[oi], off, v - (self.objs[oi]['base'] + off + 4))
            elif st == 2:
                pass
            else:
                pass
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    def obj_of(self, va):
        for i, o in enumerate(self.objs):
            if o['base'] <= va < o['base'] + o['vsize']: return i
    def read(self, va, n):
        i = self.obj_of(va); o = self.objs[i]
        return bytes(self.img[i][va - o['base']: va - o['base'] + n])
    def u32(self, va): return struct.unpack('<I', self.read(va, 4))[0]
    def dis(self, va, n=40, stop_ret=False):
        out = []
        code = self.read(va, n * 8)
        for ins in self.md.disasm(code, va):
            out.append('%08x: %-22s %s %s' % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
            if len(out) >= n or (stop_ret and ins.mnemonic == 'ret'): break
        return '\n'.join(out)
    def file_off(self, va):
        i = self.obj_of(va); o = self.objs[i]; rel = va - o['base']
        pn = o['pmi'] + rel // self.pagesize
        return self.pageoff[pn][2] + rel % self.pagesize

def va_of_file(e, fo):
    for pn, (oi, rel, off, ln) in e.pageoff.items():
        if off <= fo < off + ln:
            return e.objs[oi]['base'] + rel + (fo - off)
