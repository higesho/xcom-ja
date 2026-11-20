# パッチデータ（build/patch.bin）を作る
#   訳: text/ja_chunks/<名前>_*.json→ text/ja/frag.json → text/ja/fix.json の順に上書き。名前は
#       ufo2p_block / tacp_block（EXE の文字列のまとまり、id = 順番）、ufo2p_ind / tacp_ind（直接参照、id = 番地）、paedia（UFOペディア）
#   字形: 小 = 東雲 12、大 = 東雲 16、もう一つの小さい字（ツールチップなど）= 美咲 8
import json, os, struct, sys, re, glob
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
import extract
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)

# ------------------------------------------------------------------ 字形
def load_bdf(path, jis=False):
    g = {}
    bits = None; enc = None
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
                    if 0 <= x < w: rows[y] |= 1 << (15 - x)
    return rows

SHN12 = load_bdf(J('font', 'shnmk12.bdf'), jis=True)
SHN16 = load_bdf(J('font', 'shnmk16.bdf'), jis=True)
K12 = load_bdf(J('font', 'k8x12.bdf'))
MISAKI = load_bdf(J('font', 'misaki_gothic_2nd.bdf'))

def small_glyph(ch):
    gl = SHN12.get(ch) or K12.get(ch)
    return render(gl, 12, 12, 10) if gl else None

def tiny_glyph(ch):
    gl = MISAKI.get(ch)
    return [r >> 8 for r in render(gl, 8, 8, 7)] if gl else None

def big_glyph(ch):
    gl = SHN16.get(ch)
    return render(gl, 16, 16, 14) if gl else None

NOHEAD = set('、。，．・：；？！゛゜ー―‐～…‥）」』】〕〉》］｝ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々')
NOTAIL = set('（「『【〔〈《［｛')

