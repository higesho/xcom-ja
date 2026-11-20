# 地球画面の右のボタン（GEOGRAPH/GEOBORD.SCR の x 256-319）の字を日本語に描き替える
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from make_patch import MISAKI, render
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BIG = [(0, '迎撃'), (12, '基地'), (24, 'グラフ'), (36, 'UFOペディア'), (48, 'オプション'), (60, '資金')]
TIME = [(112, 0, '5秒'), (112, 1, '1分'), (126, 0, '5分'), (126, 1, '30分'), (140, 0, '1時間'), (140, 1, '1日')]
FILL, FACE = 0x02, 0x05

def glyph(ch):
    gl = MISAKI[ch]
    w = gl[0][0] if ord(ch) < 0x80 else 7
    adv = 4 if ord(ch) < 0x80 else 8
    return render(gl, 8, 8, 7), adv

def text_w(s): return sum(glyph(c)[1] for c in s) - 1

def draw(d, x, y, s):
    for ch in s:
        rows, adv = glyph(ch)
        for r in range(7):
            for c in range(8):
                if (rows[r] >> (7 - c)) & 1: d[(y + r) * 320 + x + c] = FILL
        x += adv

def build(src):
    d = bytearray(src)
    for y0, s in BIG:
        for y in range(y0 + 2, y0 + 9):
            for x in range(259, 317): d[y * 320 + x] = FACE
        draw(d, 259 + (58 - text_w(s)) // 2, y0 + 2, s)
    for y0, col, s in TIME:
        x0 = 256 + col * 32
        for y in range(y0 + 2, y0 + 11):
            for x in range(x0 + 3, x0 + 29): d[y * 320 + x] = FACE
        draw(d, x0 + 3 + (26 - text_w(s)) // 2, y0 + 3, s)
    return bytes(d)

if __name__ == '__main__':
    from PIL import Image
    d = build(open(os.path.join(R, 'orig', 'GEOBORD.SCR'), 'rb').read())
    pal = open(os.path.join(R, '..', 'TFD', 'GEODATA', 'PALETTES.DAT'), 'rb').read()
    P = []
    for i in range(256): P += [pal[i * 3] * 4, pal[i * 3 + 1] * 4, pal[i * 3 + 2] * 4]
    im = Image.frombytes('P', (320, 200), d); im.putpalette(P)
    im.crop((256, 0, 320, 160)).convert('RGB').resize((256, 640), Image.NEAREST).save(os.path.join(R, 'work', 'geobord_ja.png'))
