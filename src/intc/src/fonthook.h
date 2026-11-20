/* ============================================================ ゲームのスプライトフォント（xi_jp.c から #include する）
 * メニューや画面の字は GDI ではなく、ゲームが持つ絵の字（フォントの物 9 個、0x7765c0 から 0x2acc おき）で描かれる。
 * フォントの物の関数（thiscall）を差し替える:
 *   描く  0x5fe55b (面, 文, x, y, 揃え)    幅  0x5fe30e (文)
 *   折り返して描く 0x5fedd9 (面, 文, RECT*, 揃え) / 0x5ff302 (面, 文, RECT*, 飛ばす行, 揃え) / 行を数える 0x5ff6d9 (?, 文, RECT*, 揃え)
 * 日本語の字があるときだけ自分で処理する。英数字はゲームの描く関数にそのまま描かせ、日本語の字は GDI で作った字の形を
 * 面（16 ビットの DirectDraw の面）に直に書く。色と高さは、そのフォントで「H」を一度描かせて調べる（調べたあと元に戻す）。
 */
#define A_DRAW   0x5fe55b
#define A_WIDTH  0x5fe30e
#define A_WRAP   0x5fedd9
#define A_WRAP2  0x5ff302
#define A_COUNT  0x5ff6d9
#define A_LOCK   0x634239
#define A_UNLOCK 0x6343d1
#define FONT0    0x7765c0
#define FONTSZ   0x2acc
#define NFONT    9
typedef uint8_t F;
#define F_FIXED(f) (*(int8_t*)((f) + 0x2ac0))
#define F_CW(f)    (*(int*)((f) + 0x2ac4))
#define F_H(f)     (*(int*)((f) + 0x2ac8))
#define F_W(f, c)  (*(int*)((f) + 0x26c0 + (c) * 4))
typedef void (__fastcall *draw_t)(F*, void*, void*, const char*, int, int, int);
typedef int  (__fastcall *width_t)(F*, void*, const char*);
typedef void (__fastcall *wrap_t)(F*, void*, void*, const char*, RECT*, int);
typedef void (__fastcall *wrap2_t)(F*, void*, void*, const char*, RECT*, int, int);
typedef int  (__fastcall *count_t)(F*, void*, void*, const char*, RECT*, int);
typedef uint8_t *(__fastcall *lock_t)(void*, void*);
typedef int (__fastcall *unlock_t)(void*, void*);
static draw_t o_draw; static width_t o_width; static wrap_t o_wrap; static wrap2_t o_wrap2; static count_t o_count;
#define s_lock ((lock_t)A_LOCK)
#define s_unlock ((unlock_t)A_UNLOCK)

static int font_index(F *f)
{
    uintptr_t d = (uintptr_t)f - FONT0;
    return (d % FONTSZ == 0 && d / FONTSZ < NFONT) ? (int)(d / FONTSZ) : -1;
}
static int is_jp_at(const uint8_t *u) { return IS_LEAD(u[0]) && IS_TRAIL(u[1]); }
static int has_jp(const char *s)
{
    const uint8_t *u = (const uint8_t*)s;
    if (!u) return 0;
    for (; *u; u++) if (is_jp_at(u)) return 1;
    return 0;
}
/* 日本語の字と日本語の字の間の半角空白は幅 0（折り返しの切れ目として文章に入れてある） */
static int zw_at(const uint8_t *start, const uint8_t *u)
{
    if (u[0] != ' ') return 0;
    return u >= start + 2 && u[-1] >= 0xa0 && u[-2] >= 0x80 && u[-2] < 0xa0 && is_jp_at(u + 1);
}
static int after_ascii(const uint8_t *start, const uint8_t *u)   /* u の日本語の字の直前が英数字・記号（空白以外） */
{
    return u > start && u[-1] > 0x20 && u[-1] < 0x80;
}
static wchar_t jp_char(const uint8_t *u) { wchar_t w = g_uni[(u[0] - 0x80) << 8 | u[1]]; return w ? w : L'?'; }
static uint8_t jp_kin(const uint8_t *u) { return g_kin[(u[0] - 0x80) << 8 | u[1]]; }

