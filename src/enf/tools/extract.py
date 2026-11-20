# パッケージから、訳す文字列（localized の文字列の既定値）を取り出す
#   python tools/extract.py  → text/en/units.json  [{"id": "Package.Class.Prop[i]", "pkg", "cls", "key", "en"}]
#   キー: .int ファイルの [Class] の Key（配列は Key[i]）
import os, sys, json, struct, glob
sys.path.insert(0, os.path.dirname(__file__))
import upk
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
GAME = os.path.abspath(os.path.join(R, '..'))
SIZES = [1, 2, 4, 12, 16]
CPF_LOCALIZED = 0x8000

def prop_info(k, e):
    b = k.data(e); p = 0
    n, p = upk.ci(b, p)               # 先頭のタグ付きプロパティ（None）
    sup, p = upk.ci(b, p); nxt, p = upk.ci(b, p)
    dim, flags = struct.unpack_from('<iI', b, p)
    return dim, flags

def scan_defaults(k, cls_e, name):
    """クラスの中身から、プロパティ name の文字列の既定値を探す → {index: 文字列}"""
    b = k.data(cls_e)
    try: ni = k.names.index(name)
    except ValueError: return {}
    tag = upk.ci_bytes(ni)
    out = {}
    p = 0
    while True:
        p = b.find(tag, p)
        if p < 0: break
        q = p + len(tag); p += 1
        if q >= len(b): break
        info = b[q]; q += 1
        if info & 0x0f != 13: continue      # StrProperty
        sc = (info >> 4) & 7
        if sc < 5: size = SIZES[sc]
        elif sc == 5: size = b[q]; q += 1
        elif sc == 6: size = struct.unpack_from('<H', b, q)[0]; q += 2
        else: size = struct.unpack_from('<I', b, q)[0]; q += 4
        idx = 0
        if info & 0x80:
            x = b[q]
            if x < 0x80: idx = x; q += 1
            elif x < 0xc0: idx = struct.unpack_from('>H', b, q)[0] & 0x3fff; q += 2
            else: idx = struct.unpack_from('>I', b, q)[0] & 0x3fffffff; q += 4
        try:
            s, q2 = upk.fstring(b, q)
        except Exception:
            continue
        if q2 - q != size: continue
        out[idx] = s
    return out

def loc_props(paths):
    """全パッケージの localized の文字列プロパティ: 名前 → 配列の数"""
    out = {}
    for f in paths:
        k = upk.Pkg(f)
        for e in k.exports:
            if k.cls_name(e) != 'StrProperty' or e['pkg'] <= 0: continue
            dim, flags = prop_info(k, e)
            if flags & CPF_LOCALIZED: out[e['name']] = max(out.get(e['name'], 1), dim)
    return out

def extract(path, props, kinds=('Class',)):
    k = upk.Pkg(path)
    pkg = os.path.splitext(os.path.basename(path))[0]
    units = []
    for e in k.exports:
        if k.cls_name(e) not in kinds and 'Class' in kinds: continue
        if e['size'] <= 0: continue
        for name, dim in props.items():
            vals = scan_defaults(k, e, name)
            for i, s in sorted(vals.items()):
                key = name if dim == 1 else '%s[%d]' % (name, i)
                units.append(dict(id='%s.%s.%s' % (pkg, e['name'], key), pkg=pkg, cls=e['name'], key=key, en=s))
    return units

def read_int(path):
    """既存の .int を読む → [(節, キー, 値)]（[public] の Object= は除く）"""
    raw = open(path, 'rb').read()
    t = raw.decode('utf-16') if raw[:2] in (bytes([0xff, 0xfe]), bytes([0xfe, 0xff])) else raw.decode('latin-1')
    sec = None; out = []
    for l in t.splitlines():
        l = l.strip()
        if not l or l.startswith(';'): continue
        if l.startswith('[') and l.endswith(']'): sec = l[1:-1]; continue
        if '=' not in l or sec is None or sec.lower() == 'public': continue
        k, v = l.split('=', 1)
        if v.startswith('"') and v.endswith('"') and len(v) >= 2: v = v[1:-1]
        out.append((sec, k.strip(), v))
    return out

if __name__ == '__main__':
    import re
    pk = sorted(glob.glob(os.path.join(GAME, 'System', '*.u')))
    props = loc_props(pk)
    print(len(props), 'localized string properties')
    allu = []
    def add(intfile, sec, key, en, src):
        allu.append(dict(id='%s:%s.%s' % (intfile, sec, key), int=intfile, sec=sec, key=key, en=en, src=src))
    for f in pk:
        u = extract(f, props)
        for x in u: add(x['pkg'] + '.int', x['cls'], x['key'], x['en'], 'u')
        print(os.path.basename(f), len(u))
    for f in sorted(glob.glob(os.path.join(GAME, 'Maps', '*.xcm'))):
        u = extract(f, props, kinds=())
        for x in u: add(x['pkg'] + '.int', x['cls'], x['key'], x['en'], 'map')
    for f in sorted(glob.glob(os.path.join(GAME, 'System', '*.int'))):
        for sec, k, v in read_int(f): add(os.path.basename(f), sec, k, v, 'int')
    # 同じ id は後のもの（既存の .int）を優先
    d = {}
    for x in allu: d[x['id']] = x
    allu = list(d.values())
    os.makedirs(os.path.join(R, 'text', 'en'), exist_ok=True)
    json.dump(allu, open(os.path.join(R, 'text', 'en', 'units.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    json.dump(props, open(os.path.join(R, 'text', 'en', 'props.json'), 'w'), indent=0)
    print('total', len(allu), sum(len(x['en']) for x in allu))
