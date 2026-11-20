# 訳す単位を text/chunks/*.json に分ける
#   blk_NN.json : EXE の文字列（UFO2P と TACP のまとまり）。英文が同じものは 1 つにまとめる。id = "u<番号>"
#   pa_NN.json  : UFOペディア。id = "記事.箱"
#   {"id", "en", "note", "max"?}   max = 全角の最大字数（半角は 0.5 字）
#   text/en/uniq.json: {"u<番号>": [[名前, id], ...]}（make_patch がこれで元の場所に戻す）
import os, json, re
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
OUT = J('text', 'chunks'); os.makedirs(OUT, exist_ok=True)
SPC = open(J('iso', 'SMALFONT.SPC'), 'rb').read()
FR = json.load(open(J('text', 'ja', 'frag.json'), encoding='utf-8')) if os.path.exists(J('text', 'ja', 'frag.json')) else {}

def px(s):
    """小さい字での幅（ゲームと同じ詰め方）"""
    kern = [0] * 15; tot = 0
    for ch in s:
        o = ord(ch)
        if o < 0x20 or o >= 0xac: o = 0x23
        b = (o - 0x20) * 30
        l, r = SPC[b:b + 15], SPC[b + 15:b + 30]
        tot += max(0, max(kern[i] - l[i] for i in range(15)))
        kern = list(r)
    return tot + max(kern)

def max_of(en):
    if len(en) > 24: return None
    lines = en.split('\n')
    return max(2, max(int(px(l) / 13 + 0.6) for l in lines))

UFO_NOTES = [
    (2, 2, 'prompt'), (1271, 1276, 'city map instruction (status bar)'), (1278, 1310, 'vehicle / craft name'),
    (1312, 1398, 'equipment / item name'), (1400, 1402, 'price suffix; a number comes BEFORE'), (1404, 1539, 'proper name of a building in the city'),
    (1541, 1560, 'base facility name'), (1562, 1610, 'vehicle weapon / engine / equipment name'), (1613, 1660, 'building function (type of building)'),
    (1663, 1670, 'alien craft type'), (1672, 1687, 'business sector of an organization'), (1689, 1716, 'organization name'),
    (1718, 1728, 'organization category (keep the leading #)'), (1730, 1731, 'message; a name comes before/after'),
    (1733, 1743, 'building quality (adjective)'), (1745, 1751, 'vehicle / agent status; a name may follow'),
    (1753, 1811, 'vehicle ammunition / fuel name'), (1813, 1829, 'help text (keep the leading #)'),
    (1831, 1877, 'button label, skill name or tooltip'), (1879, 1924, 'error window: title or message'),
    (1926, 2056, 'buy/sell, hire/fire, diplomacy screen: label, button or message'), (2058, 2070, 'alien dimension structure'),
    (2072, 2119, 'city event message; usually a name follows after ": "'), (2121, 2148, 'transfer screen label or message'),
    (2150, 2161, 'month name inside a date like "12 January, 2084" (keep the leading/trailing spaces/comma role)'),
    (2163, 2261, 'research project name'), (2263, 2361, 'research project description'), (2363, 2405, 'manufacture item name'),
    (2407, 2410, 'Senate attitude message'), (2412, 2426, 'alien species name'), (2428, 2434, 'agent rank'),
    (2437, 2449, 'equipment type'), (2452, 2482, 'day of month (ordinal) in a date'), (2484, 2490, 'weekday'),
    (2492, 2565, 'base construction / alien containment / building economy screen label'),
    (2566, 2650, 'info label, diplomacy, auction or score screen'), (2651, 2711, 'UFOpaedia statistic label or agent stat label'),
    (2712, 2896, 'screen label or message'), (2898, 3080, 'button label or tooltip (short)'), (3082, 3093, 'weekly funding report'),
    (3095, 3128, 'main menu / scenario generator'), (3130, 3176, 'unit type'), (3178, 3260, 'finance, end game, options, save/load'),
    (3261, 3379, 'research name, stat label, damage type or message'),
]
TAC_NOTES = [
    (1296, 1388, 'equipment / item name (tactical combat)'), (1389, 1432, 'damage type'), (1434, 1461, 'organization name'),
    (1463, 1501, 'tactical combat message; a name may follow after ": "'), (1503, 1514, 'month name inside a date'),
    (1516, 1522, 'agent rank'), (1525, 1534, 'psionic action'), (1536, 1548, 'equipment type'), (1550, 1604, 'tactical screen label or message'),
    (1605, 1662, 'options / save / reserve TU / warning in tactical combat'), (1664, 1760, 'button tooltip or message in tactical combat'),
    (1759, 1775, 'message toggle label'), (1777, 1823, 'mission briefing title or text'), (1825, 9999, 'alien species / unit type'),
]

def note_of(notes, i, en):
    for a, b, n in notes:
        if a <= i <= b: return n
    return 'UI text'

SKIP_RE = re.compile(r'^(-<.*>-|BLANK|#|-|NOT USED.*|!!!.*|%[a-z]|n/a)$')

def name_range(blk):
    en = [e['en'] for e in blk]
    return en.index('Brown'), en.index('Jacqueline')

def build():
    uniq = {}; order = []
    for nm, notes in (('ufo2p_block', UFO_NOTES), ('tacp_block', TAC_NOTES)):
        blk = json.load(open(J('text', 'en', nm + '.json'), encoding='utf-8'))
        a, b = name_range(blk)
        done = set(map(str, FR.get(nm, {})))
        for e in blk:
            i, s = e['id'], e['en']
            if a <= i <= b or not s.strip() or SKIP_RE.match(s) or str(i) in done: continue
            if s not in uniq:
                uniq[s] = {'refs': [], 'note': note_of(notes, i, s)}; order.append(s)
            uniq[s]['refs'].append([nm, i])
    umap = {}; items = []
    for k, s in enumerate(order):
        uid = 'u%d' % k
        umap[uid] = uniq[s]['refs']
        it = {'id': uid, 'en': s, 'note': uniq[s]['note']}
        m = max_of(s)
        if m: it['max'] = m
        items.append(it)
    json.dump(umap, open(J('text', 'en', 'uniq.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    write('blk', items, 5000)
    pa = json.load(open(J('text', 'en', 'paedia.json'), encoding='utf-8'))
    pitems = []
    for e in pa:
        s = e['en']
        if not s.strip() or SKIP_RE.match(s): continue
        box = e['id'].split('.')[1]
        it = {'id': e['id'], 'en': s, 'note': 'UFOpaedia article title' if box == '0' else 'UFOpaedia article text'}
        if box == '0':
            m = max_of(s)
            if m: it['max'] = m
        pitems.append(it)
    write('pa', pitems, 7000)

def write(prefix, items, size):
    for f in os.listdir(OUT):
        if f.startswith(prefix + '_'): os.remove(os.path.join(OUT, f))
    chunks = []; cur = []; n = 0
    for it in items:
        cur.append(it); n += len(it['en']) + 50
        if n > size: chunks.append(cur); cur = []; n = 0
    if cur: chunks.append(cur)
    for k, c in enumerate(chunks):
        json.dump(c, open(os.path.join(OUT, '%s_%02d.json' % (prefix, k)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(prefix, len(items), 'items', len(chunks), 'chunks', sum(len(x['en']) for x in items), 'chars')

if __name__ == '__main__':
    build()
