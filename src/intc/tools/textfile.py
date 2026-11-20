# Text フォルダの文章ファイルを、訳す単位（キー → 英文）に分け、訳を入れて作り直す
#   LangFile1.txt : 行「キー  "文"  ; 注」。キーが重なるときは「キー#2」
#   news1.txt / short1.txt : 「@節」の行のあとに「@項目=文」。単位 = 「節.項目」
import os, re
FILES = ['LangFile1.txt', 'news1.txt', 'short1.txt']
LANG = re.compile(r'^(\s*)([^\s"/;][^\s"]*)(\s+)"(.*)"(.*)$')

class Doc:
    def __init__(self, path):
        self.name = os.path.basename(path)
        self.raw = open(path, 'rb').read()
        self.lines = self.raw.split(b'\r\n')
        self.units = []          # (key, 英文, 行の番号, 文の始まり, 文の終わり)
        seen = {}
        if self.name.lower().startswith('langfile'):
            for i, b in enumerate(self.lines):
                l = b.decode('latin-1')
                m = LANG.match(l)
                if not m: continue
                k = m.group(2)
                seen[k] = seen.get(k, 0) + 1
                if seen[k] > 1: k = '%s#%d' % (k, seen[k])
                st = len(m.group(1)) + len(m.group(2)) + len(m.group(3)) + 1
                self.units.append((k, m.group(4), i, st, st + len(m.group(4))))
        else:
            secn = None
            for i, b in enumerate(self.lines):
                l = b.decode('latin-1')
                if not l.startswith('@'): continue
                if '=' not in l: secn = l[1:].strip(); continue
                f, v = l[1:].split('=', 1)
                k = '%s.%s' % (secn, f.strip())
                seen[k] = seen.get(k, 0) + 1
                if seen[k] > 1: k = '%s#%d' % (k, seen[k])
                st = l.index('=') + 1
                self.units.append((k, v, i, st, len(l)))
    def build(self, get, enc):
        lines = list(self.lines)
        for k, en, i, a, b in self.units:
            t = get(k)
            if t is None: continue
            l = lines[i]
            lines[i] = l[:a] + enc(t) + l[b:]
        return b'\r\n'.join(lines)

def load_all(d):
    return {f: Doc(os.path.join(d, f)) for f in FILES}

if __name__ == '__main__':
    import sys, json
    d = sys.argv[1]
    for f, doc in load_all(d).items():
        print(f, len(doc.units), sum(len(u[1]) for u in doc.units))
        assert doc.build(lambda k: None, lambda s: s.encode('latin-1')) == doc.raw
