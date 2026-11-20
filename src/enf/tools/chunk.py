# 訳す単位を text/chunks/c_NN.json に分ける
#   {"id": "ファイル.int:節.キー", "en": 英文, "max"?: 全角の最大字数}
import os, sys, json, re
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
OUT = J('text', 'chunks')
SKIP_FILES = {'Editor.int', 'D3DDrv.int', 'GlideDrv.int', 'SoftDrv.int', 'Galaxy.int', 'IpDrv.int', 'IpServer.int', 'UWeb.int',
              'XCom.int', 'XComEd.int', 'WinDrv.int'}
SKIP_SECS = {'Language', 'General@Core.int', 'ServerCommandlet', 'HelloWorldCommandlet', 'SimpleCommandlet', 'StatLog', 'GameReplicationInfo',
             'UBrowserGSpyFact', 'IDMENU_Log', 'IDMENU_NotifyIcon', 'IDDIALOG_Directory'}

def skip(x):
    en, key = x['en'], x['key']
    if x['int'] in SKIP_FILES: return True
    if x['sec'] in SKIP_SECS or '%s@%s' % (x['sec'], x['int']) in SKIP_SECS: return True
    if not re.search(r'[A-Za-z]{2}', en): return True
    if key.startswith(('LocalizedKeyName', 'HelpCmd', 'HelpUsage', 'HelpParm')): return True
    if re.match(r'^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$', en): return True      # パッケージ.名前
    if 'http' in en or en.lower() in ('xcomenforcer',): return True
    if x['sec'] == 'General' and x['int'] == 'Engine.int' and key == 'UpgradeURL': return True
    return False

def max_of(en):
    s = en.strip()
    if len(s) > 28 or s.endswith(('.', '?', '!')) and len(s) > 16: return None
    return max(2, int(len(s.replace('&', '')) * 0.6 + 0.9))

def main():
    u = json.load(open(J('text', 'en', 'units.json'), encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
    keep = [x for x in u if not skip(x)]
    keep.sort(key=lambda x: (not x['int'].startswith(('XMenu', 'Enforcer', 'XInventory', 'Map', 'Bonus', 'DM_', 'NewEntry', 'entry')), x['int'], x['sec'], x['key']))
    cur, size, n = [], 0, 0
    for x in keep:
        e = {'id': x['id'], 'en': x['en']}
        m = max_of(x['en'])
        if m: e['max'] = m
        cur.append(e); size += len(x['en']) + 30
        if size > 4500 or len(cur) >= 90:
            json.dump(cur, open(os.path.join(OUT, 'c_%02d.json' % n), 'w', encoding='utf-8'), ensure_ascii=False, indent=0); n += 1; cur, size = [], 0
    if cur: json.dump(cur, open(os.path.join(OUT, 'c_%02d.json' % n), 'w', encoding='utf-8'), ensure_ascii=False, indent=0); n += 1
    print(n, 'chunks', len(keep), 'units', sum(len(x['en']) for x in keep), 'chars')

if __name__ == '__main__':
    main()