/* ---- 日本語の字の形（GDI で作り、覚えておく） */
static int jp_size(F *f) { int h = F_H(f); return h <= 11 ? 10 : h <= 13 ? 12 : h <= 17 ? 14 : 20; }
typedef struct { uint32_t key; int16_t adv, h; uint8_t *a; } glyph_t;
#define GCAP 8192
static glyph_t g_gc[GCAP];
static HDC g_gdc; static HBITMAP g_gbm; static uint32_t *g_gbits; static HFONT g_gfont[64];
static glyph_t *get_glyph(int size, wchar_t ch)
{
    uint32_t key = (uint32_t)size << 16 | ch, i = (key * 2654435761u) % GCAP;
    glyph_t *g;
    SIZE sz; TEXTMETRICW tm;
    int x, y, w, h;
    while (g_gc[i].key && g_gc[i].key != key) i = (i + 1) % GCAP;
    g = &g_gc[i];
    if (g->key) return g;
    if (!g_gdc) {
        BITMAPINFO bi; memset(&bi, 0, sizeof bi);
        bi.bmiHeader.biSize = sizeof bi.bmiHeader; bi.bmiHeader.biWidth = 64; bi.bmiHeader.biHeight = -64;
        bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
        g_gdc = CreateCompatibleDC(NULL);
        g_gbm = CreateDIBSection(g_gdc, &bi, DIB_RGB_COLORS, (void**)&g_gbits, NULL, 0);
        SelectObject(g_gdc, g_gbm);
        SetBkMode(g_gdc, TRANSPARENT); SetTextColor(g_gdc, RGB(255, 255, 255));
    }
    if (size < 8 || size > 40) size = 12;
    if (!g_gfont[size])
        g_gfont[size] = CreateFontW(-size, 0, 0, 0, size >= 18 ? FW_BOLD : FW_NORMAL, 0, 0, 0, SHIFTJIS_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                                    size <= 16 ? NONANTIALIASED_QUALITY : ANTIALIASED_QUALITY, FIXED_PITCH | FF_MODERN,
                                    L"\xff2d\xff33 \x30b4\x30b7\x30c3\x30af");
    SelectObject(g_gdc, g_gfont[size]);
    GdiFlush();
    memset(g_gbits, 0, 64 * 64 * 4);
    TextOutW(g_gdc, 0, 0, &ch, 1);
    GetTextExtentPoint32W(g_gdc, &ch, 1, &sz);
    GetTextMetricsW(g_gdc, &tm);
    GdiFlush();
    w = sz.cx > 64 ? 64 : sz.cx; h = tm.tmHeight > 64 ? 64 : tm.tmHeight;
    g->a = (uint8_t*)malloc(w * h);
    for (y = 0; y < h; y++) for (x = 0; x < w; x++) g->a[y * w + x] = (uint8_t)(g_gbits[y * 64 + x] >> 16);
    g->adv = (int16_t)w; g->h = (int16_t)h; g->key = key;
    return g;
}
static int jp_adv(F *f, const uint8_t *u) { return get_glyph(jp_size(f), jp_char(u))->adv; }

/* ---- 幅 */
static int ascii_w(F *f, uint8_t c) { return F_FIXED(f) ? F_CW(f) : F_W(f, c); }
static int text_width_n(F *f, const char *s, int n)
{
    const uint8_t *u = (const uint8_t*)s, *e = u + n;
    int w = 0;
    if (n < 0) e = (const uint8_t*)~(uintptr_t)0;
    while (u < e && *u) {
        if (is_jp_at(u)) { w += jp_adv(f, u) + after_ascii((const uint8_t*)s, u); u += 2; }
        else if (zw_at((const uint8_t*)s, u)) u++;
        else w += ascii_w(f, *u++);
    }
    return w;
}
static int text_width(F *f, const char *s) { return text_width_n(f, s, -1); }

/* ---- 面 */
typedef struct { uint8_t *p; int pitch, w, h; uint32_t rm, gm, bm; int was; void *surf; } canvas_t;
static int canvas_open(void *surf, canvas_t *c)
{
    uint8_t *o = (uint8_t*)surf;
    void *dds = *(void**)(o + 0x48);
    uint8_t d[0x6c];
    typedef HRESULT (__stdcall *gsd_t)(void*, void*);
    if (!dds) return 0;
    memset(d, 0, sizeof d); *(DWORD*)d = 0x6c;
    if (((gsd_t)(*(void***)dds)[0x58 / 4])(dds, d) != 0) return 0;
    if (*(DWORD*)(d + 0x48 + 0xc) != 16) return 0;
    c->h = *(int*)(d + 8); c->w = *(int*)(d + 0xc);
    c->rm = *(DWORD*)(d + 0x48 + 0x10); c->gm = *(DWORD*)(d + 0x48 + 0x14); c->bm = *(DWORD*)(d + 0x48 + 0x18);
    if (!c->rm || !c->gm || !c->bm) return 0;
    c->was = *(void**)(o + 0x20) != NULL;
    c->p = s_lock(surf, 0);
    if (!c->p) return 0;
    c->pitch = *(int*)(o + 0xc);
    c->surf = surf;
    return 1;
}
static void canvas_close(canvas_t *c) { if (!c->was) s_unlock(c->surf, 0); }
static int lum(canvas_t *c, uint16_t v)
{
    uint32_t r = v & c->rm, g = v & c->gm, b = v & c->bm;
    return (int)(r * 255 / c->rm) * 3 + (int)(g * 255 / c->gm) * 6 + (int)(b * 255 / c->bm);
}
static uint16_t blend(canvas_t *c, uint16_t s, uint16_t d, int a)
{
    uint32_t r = (((s & c->rm) * a + (d & c->rm) * (255 - a)) / 255) & c->rm;
    uint32_t g = (((s & c->gm) * a + (d & c->gm) * (255 - a)) / 255) & c->gm;
    uint32_t b = (((s & c->bm) * a + (d & c->bm) * (255 - a)) / 255) & c->bm;
    return (uint16_t)(r | g | b);
}

