# パッチデータ（build/patch.bin）を作る
#   英語: orig/*.txt を読む（tools/textfile.py）。訳: text/ja_chunks/*.json → text/ja/fix.json（キー = "ファイル:キー"）
#   日本語は独自の 2 バイト符号（1 バイト目 0x80-0x9F、2 バイト目 0xA0-0xFF）。text/codes.json に一度決めた符号を残す
import json, os, struct, sys, glob, re
sys.path.insert(0, os.path.dirname(__file__))
import textfile
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)

NOHEAD = set('、。，．・：；？！゛゜ー―‐～…‥）」』】〕〉》］｝ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々')
NOTAIL = set('（「『【〔〈《［｛')
TRAILS = list(range(0xa0, 0x100))

def norm(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 0xff01 <= o <= 0xff5e and ch not in '（）「」：！？％':
            ch = chr(o - 0xfee0)
        out.append(ch)
    return ''.join(out)

class Enc:
    CODES = J('text', 'codes.json')
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
        if len(new) > len(free): raise SystemExit('too many chars')
        for ch, v in zip(new, free): self.code[ch] = (v >> 8, v & 0xff)
        json.dump({c: (l << 8) | t for c, (l, t) in sorted(self.code.items(), key=lambda kv: kv[1])},
                  open(self.CODES, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    def enc(self, s):
        b = bytearray()
        for ch in s:
            if ord(ch) < 0x80: b.append(ord(ch))
            else: b += bytes(self.code[ch])
        return bytes(b)

def load_ja():
    out = {}
    for p in sorted(glob.glob(J('text', 'ja_chunks', '*.json'))):
        for e in json.load(open(p, encoding='utf-8')):
            if e.get('ja') is not None: out[e['id']] = e['ja']
    for f in ('frag.json', 'fix.json'):
        p = J('text', 'ja', f)
        if os.path.exists(p): out.update(json.load(open(p, encoding='utf-8')))
    rp = J('text', 'ja', 'repl.json')
    if os.path.exists(rp):                    # 用語の揺れの直し（[[元, 後], ...]）。fix.json の訳には使わない
        fix = json.load(open(J('text', 'ja', 'fix.json'), encoding='utf-8')) if os.path.exists(J('text', 'ja', 'fix.json')) else {}
        for a, b in json.load(open(rp, encoding='utf-8')):
            for k in out:
                if k not in fix: out[k] = out[k].replace(a, b)
    return {k: brk(norm(v)) for k, v in out.items()}

def is_jp(ch): return ord(ch) >= 0x80
NB_HEAD_ASCII = set(',.!?)]:;')
NB_TAIL_ASCII = set('(["')
def brk(s):
    """折り返しの切れ目: 日本語の字と字の間に半角空白を入れる（ゲームの折り返しは空白でしか切れない）。
    描くときは日本語どうしの間の空白を幅 0 にするので、見た目は変わらない。行頭・行末の禁則の所には入れない"""
    if sum(1 for c in s if is_jp(c)) < 10 or re.search(r'\[\d+\]', s): return s
    out = []
    for i, ch in enumerate(s):
        if i and out:
            a, b = s[i - 1], ch
            if is_jp(a) and is_jp(b):
                ok = not (b in NOHEAD or b in NB_HEAD_ASCII or a in NOTAIL or a in NB_TAIL_ASCII)
                if ok: out.append(' ')
        out.append(ch)
    return ''.join(out)

def sec(t, d): return t.encode() + struct.pack('<I', len(d)) + d
def named(n, d): return bytes([len(n)]) + n.encode() + d

def main():
    ja = load_ja()
    docs = textfile.load_all(J('orig'))
    E = Enc(); E.assign(ja.values())
    secs = []
    codes = sorted(E.code.items(), key=lambda kv: kv[1])
    tab = b''.join(struct.pack('<HH', (l << 8) | t, ord(ch)) for ch, (l, t) in codes)
    kin = bytes((1 if ch in NOHEAD else 0) | (2 if ch in NOTAIL else 0) for ch, _ in codes)
    secs.append(sec('C', struct.pack('<I', len(codes)) + tab + kin))
    for fn, doc in docs.items():
        data = doc.build(lambda key: ja.get(fn + ':' + key), E.enc)
        osz = os.path.getsize(J('orig', fn))
        secs.append(sec('F', named(fn, struct.pack('<II', osz, len(data)) + data)))
    blob = b'XIJ1' + struct.pack('<I', len(secs)) + b''.join(secs)
    os.makedirs(J('build'), exist_ok=True)
    open(J('build', 'patch.bin'), 'wb').write(blob)
    print('translated', sum(1 for k in ja), 'chars', len(E.code), 'blob', len(blob))

if __name__ == '__main__':
    main()
