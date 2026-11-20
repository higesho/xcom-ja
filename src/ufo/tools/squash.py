# 美咲（7 行）を 6 行に縮める: 同じ行が続く所を 1 つに、なければ差の少ない隣どうしを重ねる
def squash(bits):
    rows = list(bits[:7])
    best, bi = None, None
    for i in range(1, 7):
        a, b = rows[i - 1], rows[i]
        cost = bin(a ^ b).count('1')
        # 端の行（0 と 6）を消すより中を重ねる方がよい
        if best is None or cost < best: best, bi = cost, i
    m = rows[bi - 1] | rows[bi]
    out = rows[:bi - 1] + [m] + rows[bi + 1:]
    return bytes(out[:6])