/* ---- 「H」を描かせて、字の上下の位置と行ごとの色、影の色を調べる */
typedef struct { int done, tries, top, bot, left; uint16_t col[48]; uint16_t shadow; int sdx, sdy; } probe_t;
static probe_t g_pr[NFONT];
#define PW 48
#define PH 64
#define PX 8
#define PY 32
static void probe_font(F *f, int fi, void *surf, int x, int y)
{
    static uint16_t save[PH][PW], after[PH][PW];
    canvas_t c;
    probe_t *pr = &g_pr[fi];
    int x0 = x - PX, y0 = y - PY, xx, yy, n = 0, cnt_dark = 0, dkl = 1 << 30, ox, oy, pw = PW, ph = PH;
    uint16_t dk = 0;
    if (!canvas_open(surf, &c)) return;
    /* 調べる範囲を面の中に収める（画面の端の近くの字でも調べられるように） */
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x0 + pw > c.w) pw = c.w - x0;
    if (y0 + ph > c.h) ph = c.h - y0;
    ox = x - x0; oy = y - y0;
    if (pw < 16 || ph < 16 || ox < 0 || oy < 0) { canvas_close(&c); return; }
    memset(save, 0, sizeof save); memset(after, 0, sizeof after);
    for (yy = 0; yy < ph; yy++) memcpy(save[yy], c.p + (y0 + yy) * c.pitch + x0 * 2, pw * 2);
    canvas_close(&c);
    o_draw(f, NULL, surf, "H", x, y, 0);
    if (!canvas_open(surf, &c)) return;
    for (yy = 0; yy < ph; yy++) {
        memcpy(after[yy], c.p + (y0 + yy) * c.pitch + x0 * 2, pw * 2);
        memcpy(c.p + (y0 + yy) * c.pitch + x0 * 2, save[yy], pw * 2);
    }
    pr->top = 999; pr->bot = -999; pr->left = 999;
    for (yy = 0; yy < PH; yy++)
        for (xx = 0; xx < PW; xx++) {
            int l;
            if (after[yy][xx] == save[yy][xx]) continue;
            n++;
            if (yy - oy < pr->top) pr->top = yy - oy;
            if (yy - oy > pr->bot) pr->bot = yy - oy;
            if (xx - ox < pr->left) pr->left = xx - ox;
            l = lum(&c, after[yy][xx]);
            if (l < dkl) { dkl = l; dk = after[yy][xx]; }
            if (l < 2550 / 8) cnt_dark++;
        }
    if (n) {
        /* 行ごとに、背景との明るさの差がいちばん大きい画素の色を字の色とする（白い字にも暗い字にも合う） */
        int r, maxc = 0, rows = pr->bot - pr->top + 1, con[48];
        if (rows > 48) rows = 48;
        for (r = 0; r < rows; r++) {
            int bc = -1; uint16_t col = 0;
            yy = pr->top + r + oy;
            for (xx = 0; xx < PW; xx++) {
                int d;
                if (after[yy][xx] == save[yy][xx]) continue;
                d = abs(lum(&c, after[yy][xx]) - lum(&c, save[yy][xx]));
                if (d > bc) { bc = d; col = after[yy][xx]; }
            }
            pr->col[r] = bc >= 0 ? col : (r ? pr->col[r - 1] : 0xffff);
            con[r] = bc;
            if (bc > maxc) maxc = bc;
        }
        /* 縁のぼかしだけの行（差が小さい）は、近くのはっきりした行の色にする */
        for (r = 0; r < rows; r++) {
            int k;
            if (con[r] * 10 >= maxc * 6) continue;
            for (k = 1; k < rows; k++) {
                if (r + k < rows && con[r + k] * 10 >= maxc * 6) { pr->col[r] = pr->col[r + k]; break; }
                if (r - k >= 0 && con[r - k] * 10 >= maxc * 6) { pr->col[r] = pr->col[r - k]; break; }
            }
        }
        /* 明るい字で、暗い画素もはっきり多いときは影があるとみなす */
        if (lum(&c, pr->col[rows / 2]) > 2550 / 2 && cnt_dark * 3 >= n) { pr->shadow = dk; pr->sdx = 1; pr->sdy = 1; }
        else pr->sdx = pr->sdy = 0;
    }
    canvas_close(&c);
    if (n == 0 && ++pr->tries < 30) return;          /* 何も描かれなかった（画面の外など）: 次の機会に調べ直す */
    if (n == 0) { int r; pr->top = -5; pr->bot = F_H(f) * 2 / 3 - 5; pr->left = 0; for (r = 0; r < 48; r++) pr->col[r] = 0xffff; }
    if (g_logon) {
        uint32_t *sp = (uint32_t*)(f + 64 * 8);
        dbg("probe font %d h=%d top=%d bot=%d left=%d n=%d dark=%d shadow=%04x was=%d lk=%p cnt=%d surf=%p x=%d y=%d w=%d h=%d\n", fi, F_H(f), pr->top, pr->bot, pr->left, n, cnt_dark, pr->shadow,
            c.was, *(void**)((uint8_t*)surf + 0x20), *(int*)((uint8_t*)surf + 0x1c), surf, x, y, c.w, c.h);
        dbg("  sprite H: %x %x %x %x | %x %x %x %x | %x %x %x %x | %x %x %x %x\n", sp[0], sp[1], sp[2], sp[3], sp[4], sp[5], sp[6], sp[7], sp[8], sp[9], sp[10], sp[11], sp[12], sp[13], sp[14], sp[15]);
        for (yy = 0; yy < PH; yy++) {
            char line[PW + 1]; int any = 0;
            for (xx = 0; xx < PW; xx++) {
                if (after[yy][xx] == save[yy][xx]) { line[xx] = '.'; continue; }
                any = 1; { int l = lum(&c, after[yy][xx]) * 10 / 2551; line[xx] = (char)('0' + (l > 9 ? 9 : l)); }
            }
            line[PW] = 0;
            if (any) dbg("  %3d %s\n", yy - oy, line);
        }
    }
    pr->done = 1;
}
static uint16_t row_color(probe_t *pr, int r, int gh)
{
    int hh = pr->bot - pr->top + 1, k;
    if (hh < 1) return pr->col[0];
    k = gh > 1 ? r * (hh - 1) / (gh - 1) : 0;
    if (k < 0) k = 0;
    if (k >= hh) k = hh - 1;
    if (k > 47) k = 47;
    return pr->col[k];
}
/* 日本語の字 1 つを (x, y の基準) に書く。字の箱の真ん中を「H」の真ん中にそろえる */
static void put_glyph(canvas_t *c, probe_t *pr, int x, int y, glyph_t *g)
{
    int top = y + (pr->top + pr->bot + 1) / 2 - g->h / 2;
    int r, k, pass;
    for (pass = (pr->sdx || pr->sdy) ? 0 : 1; pass < 2; pass++) {
        int ox = pass ? 0 : pr->sdx, oy = pass ? 0 : pr->sdy;
        for (r = 0; r < g->h; r++) {
            int py = top + r + oy;
            uint16_t col = pass ? row_color(pr, r, g->h) : pr->shadow;
            uint16_t *row;
            if (py < 0 || py >= c->h) continue;
            row = (uint16_t*)(c->p + py * c->pitch);
            for (k = 0; k < g->adv; k++) {
                int a = g->a[r * g->adv + k], px = x + k + ox;
                if (!a || px < 0 || px >= c->w) continue;
                row[px] = a >= 250 ? col : blend(c, col, row[px], a);
            }
        }
    }
}

