# パッチデータ（build/patch.bin）を作る
#   text/ja/geo.json, tac.json: [{"id", "ja"}]（無い番号は英語のまま）
#   字形: 小 = 美咲ゴシック第2（7x7）、大 = 東雲 12
import json, os, struct, sys, re, unicodedata
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)

# ------------------------------------------------------------------ 字形
def load_bdf(path, jis=False):
    g = {}
    cur = None; bits = None; enc = None
    for line in open(path, encoding='latin-1'):
        t = line.split()
        if not t: continue
        if t[0] == 'ENCODING': enc = int(t[1])
        elif t[0] == 'BBX': bbx = list(map(int, t[1:5]))
        elif t[0] == 'BITMAP': bits = []
        elif t[0] == 'ENDCHAR':
            if jis:
                try: ch = bytes([(enc >> 8) | 0x80, (enc & 0xff) | 0x80]).decode('euc_jp')
                except Exception: ch = None
            else: ch = chr(enc)
            if ch: g[ch] = (bbx, bits)
            bits = None
        elif bits is not None: bits.append(int(t[0], 16))
    return g

def render(gl, w, h, ascent):
    bbx, bits = gl
    bw, bh, bx, by = bbx
    rows = [0] * h
    top = ascent - (by + bh)
    nbytes = (bw + 7) // 8
    for r, v in enumerate(bits):
        y = top + r
        if 0 <= y < h:
            for c in range(bw):
                if (v >> (nbytes * 8 - 1 - c)) & 1:
                    x = bx + c
                    if 0 <= x < w: rows[y] |= 1 << (w - 1 - x)
    return rows

MISAKI = load_bdf(J('font', 'misaki_gothic_2nd.bdf'))
SHN = load_bdf(J('font', 'shnmk12.bdf'), jis=True)
K12 = load_bdf(J('font', 'k8x12.bdf'))

def small_glyph(ch):
    gl = MISAKI.get(ch)
    if gl is None: return None
    rows = render(gl, 8, 8, 7)
    return bytes(rows)           # 7x7 を左上に使う（8 行目・8 列目は空き）

def big_glyph(ch):
    gl = SHN.get(ch)
    if gl is None:
        gl = K12.get(ch)
        if gl is None: return None
        rows = render(gl, 12, 12, 10)
        return [r << 4 for r in rows]
    rows = render(gl, 12, 12, 10)
    return [r << 4 for r in rows]

# 行頭に来ない字（1）、行末に来ない字（2）
NOHEAD = set('、。，．・：；？！゛゜ー―‐～…‥）」』】〕〉》］｝ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々')
NOTAIL = set('（「『【〔〈《［｛')

