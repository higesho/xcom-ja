# 訳の検査: python tools/check.py [c_NN ...]（省略で全部）
#   書式の記号（%s %i %o %k %w ...）の数と順番、\n の数、& のショートカット、使えない記号、頭と末尾の空白、max、日本語になっているか
import os, sys, json, re, glob
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
FMT = re.compile(r'%[-+#0]*\d*(?:\.\d+)?[a-zA-Z%]')

def width(s):
    return sum(0.5 if ord(c) < 0x80 else 1 for c in s.replace('&', ''))

def check_pair(e, ja):
    en = e['en']; errs = []
    if not isinstance(ja, str): return ['ja が文字列でない']
    if FMT.findall(en) != FMT.findall(ja): errs.append('書式の記号が違う %s → %s' % (FMT.findall(en), FMT.findall(ja)))
    if en.count('\\n') != ja.count('\\n'): errs.append('\\n の数が違う')
    m = re.search(r'&([A-Za-z0-9])', en)
    if m and ('&' + m.group(1)).lower() not in ja.lower(): errs.append('ショートカット &%s が無い' % m.group(1))
    if '"' in ja: errs.append('半角の " がある')
    if en[:1] == ' ' and ja[:1] != ' ': errs.append('頭の空白が消えた')
    if en[-1:] == ' ' and ja[-1:] != ' ': errs.append('末尾の空白が消えた')
    if e.get('max') and width(ja.strip()) > e['max']: errs.append('長すぎる %.1f > max %d' % (width(ja.strip()), e['max']))
    if re.search(r'[A-Za-z]{4}', en) and ja == en and not re.search(r'[぀-ヿ一-鿿]', ja): errs.append('訳されていない')
    if '\n' in ja: errs.append('改行文字が入っている')
    return errs

def main(names):
    files = sorted(glob.glob(J('text', 'chunks', '*.json')))
    if names: files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in names]
    bad = 0
    for f in files:
        nm = os.path.basename(f)
        src = json.load(open(f, encoding='utf-8'))
        p = J('text', 'ja_chunks', nm)
        if not os.path.exists(p): print(nm, 'まだ訳がない'); bad += 1; continue
        try: out = json.load(open(p, encoding='utf-8'))
        except Exception as ex: print(nm, 'JSON が読めない', ex); bad += 1; continue
        got = {o.get('id'): o.get('ja') for o in out}
        for e in src:
            if e['id'] not in got: print(nm, e['id'], '訳がない'); bad += 1; continue
            for er in check_pair(e, got[e['id']]):
                print(nm, e['id'], er, '|', e['en'][:60], '|', str(got[e['id']])[:60]); bad += 1
    print('problems:', bad)

if __name__ == '__main__':
    main(sys.argv[1:])