/* ---- 描く */
static void __fastcall my_draw(F *f, void *edx, void *surf, const char *s, int x, int y, int flags)
{
    const uint8_t *u;
    int fi, cx;
    char tmp[1024];
    if (!g_enabled || !s || !has_jp(s) || (fi = font_index(f)) < 0) { o_draw(f, edx, surf, s, x, y, flags); return; }
    if (g_logon) {
        static void *seen[256]; static int ns; void *ra = _ReturnAddress(); int k;
        for (k = 0; k < ns && seen[k] != ra; k++);
        if (k == ns && ns < 256) { seen[ns++] = ra; dbg("draw from %p font %d len %d x=%d y=%d fl=%x\n", ra, fi, (int)strlen(s), x, y, flags); }
    }
    if (flags & 1) x -= text_width(f, s) / 2;
    else if (flags & 4) x -= text_width(f, s);
    if (!g_pr[fi].done) probe_font(f, fi, surf, x, y);
    if (!g_pr[fi].done) {
        probe_t *p = &g_pr[fi]; int r;
        p->top = -5; p->bot = F_H(f) * 2 / 3 - 5; p->sdx = p->sdy = 0;
        for (r = 0; r < 48; r++) p->col[r] = 0xffff;
    }
    cx = x; u = (const uint8_t*)s;
    while (*u) {
        if (is_jp_at(u)) {
            canvas_t c;
            if (canvas_open(surf, &c)) {
                for (;;) {
                    if (is_jp_at(u)) { glyph_t *g = get_glyph(jp_size(f), jp_char(u)); cx += after_ascii((const uint8_t*)s, u); put_glyph(&c, &g_pr[fi], cx, y, g); cx += g->adv; u += 2; }
                    else if (zw_at((const uint8_t*)s, u) && is_jp_at(u + 1)) u++;
                    else break;
                }
                canvas_close(&c);
            } else while (is_jp_at(u)) { cx += jp_adv(f, u); u += 2; }
        } else if (zw_at((const uint8_t*)s, u) || (IS_LEAD(*u) && !IS_TRAIL(u[1]))) u++;   /* 幅 0 の空白・半分に切られた字 */
        else {
            int n = 0;
            while (u[n] && !is_jp_at(u + n) && !zw_at((const uint8_t*)s, u + n) && !IS_LEAD(u[n]) && n < (int)sizeof tmp - 1) n++;
            memcpy(tmp, u, n); tmp[n] = 0;
            o_draw(f, NULL, surf, tmp, cx, y, flags & ~5);
            cx += text_width_n(f, tmp, n);
            u += n;
        }
    }
}
static int __fastcall my_width(F *f, void *edx, const char *s)
{
    uintptr_t ra = (uintptr_t)_ReturnAddress();
    if (!g_enabled || !s || !has_jp(s)) return o_width(f, edx, s);
    /* 文章の箱（ヘルプなど 0x51ff02）が行に詰めるとき: 表の欄の幅は箱より少し狭いので、余裕を持たせる */
    if (ra >= 0x51ff02 && ra < 0x52038d) return text_width(f, s) + 12;
    return text_width(f, s);
}

