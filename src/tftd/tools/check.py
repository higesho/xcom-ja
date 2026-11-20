# 訳の点検: 改行・\x02 の数、頭と末尾の空白・記号、字数、日本語の間の半角空白、字形の有無
import json, os, sys, glob, re
sys.path.insert(0, os.path.dirname(__file__))
from make_patch import load_ja, norm, small_glyph, big_glyph
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
def w(s): return sum(0.5 if ord(c) < 0x80 else 1 for c in s)
maxes = {}
for p in glob.glob(os.path.join(R, 'text', 'chunks', '*.json')):
    n = os.path.basename(p).split('_')[0]
    for e in json.load(open(p, encoding='utf-8')):
        if 'max' in e: maxes[(n, e['id'])] = e['max']
bad = 0; nog = set()
for name in ('geo', 'tac'):
    en = {e['id']: e['en'] for e in json.load(open(os.path.join(R, 'text', 'en', name + '.json'), encoding='utf-8'))}
    ja = load_ja(name)
    miss = [i for i in en if i not in ja and en[i].strip() and en[i] != 'NOT USED']
    if miss: print(name, 'untranslated', miss[:40], len(miss))
    for i, j in sorted(ja.items()):
        e = en[i]; msg = []
        if e.count('\n') != j.count('\n'): msg.append('newlines')
        if e.count('\x02') != j.count('\x02'): msg.append('x02')
        if e[:1] == ' ' and j[:1] not in (' ',) and j[:1] and 'frag' not in sys.argv: pass
        for mk in ('> $', '>', '-', ':', '='):
            if e.rstrip().endswith(mk) and not j.rstrip().endswith(mk) and not j.rstrip().endswith('：') : msg.append('end ' + mk); break
        m = maxes.get((name, i))
        if m and max(w(l) for l in j.split('\n')) > m: msg.append('max %s>%s' % (max(w(l) for l in j.split('\n')), m))
        if re.search(r'[^\x00-\x7f] [^\x00-\x7f]', j): msg.append('space')
        for ch in norm(j):
            if ord(ch) >= 0x80 and (small_glyph(ch) is None or big_glyph(ch) is None): nog.add(ch)
        if msg:
            bad += 1
            if 'v' in sys.argv: print(name, i, msg, repr(e[:50]), repr(j[:50]))
print('issues', bad, 'no glyph', ''.join(sorted(nog)))
