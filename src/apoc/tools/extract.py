# EXE の文章を text/en/*.json に書き出す
#   <exe>_block.json : 文字列のまとまり（番号で引かれる）。[{id, en}]  id = まとまりの中の順番
#   <exe>_ind.json   : コードから直接参照される文字列（まとまりの外）。[{id: "番地", en, refs}]
#   paedia.json      : UFOペディア（PAEDIA.MT）の文字列。[{id: "記事.箱", en}]
import sys, os, re, json, struct
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)

BLOCKS = {'UFO2P.EXE': [(0xe732e, 0xf3794)], 'TACP.EXE': [(0x28e10d, 0x2929c4), (0x2929ff, 0x292d18)]}
SKIP = re.compile(r'(?i)(\.(dat|pcx|pck|tab|map|exe|cfg|bld|raw|smk|mt|mti|spc|pal|ico|txt|00\w?)\b|^[a-z]+/|\\|%[0-9]*[lu]|^rb$|^wb$|^r\+b$|couldn|^extra|malloc|loadf|^_STR_|^strdup)')

def block_strings(L, ranges):
    """まとまり（複数あれば順につなげる）の文字列 [(番地, 文字列)]"""
    b1 = L.objs[1]['base']; img = bytes(L.img[1])
    out = []
    for a, b in ranges:
        seg = img[a - b1:b - b1]
        p = 0
        while p < len(seg):
            e = seg.find(b'\0', p)
            if e < 0: e = len(seg)
            out.append((a + p, seg[p:e].decode('latin-1')))
            p = e + 1
    return out

def in_blocks(ranges, t): return any(a <= t < b for a, b in ranges)

def refs_map(L):
    m = {}
    for oi, off, st, to, tgt in L.fix:
        if off < 0: continue
        m.setdefault(L.objs[to]['base'] + tgt, []).append(L.objs[oi]['base'] + off)
    return m

def ind_strings(L, ranges):
    b1 = L.objs[1]['base']; img = bytes(L.img[1]); vs = L.objs[1]['vsize']
    out = []
    for t, srcs in sorted(refs_map(L).items()):
        if not (b1 <= t < b1 + vs) or in_blocks(ranges, t): continue
        p = t - b1
        if p > 0 and img[p - 1] != 0: continue          # 文字列の途中を指すものは除く
        e = img.find(b'\0', p)
        s = img[p:e]
        if not (2 <= len(s) <= 1500): continue
        if any((c < 0x20 and c not in (9, 10)) or c > 0x7e for c in s): continue
        txt = s.decode('latin-1')
        if not re.search(r'[A-Za-z]{2}', txt) or SKIP.search(txt): continue
        out.append({'id': '%x' % t, 'en': txt, 'refs': len(srcs)})
    return out

def paedia():
    d = open(J('orig', 'PAEDIA.MT'), 'rb').read()
    idx = open(J('orig', 'PAEDIA.MTI'), 'rb').read()
    n = len(idx) // 4; offs = struct.unpack('<%dI' % n, idx)
    out = []
    for k in range(n - 1):
        rec = d[offs[k]:offs[k + 1]]
        p = 0; box = 0
        while p + 12 <= len(rec) and rec[p:p + 2] != b'\xff\xff':
            e = rec.find(b'\0', p + 12)
            txt = rec[p + 12:e].decode('latin-1')
            out.append({'id': '%d.%d' % (k, box), 'en': txt})
            box += 1; p = e + 1
    return out

if __name__ == '__main__':
    os.makedirs(J('text', 'en'), exist_ok=True)
    for exe, rg in BLOCKS.items():
        L = LE(J('orig', exe))
        nm = exe.split('.')[0].lower()
        bl = [{'id': i, 'en': s} for i, (va, s) in enumerate(block_strings(L, rg))]
        json.dump(bl, open(J('text', 'en', nm + '_block.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        ind = ind_strings(L, rg)
        json.dump(ind, open(J('text', 'en', nm + '_ind.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        print(exe, 'block', len(bl), sum(len(x['en']) for x in bl), 'ind', len(ind), sum(len(x['en']) for x in ind))
    pa = paedia()
    json.dump(pa, open(J('text', 'en', 'paedia.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('paedia', len(pa), sum(len(x['en']) for x in pa))