/* ---- 折り返し: 空白と「~」（改行）で切り、日本語の字の間でも切る（行頭禁則・行末禁則） */
#define MAXL 64
typedef struct { const char *p; int n; int sp; } atom_t;
static int nobreak_ascii_head(uint8_t c) { return c == ',' || c == '.' || c == '!' || c == '?' || c == ')' || c == ']' || c == ':' || c == ';' || c == '%'; }
static int split_lines(F *f, const char *s, int maxw, char *buf, int cap, const char **lines)
{
    static atom_t at[1024];
    int na = 0, i, nl = 0, lw = 0, pos = 0, brk = 0, sp = 0, glue = 0, linestart = 1;
    const uint8_t *u = (const uint8_t*)s;
    int spw = ascii_w(f, ' ');
    /* 1. 切れない塊に分ける（sp: 1 = 前に空白、-1 = 前で改行） */
    while (*u && na < 1024) {
        const uint8_t *st;
        int headnb, tailnb;
        if (*u == ' ') { sp = 1; u++; continue; }
        if (*u == '~') { brk = 1; u++; continue; }
        st = u;
        if (is_jp_at(u)) { headnb = jp_kin(u) & 1; tailnb = (jp_kin(u) & 2) != 0; u += 2; }
        else {
            headnb = nobreak_ascii_head(*u);
            while (*u && *u != ' ' && *u != '~' && !is_jp_at(u)) u++;
            tailnb = (u[-1] == '(' || u[-1] == '[' || u[-1] == '"');
        }
        if (na && !sp && !brk && (headnb || glue)) at[na - 1].n = (int)((const char*)u - at[na - 1].p);
        else { at[na].p = (const char*)st; at[na].n = (int)(u - st); at[na].sp = brk ? -1 : sp; na++; }
        glue = tailnb; sp = 0; brk = 0;
    }
    /* 2. 行に詰める */
    for (i = 0; i < na; i++) {
        int w = text_width_n(f, at[i].p, at[i].n);
        int need = (!linestart && at[i].sp == 1) ? spw : 0;
        if (need && is_jp_at((const uint8_t*)at[i].p) && i && at[i - 1].n >= 2 && is_jp_at((const uint8_t*)at[i - 1].p + at[i - 1].n - 2)) need = 0;
        if (!linestart && (at[i].sp < 0 || lw + need + w > maxw)) {
            if (pos < cap) buf[pos++] = 0;
            linestart = 1; lw = 0; need = 0;
        }
        if (linestart) { if (nl >= MAXL) break; lines[nl++] = buf + pos; linestart = 0; }
        if (need && pos < cap - 1) buf[pos++] = ' ';
        if (pos + at[i].n < cap - 1) { memcpy(buf + pos, at[i].p, at[i].n); pos += at[i].n; }
        lw += need + w;
    }
    if (pos < cap) buf[pos++] = 0;
    buf[cap - 1] = 0;
    return nl;
}
static int wrap_y0(F *f, RECT *rc, int flags, int n)
{
    int h = F_H(f), adv = h + h / 3;
    if (flags & 1) return (rc->top + (rc->bottom - rc->top) / 2) - (adv * n) / 2;
    return rc->top + h / 2 + h;
}
static void __fastcall my_wrap(F *f, void *edx, void *surf, const char *s, RECT *rc, int flags)
{
    static char buf[8192]; const char *L[MAXL];
    int W, n, i, x, y, h, fi;
    if (!g_enabled || !s || !*s || !has_jp(s)) { o_wrap(f, edx, surf, s, rc, flags); return; }
    W = rc->right - rc->left;
    x = rc->left + ((flags & 1) ? W / 2 : 0);
    if (text_width(f, s) <= W && !strchr(s, '~')) { my_draw(f, NULL, surf, s, x, rc->top + (rc->bottom - rc->top) / 2, flags); return; }
    n = split_lines(f, s, W, buf, sizeof buf, L);
    h = F_H(f); y = wrap_y0(f, rc, flags, n);
    fi = font_index(f);
    if (fi >= 4 && fi <= 7) y += 4;
    for (i = 0; i < n; i++) { my_draw(f, NULL, surf, L[i], x, y, flags); y += h + h / 3; }
}
static void __fastcall my_wrap2(F *f, void *edx, void *surf, const char *s, RECT *rc, int skip, int flags)
{
    static char buf[8192]; const char *L[MAXL];
    int W, n, i, x, y, h;
    if (!g_enabled || !s || !*s || !has_jp(s)) { o_wrap2(f, edx, surf, s, rc, skip, flags); return; }
    W = rc->right - rc->left;
    x = rc->left + ((flags & 1) ? W / 2 : 0);
    if (text_width(f, s) <= W) { my_draw(f, NULL, surf, s, x, rc->top + (rc->bottom - rc->top) / 2, flags); return; }
    n = split_lines(f, s, W, buf, sizeof buf, L);
    h = F_H(f); y = wrap_y0(f, rc, flags, n);
    for (i = 0; i < n; i++) {
        if (skip > 0) { skip--; continue; }
        if (i == n - 1 && rc->bottom <= y) break;
        my_draw(f, NULL, surf, L[i], x, y, flags); y += h + h / 3;
    }
}
static int __fastcall my_count(F *f, void *edx, void *a1, const char *s, RECT *rc, int flags)
{
    static char buf[8192]; const char *L[MAXL];
    int W;
    if (!g_enabled || !s || !*s || !has_jp(s)) return o_count(f, edx, a1, s, rc, flags);
    W = rc->right - rc->left;
    if (text_width(f, s) <= W) return 1;
    return split_lines(f, s, W, buf, sizeof buf, L);
}

