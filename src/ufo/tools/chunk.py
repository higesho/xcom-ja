# 訳す単位を text/chunks/*.json に分ける
#   {"id", "en", "note", "max"?}   max = 全角の最大字数（半角は 0.5 字）
import os, json
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
W = json.load(open(os.path.join(R, 'work', 'wtab.json')))
OUT = os.path.join(R, 'text', 'chunks')
os.makedirs(OUT, exist_ok=True)

# 語順のため連結される断片（text/ja/frag.json で手で訳す）
FRAG_GEO = {42, 916, 107, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 192, 193, 194, 195, 223, 333, 339, 343,
            395, 396, 397, 412, 448, 477, 478, 479, 480, 481, 482, 483, 710, 711, 712, 713, 714, 716, 717, 802, 851,
            917, 918, 961, 962, 74, 830, 831, 965}
FRAG_TAC = {63, 64, 75, 108, 109, 120, 121} | set(range(92, 108))

GEO_NOTES = [
    (0, 10, 'UFOpaedia article: XCOM craft or craft weapon (source text is ALL CAPS; write normal Japanese)'),
    (11, 32, 'UFOpaedia article: alien life form (race overview or autopsy report)'),
    (33, 43, 'UFOpaedia article: UFO component / alien research'),
    (44, 46, 'research report that advances the story toward Mars'),
    (47, 48, 'geoscape label; a number or name follows'),
    (49, 151, 'base management screen: label / button / column heading (\\n splits a column heading into lines)'),
    (152, 159, 'end-of-game story text'),
    (160, 169, 'graphs / finance screen label'),
    (180, 184, 'research / production message box'),
    (185, 191, 'weekday shown in the clock box'),
    (196, 222, 'mission debriefing: result line or score category'),
    (224, 229, 'base defence / interception battle message'),
    (230, 236, 'sell / sack screen label; a value may follow'),
    (237, 250, 'mission briefing: title or briefing text'),
    (251, 263, 'error box: HEADLINE\\u0002explanation'),
    (264, 314, 'interception / craft status window label'),
    (315, 356, 'options, craft equipment, soldier armour screens: label / button'),
    (357, 364, 'compass direction (UFO heading)'),
    (365, 394, 'UFO detected window / craft orders; a name or number may follow'),
    (398, 400, 'research topic name (story)'),
    (401, 465, 'UFOpaedia: category, statistic label or item type'),
    (466, 476, 'alien race name'),
    (484, 542, 'research topic / manufacturable item name (list item)'),
    (543, 557, 'world region name'),
    (558, 565, 'alien mission type'),
    (566, 600, 'UFOpaedia statistic label or base facility name'),
    (601, 616, 'country name (funding nation)'),
    (617, 625, 'unit name'),
    (626, 637, 'month abbreviation in a date ("1日 1月 1999" style; keep very short)'),
    (638, 645, 'funding / craft screen label'),
    (646, 662, 'UFOpaedia article: base facility'),
    (663, 688, 'UFOpaedia article: weapon / equipment'),
    (689, 696, 'UFO type name'),
    (697, 709, 'monthly report from the council of funding nations'),
    (715, 727, 'monthly report / hyper-wave decoder / allocation label'),
    (728, 778, 'city name'),
    (779, 802, 'main menu, difficulty, save/load, psionic training, misc labels'),
    (803, 820, 'soldier list / soldier statistics screen label'),
    (821, 829, 'UFOpaedia article: HWP or ammunition'),
    (832, 839, 'UFOpaedia article: alien mission type'),
    (840, 847, 'UFOpaedia article: UFO type'),
    (848, 856, 'base facility / transfer message or label'),
    (857, 907, 'item name (inventory, stores, manufacture lists)'),
    (908, 915, 'message box / Mars mission briefing'),
    (919, 933, 'interception battle window: order button or message'),
    (934, 971, 'misc label / button / UFOpaedia article'),
]
TAC_NOTES = [
    (0, 24, 'battlescape soldier stats / medi-kit screen label'),
    (25, 40, 'battlescape action menu item / label'),
    (41, 54, 'battlescape warning message'),
    (55, 77, 'battlescape label / status message / inventory slot'),
    (78, 85, 'battlescape options screen'),
    (86, 91, 'save game screen'),
    (110, 122, 'battlescape label / message'),
    (123, 182, 'item name in the battlescape inventory, or soldier rank'),
]

def note_of(notes, i, en):
    for a, b, n in notes:
        if a <= i <= b:
            if en[:1] == ' ' or (en[:1].islower() and len(en) < 40): n += '; something (a name) comes BEFORE this text'
            return n
    return 'label'

def px(s): return sum(W[ord(c)] if ord(c) < 256 else 8 for c in s)

def max_of(en):
    if len(en) > 45 or '\x02' in en: return None
    if '\n' in en: return max(2, max(int(px(l) / 8 + 0.5) for l in en.split('\n')))
    return max(2, int(px(en) / 8 + 0.9))

def build(name, frag, notes, size):
    src = json.load(open(os.path.join(R, 'text', 'en', name + '.json'), encoding='utf-8'))
    items = []
    for e in src:
        if e['id'] in frag or not e['en'].strip() or e['en'] in ('NOT USED',): continue
        it = {'id': e['id'], 'en': e['en'], 'note': note_of(notes, e['id'], e['en'])}
        m = max_of(e['en'])
        if m: it['max'] = m
        items.append(it)
    chunks = []; cur = []; n = 0
    for it in items:
        cur.append(it); n += len(it['en']) + 60
        if n > size: chunks.append(cur); cur = []; n = 0
    if cur: chunks.append(cur)
    for k, c in enumerate(chunks):
        p = os.path.join(OUT, '%s_%02d.json' % (name, k))
        json.dump(c, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(p, len(c), sum(len(x['en']) for x in c))

build('geo', FRAG_GEO, GEO_NOTES, 7000)
build('tac', FRAG_TAC, TAC_NOTES, 7000)
