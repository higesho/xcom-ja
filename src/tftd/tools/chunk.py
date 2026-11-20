# 訳す単位を text/chunks/*.json に分ける
#   {"id", "en", "note", "max"?}   max = 全角の最大字数（半角は 0.5 字）
#   前作の訳（text/ja/tm.json）と、手で訳す断片（text/ja/frag.json）は除く
import os, json
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
W = json.load(open(os.path.join(R, 'work', 'wtab.json')))
OUT = os.path.join(R, 'text', 'chunks')
os.makedirs(OUT, exist_ok=True)
TM = json.load(open(os.path.join(R, 'text', 'ja', 'tm.json'), encoding='utf-8'))
FR = json.load(open(os.path.join(R, 'text', 'ja', 'frag.json'), encoding='utf-8'))

GEO_NOTES = [
    (0, 10, 'UFOpaedia article: X-COM flying sub or sub weapon (source text is ALL CAPS; write normal Japanese)'),
    (11, 32, 'UFOpaedia article: alien life form (race overview or autopsy report)'),
    (33, 43, 'UFOpaedia article: alien sub component / alien research'),
    (44, 44, 'research report about the alien threat'),
    (45, 46, 'item name (ammunition)'),
    (47, 48, 'geoscape label; a number or name follows'),
    (49, 151, 'base management screen: label / button / column heading (\\n splits a column heading into lines)'),
    (152, 152, 'UFOpaedia article: weapon'),
    (153, 154, 'item name'),
    (155, 156, 'end-of-game story text (defeat)'),
    (157, 158, 'item name'),
    (159, 159, 'end-of-game story text (defeat)'),
    (160, 169, 'graphs / finance screen label'),
    (180, 184, 'research / production message box'),
    (196, 222, 'mission debriefing: result line or score category'),
    (224, 229, 'base defence / interception battle message'),
    (230, 236, 'sell / sack screen label; a value may follow'),
    (237, 250, 'mission briefing: title or briefing text, or result label'),
    (251, 263, 'error box: HEADLINE\\u0002explanation'),
    (264, 314, 'interception / craft status window label'),
    (315, 356, 'options, craft equipment, aquanaut armour screens: label / button / rank'),
    (357, 364, 'compass direction (alien sub heading)'),
    (365, 394, 'alien sub detected window / craft orders; a name or number may follow'),
    (398, 400, 'research topic name (story)'),
    (401, 465, 'UFOpaedia: category, statistic label or item type'),
    (466, 476, 'alien race name'),
    (484, 539, 'research topic / manufacturable item name (list item)'),
    (516, 517, 'research report (story)'),
    (540, 542, 'personnel type'),
    (543, 557, 'sea or zone name (world region)'),
    (558, 565, 'alien mission type'),
    (566, 600, 'UFOpaedia statistic label, craft or craft weapon name, or base facility name'),
    (601, 616, 'funding organisation name (shown on the funding list and monthly report)'),
    (617, 617, 'UFOpaedia article: weapon'),
    (618, 619, 'message box text'),
    (620, 625, 'label / name'),
    (638, 645, 'funding / craft screen label'),
    (646, 662, 'UFOpaedia article: base facility'),
    (663, 688, 'UFOpaedia article: weapon / equipment, or label'),
    (689, 696, 'alien sub type name'),
    (697, 709, 'monthly report from the committee of funding organisations'),
    (715, 727, 'monthly report / transmission resolver / allocation label'),
    (728, 778, 'city / island / port name on the world map'),
    (779, 802, 'main menu, difficulty, save/load, M.C. training, misc labels'),
    (803, 820, 'aquanaut list / aquanaut statistics screen label'),
    (821, 831, 'UFOpaedia article: SWS (submersible weapons system), ammunition or melee weapon'),
    (832, 839, 'UFOpaedia article: alien mission type'),
    (840, 847, 'UFOpaedia article: alien sub type'),
    (848, 856, 'base facility / transfer message or label'),
    (857, 907, 'item name (inventory, stores, manufacture lists)'),
    (908, 915, 'message box / UFOpaedia article: armour'),
    (919, 933, 'interception battle window: order button or message'),
    (934, 970, 'misc label / button / UFOpaedia article'),
    (971, 1005, 'mission site label, mission briefing title or briefing text'),
]
TAC_NOTES = [
    (0, 24, 'battlescape aquanaut stats / medi-kit screen label'),
    (25, 40, 'battlescape action menu item / label'),
    (41, 54, 'battlescape warning message'),
    (55, 77, 'battlescape label / status message / inventory slot'),
    (78, 85, 'battlescape options screen'),
    (86, 91, 'save game screen'),
    (110, 122, 'battlescape label / message'),
    (123, 182, 'item name in the battlescape inventory, or aquanaut rank'),
    (183, 197, 'battlescape label / message / item name'),
]

def note_of(notes, i, en):
    for a, b, n in reversed(notes):
        if a <= i <= b:
            if en[:1] == ' ' or (en[:1].islower() and len(en) < 40): n += '; something (a name) comes BEFORE this text'
            return n
    return 'label'

def px(s): return sum(W[ord(c)] if ord(c) < 256 else 8 for c in s)

def max_of(en):
    if len(en) > 45 or '\x02' in en: return None
    if '\n' in en: return max(2, max(int(px(l) / 8 + 0.5) for l in en.split('\n')))
    return max(2, int(px(en) / 8 + 0.9))

def build(name, notes, size):
    src = json.load(open(os.path.join(R, 'text', 'en', name + '.json'), encoding='utf-8'))
    skip = set(map(int, TM.get(name, {}))) | set(map(int, FR.get(name, {})))
    items = []
    for e in src:
        if e['id'] in skip or not e['en'].strip() or e['en'] in ('NOT USED',): continue
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

build('geo', GEO_NOTES, 6000)
build('tac', TAC_NOTES, 6000)