/* ============================================================ 色を指定する小さい字（メニューのボタンなど）
 *   描く 0x5ffb2f (面, 文, x, y, 色, 揃え)  打ち出し 0x5ffe4e (面, 文, x, y, 色, 描く字の数, 揃え)  幅 0x5ffb06 (文)
 *   いずれも cdecl。英数字の幅は 0x6175e7 (文, 字数)。字の高さは 6〜7 ドットで、y が字の上。
 */
#define A_CDRAW  0x5ffb2f
#define A_CDRAW2 0x5ffe4e
#define A_CWIDTH 0x5ffb06
#define A_CWN    0x6175e7
#define C_JPSIZE 10
typedef void (__cdecl *cdraw_t)(void*, const char*, int, int, int, int);
typedef void (__cdecl *cdraw2_t)(void*, const char*, int, int, int, int, int);
typedef int  (__cdecl *cwidth_t)(const char*);
typedef int  (__cdecl *cwn_t)(const char*, int);
static cdraw_t o_cdraw; static cdraw2_t o_cdraw2; static cwidth_t o_cwidth;
#define c_wn ((cwn_t)A_CWN)
static int c_text_width(const char *s, int n)
{
    const uint8_t *u = (const uint8_t*)s;
    int w = 0, i = 0;
    while (u[i] && (n < 0 || i < n)) {
        if (is_jp_at(u + i)) { w += get_glyph(C_JPSIZE, jp_char(u + i))->adv + after_ascii(u, u + i); i += 2; }
        else if (zw_at(u, u + i)) i++;
        else { int k = 0; while (u[i + k] && (n < 0 || i + k < n) && !is_jp_at(u + i + k) && !zw_at(u, u + i + k)) k++; w += c_wn(s + i, k); i += k; }
    }
    return w;
}
static int __cdecl my_cwidth(const char *s)
{
    if (!g_enabled || !s || !has_jp(s)) return o_cwidth(s);
    return c_text_width(s, -1);
}
/* 文の先頭 lim バイト（-1 = 全部）を描く */
static void c_draw_jp(void *surf, const char *s, int x, int y, int color, int lim, int flags)
{
    const uint8_t *u = (const uint8_t*)s;
    int i = 0, cx, n = (int)strlen(s);
    char tmp[1024];
    if (lim >= 0 && lim < n) n = lim;
    if (flags & 1) { x -= c_text_width(s, -1) / 2; y -= 2; }
    else if (flags & 4) x -= c_text_width(s, -1);
    cx = x;
    while (i < n) {
        if (is_jp_at(u + i)) {
            canvas_t c;
            if (canvas_open(surf, &c)) {
                probe_t pr; int r;
                memset(&pr, 0, sizeof pr);
                pr.top = 0; pr.bot = 6;
                for (r = 0; r < 48; r++) pr.col[r] = (uint16_t)color;
                while (i < n && is_jp_at(u + i)) {
                    glyph_t *g = get_glyph(C_JPSIZE, jp_char(u + i));
                    cx += after_ascii(u, u + i);
                    put_glyph(&c, &pr, cx, y, g); cx += g->adv; i += 2;
                }
                canvas_close(&c);
            } else while (i < n && is_jp_at(u + i)) { cx += get_glyph(C_JPSIZE, jp_char(u + i))->adv; i += 2; }
        } else if (zw_at(u, u + i)) i++;
        else {
            int k = 0;
            while (i + k < n && !is_jp_at(u + i + k) && !zw_at(u, u + i + k) && k < (int)sizeof tmp - 1) k++;
            memcpy(tmp, s + i, k); tmp[k] = 0;
            o_cdraw(surf, tmp, cx, y, color, flags & ~5);
            cx += c_wn(tmp, k);
            i += k;
        }
    }
}
static void __cdecl my_cdraw(void *surf, const char *s, int x, int y, int color, int flags)
{
    if (!g_enabled || !s || !has_jp(s)) { o_cdraw(surf, s, x, y, color, flags); return; }
    c_draw_jp(surf, s, x, y, color, -1, flags);
}
static void __cdecl my_cdraw2(void *surf, const char *s, int x, int y, int color, int lim, int flags)
{
    if (!g_enabled || !s || !has_jp(s)) { o_cdraw2(surf, s, x, y, color, lim, flags); return; }
    c_draw_jp(surf, s, x, y, color, lim, flags);
}

