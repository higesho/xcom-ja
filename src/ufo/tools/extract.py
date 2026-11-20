# ENGLISH.DAT / ENGLISH2.DAT -> text/en/*.json（番号付きの文字列の並び）
import json, os
R = os.path.join(os.path.dirname(__file__), '..')
os.makedirs(os.path.join(R, 'text', 'en'), exist_ok=True)
for f, o in (('ENGLISH.DAT', 'geo'), ('ENGLISH2.DAT', 'tac')):
    d = open(os.path.join(R, 'orig', f), 'rb').read()
    ss = d.split(b'\x00')
    assert ss[-1] == b''
    ss = ss[:-1]
    out = [{'id': i, 'en': s.decode('latin-1')} for i, s in enumerate(ss)]
    json.dump(out, open(os.path.join(R, 'text', 'en', o + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(o, len(out), sum(len(s) for s in ss))