# ------------------------------------------------------------------ 文字列の符号化
TRAILS = [t for t in range(0xa0, 0x100) if t != 0xe1]
def norm(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0xff01 <= o <= 0xff5e and ch not in '（）「」：！？':   # 全角英数 → 半角
            ch = chr(o - 0xfee0)
        out.append(ch)
    return ''.join(out)

class Enc:
    def __init__(self):
        self.code = {}
    def assign(self, texts):
        cnt = {}
        for s in texts:
            for ch in s:
                if ord(ch) >= 0x80: cnt[ch] = cnt.get(ch, 0) + 1
        chars = sorted(cnt, key=lambda c: (-cnt[c], c))
        if len(chars) > 32 * len(TRAILS): raise SystemExit('too many chars %d' % len(chars))
        for i, ch in enumerate(chars):
            self.code[ch] = (0x80 + i // len(TRAILS), TRAILS[i % len(TRAILS)])
    def enc(self, s):
        b = bytearray()
        for ch in s:
            o = ord(ch)
            if o < 0x80: b.append(o)
            else: b += bytes(self.code[ch])
        return bytes(b)

def load_ja(name):
    """訳: text/ja_chunks/<name>_*.json→ text/ja/frag.json（断片）→ text/ja/fix.json（手直し）の順に上書き"""
    import glob
    out = {}
    for p in sorted(glob.glob(J('text', 'ja_chunks', name + '_*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is not None: out[e['id']] = e['ja']
    for f in ('frag.json', 'fix.json'):
        p = J('text', 'ja', f)
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding='utf-8')).get(name, {}).items(): out[int(k)] = v
    return out

# ------------------------------------------------------------------ EXE
FUNCS = {   # 名前: (GEOSCAPE の番地, 先頭 10 バイト)
    'F1': 0x39410, 'SMALL': 0x398f0, 'BIG': 0x39950, 'BIGW': 0x39bc0, 'SMALLW': 0x39c40, 'F2': 0x39a30,
}
NX = 20
X = dict(F1=0, SMALL=1, BIG=2, BIGW=3, SMALLW=4, F1W=5, F2=6, DREF=7, DVAL=8, CUR=9, SMALLSET=10, BIGLETS=11, WTAB=12,
         KERN=13, KTAB=14, F1PTR=15, CENTER=16, SCREEN=17, MAXR=18, SCRATCH=19)
SCRATCH = 0x3000

def find_funcs(L):
    G = LE(J('orig', 'GEOSCAPE.EXE'))
    img = L.img[0]; out = {}
    for n, a in FUNCS.items():
        sig = bytes(G.read(a, 8 if n == 'SMALLW' else 10))
        hits = [m.start() + L.objs[0]['base'] for m in re.finditer(re.escape(sig), img)]
        if n == 'F2' and not hits: continue
        assert len(hits) == 1, (n, hits)
        out[n] = hits[0]
    return out

def u32(L, va): return struct.unpack('<I', L.read(va, 4))[0]

def exe_patch(name, kind, extra=()):
    L = LE(J('orig', name))
    f = find_funcs(L)
    raw = open(J('orig', name), 'rb').read()
    ents = []
    def put(va, new):
        fo = L.file_off(va)
        ents.append((fo, raw[fo:fo + len(new)], bytes(new)))
    cb = lambda i: bytes([0xfe, 0x38, 0x70 + kind * 8 + i, 0x00])
    x = [0] * NX
    # 入口: 置き換える命令の長さに合わせて nop で埋める
    put(f['F1'], cb(0) + b'\x90\x90'); assert raw[L.file_off(f['F1']):L.file_off(f['F1']) + 6] == bytes.fromhex('5657 5583ec2c'.replace(' ', ''))
    put(f['SMALL'], cb(1) + b'\x90'); assert L.read(f['SMALL'], 5) == bytes.fromhex('5188c188d5')
    put(f['BIG'], cb(2) + b'\x90\x90'); assert L.read(f['BIG'], 6) == bytes.fromhex('51565783ec10')
    put(f['BIGW'], cb(3) + b'\x90'); assert L.read(f['BIGW'], 5) == bytes.fromhex('5351525657')
    put(f['SMALLW'], cb(4) + b'\x90' * 4); assert L.read(f['SMALLW'], 8) == bytes.fromhex('5231d225ff000000')
    f1w = f['F1'] + 0x255
    assert L.read(f1w, 7) == bytes.fromhex('25ff0000008a80'), L.read(f1w, 7).hex()
    put(f1w, cb(5) + b'\x90')
    x[X['F1']] = f['F1']; x[X['SMALL']] = f['SMALL']; x[X['BIG']] = f['BIG']; x[X['BIGW']] = f['BIGW']
    x[X['SMALLW']] = f['SMALLW']; x[X['F1W']] = f1w
    if 'F2' in f:
        put(f['F2'], cb(6) + b'\x90\x90'); x[X['F2']] = f['F2']
    # 番地（命令の中から読む）
    x[X['DREF']] = f['SMALL'] + 0x19; x[X['DVAL']] = u32(L, f['SMALL'] + 0x19)
    x[X['SMALLSET']] = u32(L, f['SMALL'] + 0x19)
    x[X['WTAB']] = u32(L, f['SMALL'] + 0x41)
    x[X['CUR']] = u32(L, f['SMALL'] + 0x47)
    x[X['BIGLETS']] = u32(L, f['BIG'] + 0x1b)
    x[X['KERN']] = u32(L, f['BIG'] + 0x13)
    x[X['KTAB']] = u32(L, f['BIG'] + 0x3d)
    x[X['F1PTR']] = u32(L, f['F1'] + 0xb1)
    x[X['CENTER']] = u32(L, f['F1'] + 0x21) & 0xffffffff
    x[X['SCREEN']] = u32(L, f['F1'] + 0x302)
    x[X['MAXR']] = u32(L, f['SMALLW'] + 0xb)
    assert L.read(f['SMALL'] + 0x17, 2) == b'\x8b\x1d' and L.read(f['SMALL'] + 0x3f, 2) == b'\x8a\x90'
    assert L.read(f['SMALL'] + 0x45, 2) == b'\x8b\x1d' and L.read(f['BIG'] + 0x19, 2) == b'\x8b\x0d'
    assert L.read(f['F1'] + 0xaf, 2) == b'\x89\x35' and L.read(f['F1'] + 0x1e, 3) == b'\x66\x83\x3d'
    assert L.read(f['F1'] + 0x300, 2) == b'\x8b\x1d' and L.read(f['SMALLW'] + 0x8, 3) == b'\x66\x89\x15'
    # データの段（スタックのある段）を広げて、末尾を作業場所にする
    le = L.le; objtab = le + struct.unpack_from('<I', raw, le + 0x40)[0]
    so = L.esp_obj - 1
    vs = L.objs[so]['vsize']
    assert L.esp == vs
    fo = objtab + so * 24
    ents.append((fo, raw[fo:fo + 4], struct.pack('<I', vs + SCRATCH)))
    x[X['SCRATCH']] = L.objs[so]['base'] + vs
    for va, new in extra: put(va, new)
    body = struct.pack('<II', len(raw), len(ents)) + b''.join(struct.pack('<IH', fo, len(o)) + o + n for fo, o, n in ents)
    xs = bytes([kind]) + struct.pack('<%dI' % NX, *x)
    print(name, {k: hex(v) for k, v in zip(X, x)})
    return body, xs

def sec(t, d): return t.encode() + struct.pack('<I', len(d)) + d

def named(n, d): return bytes([len(n)]) + n.encode() + d

def main():
    en_geo = json.load(open(J('text', 'en', 'geo.json'), encoding='utf-8'))
    en_tac = json.load(open(J('text', 'en', 'tac.json'), encoding='utf-8'))
    ja_geo = load_ja('geo'); ja_tac = load_ja('tac')
    extra_ja = {'ENGLISH': '日本語'}
    geo = [norm(ja_geo.get(e['id'], e['en'])) for e in en_geo]
    tac = [norm(ja_tac.get(e['id'], e['en'])) for e in en_tac]
    E = Enc()
    E.assign(geo + tac + list(extra_ja.values()))
    gl = []
    miss = []
    for ch, (l, t) in sorted(E.code.items(), key=lambda kv: kv[1]):
        sm = small_glyph(ch); bg = big_glyph(ch)
        if sm is None or bg is None: miss.append(ch)
        sm = sm or bytes(8); bg = bg or [0] * 12
        fl = (1 if ch in NOHEAD else 0) | (2 if ch in NOTAIL else 0)
        gl.append(struct.pack('<HBB', (l << 8) | t, fl, 0) + sm + struct.pack('<12H', *bg))
    if miss: print('glyph missing:', ''.join(miss))
    secs = [sec('G', struct.pack('<I', len(gl)) + b''.join(gl))]
    for name, lst, osz in (('ENGLISH.DAT', geo, 46601), ('ENGLISH2.DAT', tac, 2272)):
        d = b''.join(E.enc(s) + b'\x00' for s in lst)
        secs.append(sec('F', named(name, struct.pack('<II', osz, len(d)) + d)))
    import geobord
    gb = open(J('orig', 'GEOBORD.SCR'), 'rb').read()
    secs.append(sec('F', named('GEOBORD.SCR', struct.pack('<II', len(gb), len(gb)) + geobord.build(gb))))
    # 言語の選択の "ENGLISH"（GEOSCAPE のデータ）
    G = LE(J('orig', 'GEOSCAPE.EXE'))
    gx = []
    eng = [o['base'] + m.start() for o, img in zip(G.objs, G.img) for m in re.finditer(b'ENGLISH\x00DEUTSCHE', img)]
    assert len(eng) == 1
    jb = E.enc(extra_ja['ENGLISH']) + b'\x00'
    assert len(jb) <= 8
    gx.append((eng[0], jb))
    for name, kind, extra in (('GEOSCAPE.EXE', 0, gx), ('TACTICAL.EXE', 1, ())):
        body, xs = exe_patch(name, kind, extra)
        secs.append(sec('E', named(name, body)))
        secs.append(sec('X', xs))
    blob = b'XCJ1' + struct.pack('<I', len(secs)) + b''.join(secs)
    open(J('build', 'patch.bin'), 'wb').write(blob)
    print('chars', len(E.code), 'blob', len(blob))

if __name__ == '__main__':
    main()