# ------------------------------------------------------------------ 文字列の符号化
TRAILS = [t for t in range(0xa0, 0x100) if t != 0xe1]
def norm(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0xff01 <= o <= 0xff5e and ch not in '（）「」：！？％':
            ch = chr(o - 0xfee0)
        out.append(ch)
    return ''.join(out)

class Enc:
    """字の符号。text/codes.json に一度決めた符号を残し、版を重ねても同じ字は同じ符号にする
    （基地やセーブの名前はゲームがこの符号のままセーブデータに書くため）"""
    CODES = os.path.join(R, 'text', 'codes.json')
    def __init__(self): self.code = {}
    def assign(self, texts):
        cnt = {}
        for s in texts:
            for ch in s:
                if ord(ch) >= 0x80: cnt[ch] = cnt.get(ch, 0) + 1
        old = json.load(open(self.CODES, encoding='utf-8')) if os.path.exists(self.CODES) else {}
        used = set(old.values())
        for ch, v in old.items(): self.code[ch] = (v >> 8, v & 0xff)
        free = [(0x80 + i // len(TRAILS)) << 8 | TRAILS[i % len(TRAILS)] for i in range(32 * len(TRAILS))]
        free = [v for v in free if v not in used]
        new = sorted((c for c in cnt if c not in self.code), key=lambda c: (-cnt[c], c))
        if len(new) > len(free): raise SystemExit('too many chars %d' % (len(self.code) + len(new)))
        for ch, v in zip(new, free): self.code[ch] = (v >> 8, v & 0xff)
        json.dump({c: (l << 8) | t for c, (l, t) in sorted(self.code.items(), key=lambda kv: kv[1])},
                  open(self.CODES, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    def enc(self, s):
        b = bytearray()
        for ch in s:
            o = ord(ch)
            if o < 0x80: b.append(o)
            else: b += bytes(self.code[ch])
        return bytes(b)

def load_ja(name):
    out = {}
    for p in sorted(glob.glob(J('text', 'ja_chunks', name + '_*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is not None: out[str(e['id'])] = e['ja']
    for f in ('frag.json', 'fix.json'):
        p = J('text', 'ja', f)
        if os.path.exists(p):
            for k, v in json.load(open(p, encoding='utf-8')).get(name, {}).items(): out[str(k)] = v
    return out

# ------------------------------------------------------------------ EXE
CB = ['F1', 'SMALL', 'BIG', 'FONT1', 'SMALLW', 'BIGW', 'F1W', 'ENTRY']
X = ['F1', 'SMALL', 'BIG', 'FONT1', 'SMALLW', 'BIGW', 'F1W', 'ENTRY', 'F1WCONT', 'F1WEBP', 'F1SUB',
     'DREF', 'DVAL', 'CUR', 'SCREEN', 'CLIP', 'KERN', 'COLT', 'MAXR', 'F1PTR', 'WTAB1', 'POOL', 'SCRATCH']
XI = {n: i for i, n in enumerate(X)}
EXES = {
    'UFO2P.EXE': dict(kind=0, F1=0x27020, F1SUB=0x2c, SMALL=0x27b60, BIG=0x27df0, FONT1=0x27a00, SMALLW=0x27aa0, BIGW=0x27d30,
                      F1W=0x2714b, F1WB='0fb6ea31c0', F1WCONT=0x27177, F1WEBP=1, ENTRY=0xc07fc,
                      CUR=0x182dd0, SCREEN=0x182dec, CLIP=0xd4cd6, KERN=0xe69cd, COLT=0xe69f0, MAXR=0x1a1154, F1PTR=0x1a1148, WTAB1=0xe6925,
                     UPPER=0x30083),
    'TACP.EXE': dict(kind=1, F1=0x32ba0, F1SUB=0x34, SMALL=0x33620, BIG=0x338b0, FONT1=0x334e0, SMALLW=0x33560, BIGW=0x337f0,
                     F1W=0x32cd0, F1WB='31c088d08a', F1WCONT=0x32cfd, F1WEBP=0, ENTRY=0xc2928,
                     CUR=0xe60b4, SCREEN=0xe6080, CLIP=0xe4d74, KERN=0x284c85, COLT=0x284ca3, MAXR=0x2cce0a, F1PTR=0x2ccaa8, WTAB1=0x284bd9,
                     UPPER=0x3bb83),
}
PROLOGUE = {'F1': None, 'SMALL': '5156575583ec20', 'BIG': '5156575583ec20', 'FONT1': '51565783ec04', 'SMALLW': '5351525657', 'BIGW': '5351525657',
            'ENTRY': 'fb83e4fc'}
POOLMAX = 0x40000
SCRATCH = 0x6000

def exe_patch(name, pool_len):
    cfg = EXES[name]; kind = cfg['kind']
    L = LE(J('orig', name))
    raw = open(J('orig', name), 'rb').read()
    ents = []
    def put(va, new):
        fo = L.file_off(va)
        ents.append((fo, raw[fo:fo + len(new)], bytes(new)))
    def chk(va, h): assert L.read(va, len(bytes.fromhex(h))) == bytes.fromhex(h), (name, hex(va), L.read(va, 8).hex(), h)
    cb = lambda i: bytes([0xfe, 0x38, 0x70 + kind * 8 + i, 0x00])
    x = [0] * len(X)
    for i, n in enumerate(CB):
        va = cfg[n]
        if n == 'F1': pro = '565755' + '83ec%02x' % cfg['F1SUB']
        elif n == 'F1W': pro = cfg['F1WB']
        else: pro = PROLOGUE[n]
        chk(va, pro)
        put(va, cb(i) + b'\x90' * (len(bytes.fromhex(pro)) - 4))
        x[XI[n]] = va
    # 大文字にする関数（見出し用）: 0x80 以上の字（ヨーロッパの文字の表）を変えずに返す（日本語の符号を壊さないように）
    chk(cfg['UPPER'], '7c07e8'); put(cfg['UPPER'], bytes.fromhex('7c05'))
    for n in ('F1WCONT', 'F1WEBP', 'F1SUB', 'CUR', 'SCREEN', 'CLIP', 'KERN', 'COLT', 'MAXR', 'F1PTR', 'WTAB1'): x[XI[n]] = cfg[n]
    # データのずれ: 小さい字の幅の関数の中の「mov edx,[字間の表]」の番地
    sw = cfg['SMALLW']; assert L.read(sw + 0x25, 2) == b'\x8b\x15'
    x[XI['DREF']] = sw + 0x27; x[XI['DVAL']] = struct.unpack('<I', L.read(sw + 0x27, 4))[0]
    # データの段（スタックのある段）を広げて、末尾を文字列の束と作業場所にする
    le = L.le; objtab = le + struct.unpack_from('<I', raw, le + 0x40)[0]
    so = L.esp_obj - 1
    vs = L.objs[so]['vsize']
    assert L.esp == vs and so == 1
    assert pool_len <= POOLMAX
    fo = objtab + so * 24
    ents.append((fo, raw[fo:fo + 4], struct.pack('<I', vs + POOLMAX + 2 * SCRATCH)))
    x[XI['POOL']] = L.objs[so]['base'] + vs
    x[XI['SCRATCH']] = L.objs[so]['base'] + vs + POOLMAX
    body = struct.pack('<II', len(raw), len(ents)) + b''.join(struct.pack('<IH', fo, len(o)) + o + n for fo, o, n in ents)
    xs = bytes([kind]) + struct.pack('<%dI' % len(X), *x)
    return body, xs

def fixup_sites(L):
    """{target VA: [(site VA, obj)]}（32 ビットの番地の fixup だけ）"""
    m = {}
    for oi, off, st, to, tgt in L.fix:
        if off < 0 or st != 7: continue
        m.setdefault(L.objs[to]['base'] + tgt, []).append((L.objs[oi]['base'] + off, oi))
    return m

def string_pool(name, E, texts):
    """日本語の文字列の束と、書き換える場所の一覧"""
    nm = name.split('.')[0].lower()
    L = LE(J('orig', name))
    rg = extract.BLOCKS[name]
    sites = fixup_sites(L)
    pool = bytearray(); out = []
    # まとまり: 順番どおりに作り直す（訳のないものは英語のまま）
    blk = extract.block_strings(L, rg)
    ja = texts[nm + '_block']
    starts = []
    for i, (va, en) in enumerate(blk):
        s = ja.get(str(i), en)
        starts.append((va, len(en), len(pool)))
        pool += E.enc(s) + b'\0'
    import bisect
    keys = [v for v, _, _ in starts]
    nmid = 0
    for t, ss in sites.items():
        if not extract.in_blocks(rg, t): continue
        k = bisect.bisect_right(keys, t) - 1
        va, ln, no = starts[k]
        d = t - va
        if d:
            nmid += 1
            nxt = starts[k + 1][2] if k + 1 < len(starts) else len(pool)
            d = min(d, nxt - no - 1)
        for site, oi in ss: out.append((site, 0 if oi == 0 else 1, no + d))
    # 直接参照: 訳したものだけ束に足して、指す場所を書き換える
    ind = texts[nm + '_ind']
    for k, s in ind.items():
        t = int(k, 16)
        no = len(pool); pool += E.enc(s) + b'\0'
        for site, oi in sites.get(t, []): out.append((site, 0 if oi == 0 else 1, no))
    print(name, 'pool', len(pool), 'sites', len(out), 'mid-string targets', nmid)
    body = bytes([EXES[name]['kind']]) + struct.pack('<I', len(pool)) + bytes(pool) + struct.pack('<I', len(out)) + \
        b''.join(struct.pack('<IBI', s, o, n) for s, o, n in out)
    return body, len(pool)

def paedia_files(E, ja):
    d = open(J('orig', 'PAEDIA.MT'), 'rb').read()
    idx = open(J('orig', 'PAEDIA.MTI'), 'rb').read()
    n = len(idx) // 4; offs = struct.unpack('<%dI' % n, idx)
    out = bytearray(); noffs = []
    for k in range(n - 1):
        rec = d[offs[k]:offs[k + 1]]
        noffs.append(len(out))
        p = 0; box = 0
        while p + 12 <= len(rec) and rec[p:p + 2] != b'\xff\xff':
            e = rec.find(b'\0', p + 12)
            txt = rec[p + 12:e].decode('latin-1')
            s = ja.get('%d.%d' % (k, box), txt)
            out += rec[p:p + 12] + E.enc(s) + b'\0'
            box += 1; p = e + 1
        out += rec[p:]
    noffs.append(len(out))
    return bytes(out), struct.pack('<%dI' % len(noffs), *noffs), len(d), len(idx)

def sec(t, d): return t.encode() + struct.pack('<I', len(d)) + d
def named(n, d): return bytes([len(n)]) + n.encode() + d

NAMES = ['ufo2p_block', 'tacp_block', 'ufo2p_ind', 'tacp_ind', 'paedia']

def all_texts():
    """名前ごとの訳 {id: 訳}。blk_*（英文ごと）は uniq.json で元の場所に広げ、pa_* は paedia に入れる"""
    out = {n: {} for n in NAMES}
    um = json.load(open(J('text', 'en', 'uniq.json'), encoding='utf-8'))
    for p in sorted(glob.glob(J('text', 'ja_chunks', 'blk_*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is None: continue
            for nm, i in um.get(e['id'], []): out[nm][str(i)] = e['ja']
    for p in sorted(glob.glob(J('text', 'ja_chunks', 'pa_*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is not None: out['paedia'][str(e['id'])] = e['ja']
    for f in ('frag.json', 'fix.json'):
        p = J('text', 'ja', f)
        if os.path.exists(p):
            for n, d in json.load(open(p, encoding='utf-8')).items():
                for k, v in d.items():
                    if n == 'blk':          # 英文ごとの訳（uniq.json で広げる）
                        for nm, i in um.get(k, []): out[nm][str(i)] = v
                    else: out[n][str(k)] = v
    return {n: {k: norm(v) for k, v in d.items()} for n, d in out.items()}

def main():
    texts = all_texts()
    E = Enc()
    E.assign([v for n in NAMES for v in texts[n].values()])
    gl = []; miss = []
    for ch, (l, t) in sorted(E.code.items(), key=lambda kv: kv[1]):
        sm = small_glyph(ch); bg = big_glyph(ch)
        if sm is None or bg is None: miss.append(ch)
        sm = sm or [0] * 12; bg = bg or (sm + [0] * 4 if sm else [0] * 16)
        fl = (1 if ch in NOHEAD else 0) | (2 if ch in NOTAIL else 0)
        ti = tiny_glyph(ch) or [0] * 8
        gl.append(struct.pack('<HBB', (l << 8) | t, fl, 0) + struct.pack('<12H', *sm) + struct.pack('<16H', *bg) + bytes(ti))
    if miss: print('glyph missing:', ''.join(miss))
    secs = [sec('G', struct.pack('<I', len(gl)) + b''.join(gl))]
    mt, mti, osz, osz2 = paedia_files(E, texts['paedia'])
    secs.append(sec('F', named('PAEDIA.MT', struct.pack('<II', osz, len(mt)) + mt)))
    secs.append(sec('F', named('PAEDIA.MTI', struct.pack('<II', osz2, len(mti)) + mti)))
    for name in ('UFO2P.EXE', 'TACP.EXE'):
        sp, plen = string_pool(name, E, texts)
        body, xs = exe_patch(name, plen)
        secs.append(sec('E', named(name, body)))
        secs.append(sec('X', xs))
        secs.append(sec('S', sp))
    blob = b'XCJ1' + struct.pack('<I', len(secs)) + b''.join(secs)
    os.makedirs(J('build'), exist_ok=True)
    open(J('build', 'patch.bin'), 'wb').write(blob)
    print('chars', len(E.code), 'blob', len(blob))

if __name__ == '__main__':
    main()
