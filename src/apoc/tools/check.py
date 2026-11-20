# 訳の点検: 改行・書式記号（%d など）・\t の数、頭と末尾の空白・記号、頭の #、日本語の間の半角空白、字形の有無
#   python tools/check.py [v]
import json, os, sys, re, glob
sys.path.insert(0, os.path.dirname(__file__))
from make_patch import all_texts, small_glyph, big_glyph, NAMES
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
FMT = re.compile(r'%[-+0-9.]*[a-zA-Z]')
def en_of(name):
    if name == 'paedia': return {e['id']: e['en'] for e in json.load(open(J('text', 'en', 'paedia.json'), encoding='utf-8'))}
    return {str(e['id']): e['en'] for e in json.load(open(J('text', 'en', name + '.json'), encoding='utf-8'))}
texts = all_texts()
bad = 0; nog = set()
for name in NAMES:
    en = en_of(name)
    for i, j in texts[name].items():
        if i not in en: print('unknown id', name, i); continue
        e = en[i]; msg = []
        if e.count('\n') != j.count('\n'): msg.append('newlines')
        if e.count('\t') != j.count('\t'): msg.append('tab')
        if FMT.findall(e) != FMT.findall(j): msg.append('fmt %s/%s' % (FMT.findall(e), FMT.findall(j)))
        if e.startswith('#') and not j.startswith('#'): msg.append('#')
        if e[:1] == ' ' and j[:1] != ' ': msg.append('lead space')
        for mk in ('> $', '>', ': ', ':', '$', '='):
            if e.endswith(mk) and not (j.endswith(mk) or j.endswith(mk.replace(':', '：'))): msg.append('end ' + mk); break
        if e.endswith(' ') and not j.endswith(' ') and not e.endswith(': '): msg.append('trail space')
        if re.search(r'[^\x00-\x7f] [^\x00-\x7f]', j): msg.append('space')
        for ch in j:
            if ord(ch) >= 0x80 and (small_glyph(ch) is None or big_glyph(ch) is None): nog.add(ch)
        if msg:
            bad += 1
            if 'v' in sys.argv: print(name, i, msg, repr(e[:60]), repr(j[:60]))
print('issues', bad, 'no glyph', ''.join(sorted(nog)))