/* ---- 長すぎる文を「...」で切る 0x5eb776 (フォント, 文, 幅) cdecl。元はバイト単位で削るので、日本語の字の途中で切れないようにする */
#define A_ELLIP 0x5eb776
typedef char *(__cdecl *ellip_t)(F*, const char*, int);
static ellip_t o_ellip;
static char *__cdecl my_ellip(F *f, const char *s, int maxw)
{
    static char buf[4096];
    int n, k, last;
    if (!g_enabled || !s || !has_jp(s)) return o_ellip(f, s, maxw);
    lstrcpynA(buf, s, sizeof buf - 4);
    if (text_width(f, buf) <= maxw) return buf;
    n = (int)strlen(buf);
    while (n > 0) {
        /* n の手前の字の頭を探す */
        for (k = 0, last = 0; k < n; ) { last = k; k += is_jp_at((const uint8_t*)buf + k) ? 2 : 1; }
        n = last;
        while (n > 0 && buf[n - 1] == ' ') n--;
        memcpy(buf + n, "...", 4);
        if (text_width(f, buf) <= maxw) return buf;
    }
    buf[0] = 0;
    return buf;
}

/* ---- 日付 0x412806: sprintf(buf, "%s %02d, %04d", 月, 日, 年) の呼び出しを差し替え、「2067年1月1日」にする */
#define A_DATECALL 0x412806
static int enc_char(wchar_t w, char *o)      /* Unicode → 独自の符号（2 バイト）。無ければ 0 */
{
    int i;
    for (i = 0; i < 0x2000; i++) if (g_uni[i] == w) { o[0] = (char)(0x80 + (i >> 8)); o[1] = (char)(i & 0xff); o[2] = 0; return 1; }
    return 0;
}
static int __cdecl my_datefmt(char *buf, const char *fmt, const char *mon, int day, int year)
{
    static char nen[3], nichi[3]; static int ok = -1;
    (void)fmt;
    if (ok < 0) ok = enc_char(0x5e74, nen) && enc_char(0x65e5, nichi);
    if (g_enabled && ok > 0 && mon && has_jp(mon)) return wsprintfA(buf, "%d%s%s%d%s", year, nen, mon, day, nichi);
    return wsprintfA(buf, "%s %02d, %04d", mon, day, year);
}
static void patch_call(uintptr_t at, void *to)
{
    uint8_t *p = (uint8_t*)at;
    DWORD old;
    if (p[0] != 0xe8) { dbg("not a call at %08x\n", (unsigned)at); return; }
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    *(int32_t*)(p + 1) = (int32_t)((uint8_t*)to - (p + 5));
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
}

