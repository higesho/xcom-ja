# 訳す単位を text/chunks/c_NN.json に分ける
#   {"id": "ファイル:キー", "en": 英文, "max"?: 全角の最大字数（短い文字列だけ。半角は 0.5 字）}
#   キーの名前も id に入っているので、文脈の手がかりになる
import os, sys, json, re
sys.path.insert(0, os.path.dirname(__file__))
import textfile
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = lambda *a: os.path.join(R, *a)
OUT = J('text', 'chunks')

def skip(fn, key, en):
    if not re.search(r'[A-Za-z]{2}', en): return True          # 数字・記号・1 字だけ
    if key.startswith('S_KEY'): return True                     # キーボードのキーの名前
    if re.match(r'S_MONTH_ABREV_\w+2$', key): return True       # 月の頭文字 1 字
    return False

def max_of(en):
    if len(en) > 32 or '~' in en or en.rstrip().endswith(('.', '?', '!')) and len(en) > 20: return None
    return max(2, int(len(en.strip()) * 0.65 + 0.9))

def units():
    docs = textfile.load_all(J('orig'))
    for fn, doc in docs.items():
        for k, en, *_ in doc.units:
            if skip(fn, k, en): continue
            yield fn, k, en

def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
    cur, size, n, total = [], 0, 0, 0
    def flush():
        nonlocal cur, size, n
        if cur:
            json.dump(cur, open(os.path.join(OUT, 'c_%02d.json' % n), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            n += 1; cur = []; size = 0
    for fn, k, en in units():
        e = {'id': fn + ':' + k, 'en': en}
        m = max_of(en)
        if m: e['max'] = m
        cur.append(e); size += len(en) + 20; total += 1
        if size > 6500 or len(cur) >= 90: flush()
    flush()
    print(n, 'chunks', total, 'units')

if __name__ == '__main__':
    main()
