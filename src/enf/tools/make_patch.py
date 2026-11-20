# パッチデータ（build/patch.bin）を作る
#   1. 訳（text/ja_chunks/*.json → text/ja/fix.json で上書き、text/ja/repl.json で用語の揺れを直す）
#   2. .int ファイル（UTF-16）: 既存の .int は値を置き換え、無いもの（XMenu.int、マップの .int）は新しく作る
#   3. 日本語の字のパッケージ XCJP.u: 訳に出てくる字で、work/game の UCC make で作る（--nofont で作り直さない）
#   4. 'XEJ1' に XCJP.u と .int をまとめる
import os, sys, json, glob, struct, re, subprocess, shutil
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
GAME = os.path.abspath(os.path.join(R, '..'))
WG = J('work', 'game')
NOHEAD = set('、。，．・：；？！゛゜ー―‐～…‥）」』】〕〉》］｝ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々')
NOTAIL = set('（「『【〔〈《［｛')
SIZES = [10, 12, 14, 16, 20, 24, 30, 40]

def is_jp(c): return ord(c) >= 0x2e80
def brk(s):
    """折り返しの切れ目: 日本語の字と字の間に半角空白を入れる（UWindow・Canvas は空白でしか折り返さない）。
    日本語の字のすぐ後の空白は、描くときに幅 0 になる。行頭・行末の禁則の所には入れない"""
    if sum(1 for c in s if is_jp(c)) < 8: return s
    out = []
    for i, ch in enumerate(s):
        if i and is_jp(s[i - 1]) and is_jp(ch) and ch not in NOHEAD and s[i - 1] not in NOTAIL: out.append(' ')
        out.append(ch)
    return ''.join(out)