/* ---- ゲームの関数の入口に jmp を書く（元の入口の命令は写して戻り口を作る） */
static void *hook_code(uintptr_t at, int steal, const uint8_t *expect, void *to)
{
    uint8_t *p = (uint8_t*)at, *t;
    DWORD old;
    if (memcmp(p, expect, steal)) { dbg("unexpected bytes at %08x\n", (unsigned)at); return NULL; }
    t = (uint8_t*)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, p, steal);
    t[steal] = 0xe9; *(int32_t*)(t + steal + 1) = (int32_t)((p + steal) - (t + steal + 5));
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int32_t*)(p + 1) = (int32_t)((uint8_t*)to - (p + 5));
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    return t;
}
static const uint8_t X_DRAW[]  = {0x55, 0x8b, 0xec, 0xb8, 0x48, 0x10, 0x00, 0x00};
static const uint8_t X_WIDTH[] = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x0c};
static const uint8_t X_WRAP[]  = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x48};
static const uint8_t X_CDRAW[]  = {0x55, 0x8b, 0xec, 0xb8, 0x38, 0x10, 0x00, 0x00};
static const uint8_t X_CWIDTH[] = {0x55, 0x8b, 0xec, 0x53, 0x56, 0x57};
static const uint8_t X_ELLIP[]  = {0x55, 0x8b, 0xec, 0x83, 0xec, 0x08};
static volatile LONG g_game_hooked;
static void hook_game(void)
{
    if (g_game_hooked || !g_enabled) return;
    if (IsBadReadPtr((void*)A_DRAW, 8) || memcmp((void*)A_DRAW, X_DRAW, 8)) return;   /* まだ DRM がコードを戻していない */
    if (memcmp((void*)A_WIDTH, X_WIDTH, 6) || memcmp((void*)A_WRAP, X_WRAP, 6) || memcmp((void*)A_WRAP2, X_WRAP, 6) || memcmp((void*)A_COUNT, X_WRAP, 6)) {
        dbg("game code differs, sprite font hooks not installed\n"); g_game_hooked = 1; return;
    }
    if (InterlockedExchange(&g_game_hooked, 1)) return;
    o_draw  = (draw_t) hook_code(A_DRAW, 8, X_DRAW, (void*)my_draw);
    o_width = (width_t)hook_code(A_WIDTH, 6, X_WIDTH, (void*)my_width);
    o_wrap  = (wrap_t) hook_code(A_WRAP, 6, X_WRAP, (void*)my_wrap);
    o_wrap2 = (wrap2_t)hook_code(A_WRAP2, 6, X_WRAP, (void*)my_wrap2);
    o_count = (count_t)hook_code(A_COUNT, 6, X_WRAP, (void*)my_count);
    if (!memcmp((void*)A_CDRAW, X_CDRAW, 8) && !memcmp((void*)A_CDRAW2, X_CDRAW, 8) && !memcmp((void*)A_CWIDTH, X_CWIDTH, 6)) {
        o_cdraw  = (cdraw_t) hook_code(A_CDRAW, 8, X_CDRAW, (void*)my_cdraw);
        o_cdraw2 = (cdraw2_t)hook_code(A_CDRAW2, 8, X_CDRAW, (void*)my_cdraw2);
        o_cwidth = (cwidth_t)hook_code(A_CWIDTH, 6, X_CWIDTH, (void*)my_cwidth);
    } else dbg("small font code differs\n");
    if (*(uint8_t*)A_DATECALL == 0xe8 && *(int32_t*)(A_DATECALL + 1) == 0x23b085) patch_call(A_DATECALL, (void*)my_datefmt);
    if (!memcmp((void*)A_ELLIP, X_ELLIP, 6)) o_ellip = (ellip_t)hook_code(A_ELLIP, 6, X_ELLIP, (void*)my_ellip);
    dbg("game hooks %p %p %p %p %p\n", o_draw, o_width, o_wrap, o_wrap2, o_count);
}