def load_ja():
    out = {}
    for p in sorted(glob.glob(J('text', 'ja_chunks', '*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is not None: out[e['id']] = e['ja']
    fix = json.load(open(J('text', 'ja', 'fix.json'), encoding='utf-8')) if os.path.exists(J('text', 'ja', 'fix.json')) else {}
    rp = J('text', 'ja', 'repl.json')
    if os.path.exists(rp):
        for a, b in json.load(open(rp, encoding='utf-8')):
            for k in out: out[k] = out[k].replace(a, b)
    out.update(fix)
    return out

def read_text(path):
    raw = open(path, 'rb').read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'): return raw.decode('utf-16')
    return raw.decode('latin-1')

def q(v): return '"%s"' % v

def build_ints(ja):
    units = {u['id']: u for u in json.load(open(J('text', 'en', 'units.json'), encoding='utf-8'))}
    byfile = {}
    for k, v in ja.items():
        u = units.get(k)
        if not u: continue
        byfile.setdefault(u['int'], {}).setdefault(u['sec'], {})[u['key']] = brk(v)
    out = {}
    for fn, secs in byfile.items():
        src = os.path.join(GAME, 'System', fn)
        lines = read_text(src).splitlines() if os.path.exists(src) else []
        done = set(); res = []; cur = None
        def flush_section(sec):
            # 既存の節の終わりに、まだ書いていないキーを足す
            for k, v in secs.get(sec, {}).items():
                if (sec, k) not in done: res.append('%s=%s' % (k, q(v))); done.add((sec, k))
        for l in lines:
            st = l.strip()
            if st.startswith('[') and st.endswith(']'):
                if cur is not None: flush_section(cur)
                cur = st[1:-1]; res.append(l); continue
            if cur is not None and '=' in st and not st.startswith(';'):
                k = st.split('=', 1)[0].strip()
                if k in secs.get(cur, {}):
                    res.append('%s=%s' % (k, q(secs[cur][k]))); done.add((cur, k)); continue
            res.append(l)
        if cur is not None: flush_section(cur)
        for sec, kv in secs.items():
            rest = [(k, v) for k, v in kv.items() if (sec, k) not in done]
            if not rest: continue
            res.append(''); res.append('[%s]' % sec)
            for k, v in rest: res.append('%s=%s' % (k, q(v)))
        out[fn] = b'\xff\xfe' + ('\r\n'.join(res) + '\r\n').encode('utf-16-le')
    return out

def build_font(chars):
    """work/game で XCJP.u を作る（BIZ UDGothic、各大きさ、1 ページ 32 字）"""
    os.makedirs(os.path.join(WG, 'jpchars'), exist_ok=True)
    for f in glob.glob(os.path.join(WG, 'jpchars', '*')): os.remove(f)
    open(os.path.join(WG, 'jpchars', 'chars.txt'), 'w', encoding='utf-16').write(''.join(sorted(chars)))
    os.makedirs(os.path.join(WG, 'XCJP', 'Classes'), exist_ok=True)
    cls = 'class XCJP extends Object;\r\n\r\n'
    for h in SIZES:
        cls += ('#exec new TrueTypeFontFactory PACKAGE="XCJP" Name=JP%d FontName="BIZ UDGothic Bold" Height=%d AntiAlias=1 '
                'CharactersPerPage=32 Path=..\\jpchars Wildcard=*.txt\r\n') % (h, h)
    open(os.path.join(WG, 'XCJP', 'Classes', 'XCJP.uc'), 'w', newline='').write(cls)
    u = os.path.join(WG, 'System', 'XCJP.u')
    if os.path.exists(u): os.remove(u)
    r = subprocess.run([os.path.join(WG, 'System', 'UCC.exe'), 'make'], cwd=os.path.join(WG, 'System'), capture_output=True, text=True, errors='replace')
    if not os.path.exists(u): print(r.stdout[-2000:]); raise SystemExit('font build failed')
    return open(u, 'rb').read()

def u16(t):
    b = t.encode('utf-16-le')
    return struct.pack('<H', len(b) // 2) + b

def build_lits(ja, tag='LIT:'):
    items = [(k[len(tag):], brk(v)) for k, v in ja.items() if k.startswith(tag)]
    return struct.pack('<I', len(items)) + b''.join(u16(a) + u16(b) for a, b in items)

def class_tree():
    """クラスの親子（名前 → 親の名前）と、各クラスの書き出し（パッケージ, export）"""
    sys.path.insert(0, os.path.dirname(__file__))
    import upk
    parent, where = {}, {}
    for f in glob.glob(os.path.join(GAME, 'System', '*.u')):
        k = upk.Pkg(f)
        for e in k.exports:
            if k.cls_name(e) != 'Class': continue
            parent[e['name']] = k.obj_name(e['sup'])
            where[e['name']] = (os.path.splitext(os.path.basename(f))[0], k, e)
    return parent, where

def build_sets(ja):
    import extract
    sets = {}
    for k, v in ja.items():
        m = re.match(r'SET:(\w+)\.(\w+):(\w+)\[(\d+)\]$', k)
        if m: sets[(m.group(2), m.group(3), int(m.group(4)))] = (m.group(1), brk(v))
    parent, where = class_tree()
    def is_child(c, a):
        while c:
            c = parent.get(c)
            if c == a: return True
        return False
    out = dict(sets)
    # 子クラスが自分で値を持たない（親の値を引き継ぐ）ときは、子クラスにも同じ訳を入れる
    for (c, prop, i), (pkg, v) in sets.items():
        for d, (dpkg, k, e) in where.items():
            if (d, prop, i) in out or not is_child(d, c): continue
            if i in extract.scan_defaults(k, e, prop): continue
            out[(d, prop, i)] = (dpkg, v)
    items = sorted(out.items())
    b = struct.pack('<I', len(items))
    for (c, prop, i), (pkg, v) in items: b += u16(pkg) + u16(c) + u16(prop) + struct.pack('<i', i) + u16(v)
    return b, len(items)

def main():
    ja = load_ja()
    ints = build_ints(ja)
    chars = set(c for v in ja.values() for c in v if is_jp(c))
    chars |= set('、。「」（）！？・ー')
    fp = J('build', 'XCJP.u')
    if '--nofont' in sys.argv and os.path.exists(fp): font = open(fp, 'rb').read()
    else:
        font = build_font(chars)
        os.makedirs(J('build'), exist_ok=True); open(fp, 'wb').write(font)
    lits = build_lits(ja)
    setb, nset = build_sets(ja)
    files = [('XCJP.u', font), ('lit.bin', lits), ('set.bin', setb), ('draw.bin', build_lits(ja, 'DRAW:'))] + sorted(ints.items())
    blob = b'XEJ1' + struct.pack('<I', len(files))
    for n, d in files: blob += bytes([len(n)]) + n.encode() + struct.pack('<I', len(d)) + d
    open(J('build', 'patch.bin'), 'wb').write(blob)
    os.makedirs(J('build', 'int'), exist_ok=True)
    for n, d in ints.items(): open(J('build', 'int', n), 'wb').write(d)
    print('sets', nset)
    print('translated', len(ja), 'int files', len(ints), 'chars', len(chars), 'font', len(font), 'blob', len(blob))

if __name__ == '__main__':
    main()
