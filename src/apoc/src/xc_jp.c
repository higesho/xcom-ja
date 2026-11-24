/*
 * X-COM: Apocalypse 日本語化パッチ（実行時部分）
 * Steam 版の DOSBox 0.72 に winmm.dll の代理として読み込まれる。ゲームのファイルは書き換えない。
 * DOSBox がゲームのファイルを開くとき（fopen）に、次のものは %LOCALAPPDATA%\XC_JP_APOC に作ったコピーを渡す:
 *   UFOEXE\UFO2P.EXE / TACEXE\TACP.EXE  文字の描画の関数の入口などに DOSBox のコールバック（FE 38 nn 00）を置き、
 *                                       データの段を広げたもの（広げた所に日本語の文字列を置く）
 *   UFOPAEDI\PAEDIA.MT / PAEDIA.MTI     UFOペディアの日本語の文章
 * EXE の文字列は、起動の直後（sti; and esp,-4 の所）のコールバックで、日本語の文字列の束を広げた所に書き、
 * その文字列を指していたすべての場所（LE の fixup の位置）を書き換える。
 * 日本語の符号: 1 バイト目 0x80-0x9F、2 バイト目 0xA0-0xFF（0xE1 を除く）。字形は DLL が描く（小: 東雲 12、大: 東雲 16）。
 * 日本語の字の直後の空白は、次が日本語の字なら幅 0（折り返しの切れ目）。折り返しのある描画では、入口で日本語の字の間にこの空白を足す。
 */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "resource.h"

void proxy_init(void);
#ifdef XC_TEST
void testio_init(void);
void testio_mouse(int x, int y);
#endif

static char g_dir[MAX_PATH];
#ifdef XC_TEST
/* 試験版だけ: 環境変数 XC_LOG があれば g_dir\log.txt に記録する */
static FILE *g_log;
static int g_logon;
static void dbg(const char *fmt, ...)
{
    va_list ap;
    if (!g_logon) return;
    if (!g_log) {
        char p[MAX_PATH];
        wsprintfA(p, "%s\\log.txt", g_dir);
        g_log = fopen(p, "a");
        if (!g_log) return;
    }
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fflush(g_log);
}
#else
#define dbg(...) ((void)0)
#endif

/* ------------------------------------------------ DOSBox 0.72（Steam 版、md5 cacb05c2）の中身 */
#define A_CB_HANDLERS 0x6d1430u
#define A_CB_ILLEGAL 0x408360u
#define A_REGS 0x6d11d0u
#define A_SEGPHYS 0x6d1110u
#define A_TLB_READ 0x6d16a0u
#define A_TLB_WRITE 0xad16a0u
#define A_TLB_HANDLER 0xed16a0u
#define CB_MAX 128
typedef uint32_t (__cdecl *ph_rb)(void *self, uint32_t a);
typedef void (__cdecl *ph_wb)(void *self, uint32_t a, uint32_t v);
static int verify_dosbox(void)
{
    static const uint8_t s1[] = {0x81, 0x3c, 0x85, 0x30, 0x14, 0x6d, 0x00, 0x60, 0x83, 0x40, 0x00};   /* CALLBACK_Allocate */
    static const uint8_t s2[] = {0x89, 0x14, 0x85, 0xa0, 0x16, 0x6d, 0x00};                          /* paging.tlb.read */
    static const uint8_t s3[] = {0x89, 0x34, 0xbd, 0x10, 0x11, 0x6d, 0x00};                          /* Segs.phys */
    static const uint8_t s4[] = {0x89, 0x0d, 0xf0, 0x11, 0x6d, 0x00};                                /* reg_eip */
    MEMORY_BASIC_INFORMATION mi;
    if ((uintptr_t)GetModuleHandleA(NULL) != 0x400000) return 0;
    if (!VirtualQuery((void*)0x408396, &mi, sizeof mi) || mi.State != MEM_COMMIT) return 0;
    return !memcmp((void*)0x408396, s1, sizeof s1) && !memcmp((void*)0x40a1f4, s2, sizeof s2) &&
           !memcmp((void*)0x402bcd, s3, sizeof s3) && !memcmp((void*)0x403565, s4, sizeof s4);
}
static __inline uint8_t rb(uint32_t a)
{
    uint8_t *p = ((uint8_t**)A_TLB_READ)[a >> 12];
    void *h;
    if (p) return p[a];
    h = ((void**)A_TLB_HANDLER)[a >> 12];
    return (uint8_t)((ph_rb)((*(void***)h)[2]))(h, a);
}
static __inline void wb(uint32_t a, uint8_t v)
{
    uint8_t *p = ((uint8_t**)A_TLB_WRITE)[a >> 12];
    void *h;
    if (p) { p[a] = v; return; }
    h = ((void**)A_TLB_HANDLER)[a >> 12];
    ((ph_wb)((*(void***)h)[5]))(h, a, v);
}
static __inline uint32_t rd(uint32_t a) { return rb(a) | (rb(a + 1) << 8) | (rb(a + 2) << 16) | ((uint32_t)rb(a + 3) << 24); }
static __inline void wd(uint32_t a, uint32_t v) { wb(a, (uint8_t)v); wb(a + 1, (uint8_t)(v >> 8)); wb(a + 2, (uint8_t)(v >> 16)); wb(a + 3, (uint8_t)(v >> 24)); }
static __inline uint16_t rw(uint32_t a) { return (uint16_t)(rb(a) | (rb(a + 1) << 8)); }
static __inline void ww(uint32_t a, uint16_t v) { wb(a, (uint8_t)v); wb(a + 1, (uint8_t)(v >> 8)); }
#define REG32(i) (((uint32_t*)A_REGS)[i])
#define R_EAX REG32(0)
#define R_ECX REG32(1)
#define R_EDX REG32(2)
#define R_EBX REG32(3)
#define R_ESP REG32(4)
#define R_EBP REG32(5)
#define R_ESI REG32(6)
#define R_EDI REG32(7)
#define R_EIP REG32(8)
#define PHYS_SS (((uint32_t*)A_SEGPHYS)[2])
static __inline void push32(uint32_t v) { R_ESP -= 4; wd(PHYS_SS + R_ESP, v); }
static __inline uint32_t pop32(void) { uint32_t v = rd(PHYS_SS + R_ESP); R_ESP += 4; return v; }

/* ------------------------------------------------------- パッチデータ
 * 'XCJ1', 節の数, 節 {u8 種類, u32 長さ, 中身}
 *  'G' 字形: u32 件数, {u16 符号, u8 禁則（1 行頭に来ない 2 行末に来ない）, u8 0, u16 小[12]（12x12）, u16 大[16]（16x16）, u8 極小[8]（8x8）}
 *  'F' ファイルの差し替え: u8 名前の長さ, 名前（大文字の基本名）, u32 元の大きさ（0 = 見ない）, u32 大きさ, 中身
 *  'E' EXE の書き換え: u8 名前の長さ, 名前, u32 元の大きさ, u32 件数, {u32 位置, u16 長さ, 元[長さ], 新[長さ]}
 *  'X' EXE ごとの番地: u8 種類（0 UFO2P 1 TACP）, u32 値[NX]（リンク時の番地）
 *  'S' EXE ごとの文字列: u8 種類, u32 束の長さ, 束, u32 件数, {u32 位置（リンク時）, u8 段（0 コード 1 データ）, u32 束の中の位置}
 */
enum { X_F1, X_SMALL, X_BIG, X_FONT1, X_SMALLW, X_BIGW, X_F1W, X_ENTRY,    /* コールバックの位置（FE 38 の位置） */
       X_F1WCONT, X_F1WEBP, X_F1SUB,                                      /* 折り返しの中の幅: 続きの番地、ebp に字を入れるか、入口の sub esp の値 */
       X_DREF, X_DVAL,                                                    /* データの番地のずれを求める: 命令の中の番地の場所とその値 */
       X_CUR, X_SCREEN, X_CLIP, X_KERN, X_COLT, X_MAXR, X_F1PTR, X_WTAB1, X_POOL, X_SCRATCH, NX };
#define NCB 8
static uint32_t g_x[2][NX];
static const uint8_t *g_blob;
static uint32_t g_blob_len, g_blob_crc;
static int g_cb_base = -1;
static int g_enabled;
typedef struct { uint8_t flags; uint16_t sm[12]; uint16_t bg[16]; uint8_t ti[8]; int ok; } glyph_t;
static glyph_t *g_gl;                     /* [lead-0x80][trail] → 0x2000 個 */
#define GL(l, t) (&g_gl[(((l) - 0x80) << 8) | (t)])
#define IS_LEAD(c) ((c) >= 0x80 && (c) < 0xa0)
#define IS_TRAIL(c) ((c) >= 0xa0)
typedef struct { char name[16]; uint32_t osize, size; const uint8_t *data; } frep_t;
static frep_t g_frep[8]; static int g_nfrep;
typedef struct { char name[16]; const uint8_t *p; } epatch_t;
static epatch_t g_ep[4]; static int g_nep;
typedef struct { uint32_t len; const uint8_t *pool; uint32_t n; const uint8_t *sites; } spool_t;
static spool_t g_sp[2];

static uint32_t crc32(const uint8_t *p, uint32_t n)
{
    uint32_t c = 0xffffffffu, k;
    while (n--) { c ^= *p++; for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1))); }
    return ~c;
}
static int load_blob(HMODULE self)
{
    HRSRC r = FindResourceA(self, MAKEINTRESOURCEA(IDR_PATCH), (LPCSTR)RT_RCDATA);
    const uint8_t *p;
    uint32_t ns, i;
    if (!r) return 0;
    g_blob = (const uint8_t*)LockResource(LoadResource(self, r));
    g_blob_len = SizeofResource(self, r);
    if (!g_blob || g_blob_len < 8 || memcmp(g_blob, "XCJ1", 4)) return 0;
    g_blob_crc = crc32(g_blob, g_blob_len) ^ 0x1u;    /* 末尾の数 = DLL のコードの版 */
    g_gl = (glyph_t*)calloc(0x2000, sizeof(glyph_t));
    ns = *(const uint32_t*)(g_blob + 4);
    p = g_blob + 8;
    for (i = 0; i < ns && p + 5 <= g_blob + g_blob_len; i++) {
        uint8_t t = p[0];
        uint32_t len = *(const uint32_t*)(p + 1), k;
        const uint8_t *d = p + 5;
        if (t == 'G') {
            uint32_t n = *(const uint32_t*)d;
            const uint8_t *q = d + 4;
            for (k = 0; k < n; k++, q += 68) {
                uint16_t c = *(const uint16_t*)q;
                glyph_t *g;
                if ((c >> 8) < 0x80 || (c >> 8) >= 0xa0) continue;
                g = GL(c >> 8, c & 0xff);
                g->flags = q[2]; memcpy(g->sm, q + 4, 24); memcpy(g->bg, q + 28, 32); memcpy(g->ti, q + 60, 8); g->ok = 1;
            }
        } else if (t == 'F' && g_nfrep < 8) {
            frep_t *f = &g_frep[g_nfrep++];
            memcpy(f->name, d + 1, d[0]); f->name[d[0]] = 0;
            f->osize = *(const uint32_t*)(d + 1 + d[0]); f->size = *(const uint32_t*)(d + 5 + d[0]); f->data = d + 9 + d[0];
        } else if (t == 'E' && g_nep < 4) {
            epatch_t *e = &g_ep[g_nep++];
            memcpy(e->name, d + 1, d[0]); e->name[d[0]] = 0;
            e->p = d + 1 + d[0];
        } else if (t == 'X' && d[0] < 2) memcpy(g_x[d[0]], d + 1, sizeof g_x[0]);
        else if (t == 'S' && d[0] < 2) {
            spool_t *s = &g_sp[d[0]];
            s->len = *(const uint32_t*)(d + 1); s->pool = d + 5;
            s->n = *(const uint32_t*)(d + 5 + s->len); s->sites = d + 9 + s->len;
        }
        p = d + len;
    }
    return g_nep > 0;
}

/* ------------------------------------------------------------ 実行時の番地 */
static int g_k;                         /* 今のコールバックの EXE（0 UFO2P 1 TACP） */
static uint32_t g_cd, g_dd;             /* コードとデータの番地のずれ */
static void set_k(int k, int site)
{
    g_k = k;
    g_cd = R_EIP - (g_x[k][site] + 4);
    g_dd = rd(g_x[k][X_DREF] + g_cd) - g_x[k][X_DVAL];
}
#define DA(f) (g_x[g_k][f] + g_dd)
static void ret_near(void) { R_EIP = pop32(); }

/* ------------------------------------------------------------ 字を描く（640x480、画面の切り抜き [CLIP] x0,y0,x1,y1） */
#define SCR_W 640
static uint32_t g_scr; static int g_cx0, g_cy0, g_cx1, g_cy1;
static void begin_draw(void)
{
    uint32_t c = DA(X_CLIP);
    g_scr = rd(DA(X_SCREEN));
    g_cx0 = (int16_t)rw(c); g_cy0 = (int16_t)rw(c + 2); g_cx1 = (int16_t)rw(c + 4); g_cy1 = (int16_t)rw(c + 6);
}
static void put_px(uint32_t dst, int dx, int dy, uint8_t v)
{
    int32_t off = (int32_t)(dst - g_scr);
    int x, y;
    if (off < 0) return;
    x = off % SCR_W + dx; y = off / SCR_W + dy;
    if (x < g_cx0 || x >= g_cx1 || y < g_cy0 || y >= g_cy1) return;
    wb(g_scr + (uint32_t)(y * SCR_W + x), v);
}
#define SMALL_ADV 13
#define BIG_ADV 17
#define TINY_ADV 9
#define SMALL_ROWS 15
#define BIG_ROWS 12
#define SMALL_SPACE 6
#define BIG_SPACE 12
static void draw_small_jp(uint32_t dst, const glyph_t *g, uint8_t v)
{
    int r, c;
    begin_draw();
    for (r = 0; r < 12; r++) for (c = 0; c < 12; c++)
        if ((g->sm[r] >> (15 - c)) & 1) put_px(dst, c, r + 2, v);
}
static void draw_tiny_jp(uint32_t dst, const glyph_t *g, uint8_t v)
{
    int r, c;
    begin_draw();
    for (r = 0; r < 8; r++) for (c = 0; c < 8; c++)
        if ((g->ti[r] >> (7 - c)) & 1) put_px(dst, c, r + 1, v);
}
static void draw_big_jp(uint32_t dst, const glyph_t *g, uint8_t col)
{
    static const uint8_t shade[16] = {0xd, 0xd, 0xd, 0xd, 0xd, 0xd, 0xc, 0xc, 0xc, 0xc, 0xc, 0xb, 0xb, 0xb, 0xb, 0xb};
    int r, c;
    begin_draw();
    for (r = 0; r < 16; r++) for (c = 0; c < 16; c++)
        if ((g->bg[r] >> (15 - c)) & 1) put_px(dst, c, r + 5, (uint8_t)(shade[r] + col - 1));
}

/* 状態: 描く側と幅を測る側で別に持つ（1 バイト目の保留、直前が日本語の字か、保留中の空白の幅） */
typedef struct { uint8_t lead; uint8_t prevjp; uint8_t pend; } jst;
static jst g_ds, g_bs, g_ws, g_bws, g_fs;
static void reset_states(void) { memset(&g_ds, 0, sizeof g_ds); g_bs = g_ws = g_bws = g_fs = g_ds; }

/* 前の字の右の形（[KERN] rows 段）から、次の字を置く位置までのずれ */
static uint32_t kern_max(int rows)
{
    uint32_t k = DA(X_KERN), w = 0; int b;
    for (b = 0; b < rows; b++) if (rb(k + b) > w) w = rb(k + b);
    return w;
}
static void kern_set(int rows, uint8_t v) { uint32_t k = DA(X_KERN); int b; for (b = 0; b < rows; b++) wb(k + b, v); }
static void kern_add(int rows, uint8_t v) { uint32_t k = DA(X_KERN); int b; for (b = 0; b < rows; b++) wb(k + b, (uint8_t)(rb(k + b) + v)); }

/* 1: 小さい字（push ecx; push esi; push edi; push ebp; sub esp,20h の代わり）。al = 字, dl = 色, ebx = 描く所。ずれを返し [CUR] に足す */
static uint32_t __cdecl cb_small(int k)
{
    uint8_t c = (uint8_t)R_EAX, col = (uint8_t)R_EDX;
    uint32_t dst = R_EBX, w = 0;
    set_k(k, X_SMALL);
    if (IS_LEAD(c)) { g_ds.lead = c; goto done; }
    if (IS_TRAIL(c) && g_ds.lead) {
        glyph_t *g = GL(g_ds.lead, c);
        g_ds.lead = 0; g_ds.pend = 0;
        w = kern_max(SMALL_ROWS);
        if (g->ok) draw_small_jp(dst + w, g, rb(DA(X_COLT) + col * 3 + 1));
        kern_set(SMALL_ROWS, SMALL_ADV);
        g_ds.prevjp = 1; goto done;
    }
    g_ds.lead = 0;
    if (c == ' ' && g_ds.prevjp) { g_ds.prevjp = 0; g_ds.pend = SMALL_SPACE; goto done; }
    g_ds.prevjp = 0;
    if (g_ds.pend) { R_EBX += g_ds.pend; wd(DA(X_CUR), rd(DA(X_CUR)) + g_ds.pend); g_ds.pend = 0; }
    push32(R_ECX); push32(R_ESI); push32(R_EDI); push32(R_EBP); R_ESP -= 0x20;
    return 0;
done:
    wd(DA(X_CUR), rd(DA(X_CUR)) + w);
    R_EAX = w;
    ret_near();
    return 0;
}
/* 2: 大きい字（入口は小さい字と同じ命令） */
static uint32_t __cdecl cb_big(int k)
{
    uint8_t c = (uint8_t)R_EAX, col = (uint8_t)R_EDX;
    uint32_t dst = R_EBX, w = 0;
    set_k(k, X_BIG);
    if (IS_LEAD(c)) { g_bs.lead = c; goto done; }
    if (IS_TRAIL(c) && g_bs.lead) {
        glyph_t *g = GL(g_bs.lead, c);
        g_bs.lead = 0; g_bs.pend = 0;
        w = kern_max(BIG_ROWS);
        if (g->ok) draw_big_jp(dst + w, g, col);
        kern_set(BIG_ROWS, BIG_ADV);
        g_bs.prevjp = 1; goto done;
    }
    g_bs.lead = 0;
    if (c == ' ' && g_bs.prevjp) { g_bs.prevjp = 0; g_bs.pend = BIG_SPACE; goto done; }
    g_bs.prevjp = 0;
    if (g_bs.pend) { R_EBX += g_bs.pend; wd(DA(X_CUR), rd(DA(X_CUR)) + g_bs.pend); g_bs.pend = 0; }
    push32(R_ECX); push32(R_ESI); push32(R_EDI); push32(R_EBP); R_ESP -= 0x20;
    return 0;
done:
    wd(DA(X_CUR), rd(DA(X_CUR)) + w);
    R_EAX = w;
    ret_near();
    return 0;
}
/* 3: もう一つの小さい字（固定の幅の表 [WTAB1]）。push ecx; push esi; push edi; sub esp,4 の代わり */
static uint32_t __cdecl cb_font1(int k)
{
    uint8_t c = (uint8_t)R_EAX, col = (uint8_t)R_EDX;
    uint32_t dst = R_EBX, w = 0;
    set_k(k, X_FONT1);
    if (IS_LEAD(c)) { g_fs.lead = c; goto done; }
    if (IS_TRAIL(c) && g_fs.lead) {
        glyph_t *g = GL(g_fs.lead, c);
        g_fs.lead = 0; g_fs.pend = 0;
        if (g->ok) draw_tiny_jp(dst, g, rb(DA(X_COLT) + col * 3 + 1));
        g_fs.prevjp = 1; w = TINY_ADV; goto done;
    }
    g_fs.lead = 0;
    if (c == ' ' && g_fs.prevjp) { g_fs.prevjp = 0; g_fs.pend = rb(DA(X_WTAB1) + ' '); goto done; }
    g_fs.prevjp = 0;
    if (g_fs.pend) { R_EBX += g_fs.pend; wd(DA(X_CUR), rd(DA(X_CUR)) + g_fs.pend); g_fs.pend = 0; }
    push32(R_ECX); push32(R_ESI); push32(R_EDI); R_ESP -= 4;
    return 0;
done:
    wd(DA(X_CUR), rd(DA(X_CUR)) + w);
    R_EAX = w;
    ret_near();
    return 0;
}
/* 4, 5: 字の幅（push ebx; push ecx; push edx; push esi; push edi の代わり）。前の字の右の形から求めたずれを返す。[MAXR] = 右の形の最大
 *    保留した空白は、次の字の前に前の字の右の形を広げて足す */
static uint32_t width_cb(jst *s, int rows, uint8_t adv, uint8_t space)
{
    uint8_t c = (uint8_t)R_EAX;
    uint32_t w = 0;
    if (IS_LEAD(c)) { s->lead = c; goto done; }
    if (IS_TRAIL(c) && s->lead) {
        s->lead = 0; s->pend = 0;
        w = kern_max(rows);
        kern_set(rows, adv);
        ww(DA(X_MAXR), adv);
        s->prevjp = 1; goto done;
    }
    s->lead = 0;
    if (c == ' ' && s->prevjp) { s->prevjp = 0; s->pend = space; goto done; }
    s->prevjp = 0;
    if (s->pend) { kern_add(rows, s->pend); s->pend = 0; }
    push32(R_EBX); push32(R_ECX); push32(R_EDX); push32(R_ESI); push32(R_EDI);
    return 0;
done:
    R_EAX = w;
    ret_near();
    return 0;
}
static uint32_t __cdecl cb_smallw(int k) { set_k(k, X_SMALLW); return width_cb(&g_ws, SMALL_ROWS, SMALL_ADV, SMALL_SPACE); }
static uint32_t __cdecl cb_bigw(int k) { set_k(k, X_BIGW); return width_cb(&g_bws, BIG_ROWS, BIG_ADV, BIG_SPACE); }

/* 6: 折り返しの描画の中の、もう一つの小さい字の幅（表を引く所）。字の場所は [F1PTR]。続きの番地へ飛ぶ */
static uint32_t __cdecl cb_f1w(int k)
{
    uint32_t p, w;
    uint8_t c, n;
    set_k(k, X_F1W);
    p = rd(DA(X_F1PTR)); c = rb(p);
    if (IS_LEAD(c)) w = 0;
    else if (IS_TRAIL(c)) w = TINY_ADV;
    else if (c == ' ' && IS_TRAIL(rb(p - 1)) && ((n = rb(p + 1)), IS_LEAD(n) || n < 0x20)) w = 0;
    else w = rb(DA(X_WTAB1) + c);
    if (g_x[k][X_F1WEBP]) R_EBP = c;
    R_EAX = w;
    R_EIP = g_x[k][X_F1WCONT] + g_cd;
    return 0;
}

/* 0: 折り返しのある描画の入口（push esi; push edi; push ebp; sub esp,N の代わり）。eax = 文字列
 *    日本語の字があれば、字の間に切れ目（幅 0 の空白）を足した写しを作り、それを渡す */
static int kin_head(const uint8_t *s)
{
    if (IS_LEAD(s[0]) && IS_TRAIL(s[1])) return GL(s[0], s[1])->flags & 1;
    return s[0] == '.' || s[0] == ',' || s[0] == '!' || s[0] == '?' || s[0] == ')' || s[0] == ':' || s[0] == ';' || s[0] == '%';
}
static uint32_t g_scr_slot;
static uint32_t __cdecl cb_f1(int k)
{
    static uint8_t s[8192], o[12288];
    uint32_t src = R_EAX, n = 0, m = 0, i;
    int has = 0;
    set_k(k, X_F1);
    reset_states();
    push32(R_ESI); push32(R_EDI); push32(R_EBP); R_ESP -= g_x[k][X_F1SUB];
    if (!src) return 0;
    while (n < sizeof s - 1) { s[n] = rb(src + n); if (!s[n]) break; if (s[n] >= 0x80) has = 1; n++; }
    s[n] = 0;
    if (!has || n >= sizeof s - 1) return 0;
    for (i = 0; i < n; ) {
        if (IS_LEAD(s[i]) && IS_TRAIL(s[i + 1])) {
            o[m++] = s[i]; o[m++] = s[i + 1];
            i += 2;
            if (IS_LEAD(s[i]) && IS_TRAIL(s[i + 1]) && !(GL(s[i - 2], s[i - 1])->flags & 2) && !kin_head(s + i)) o[m++] = ' ';
        } else o[m++] = s[i++];
        if (m >= sizeof o - 4) return 0;
    }
    o[m++] = 0;
    {
        uint32_t dst = DA(X_SCRATCH) + (g_scr_slot ^= 1) * 0x3000;
        if (m > 0x3000) return 0;
        for (i = 0; i < m; i++) wb(dst + i, o[i]);
        R_EAX = dst;
    }
    return 0;
}

/* 7: 起動の直後（sti; and esp,-4 の代わり）。日本語の文字列の束を書き、それを指す場所を書き換える */
static uint32_t __cdecl cb_entry(int k)
{
    spool_t *s = &g_sp[k];
    uint32_t pool, i;
    const uint8_t *q;
    set_k(k, X_ENTRY);
    R_ESP &= ~3u;
    if (!s->pool) return 0;
    pool = DA(X_POOL);
    for (i = 0; i < s->len; i++) wb(pool + i, s->pool[i]);
    for (i = 0, q = s->sites; i < s->n; i++, q += 9) {
        uint32_t site = *(const uint32_t*)q, off = *(const uint32_t*)(q + 5);
        wd(site + (q[4] ? g_dd : g_cd), pool + off);
    }
    dbg("exe %d: pool %x (%u bytes), %u sites, cd %x dd %x\n", k, pool, s->len, s->n, g_cd, g_dd);
    return 0;
}

#define CBW(n, f, k) static uint32_t __cdecl n(void) { return f(k); }
CBW(g0, cb_f1, 0) CBW(g1, cb_small, 0) CBW(g2, cb_big, 0) CBW(g3, cb_font1, 0) CBW(g4, cb_smallw, 0) CBW(g5, cb_bigw, 0) CBW(g6, cb_f1w, 0) CBW(g7, cb_entry, 0)
CBW(t0, cb_f1, 1) CBW(t1, cb_small, 1) CBW(t2, cb_big, 1) CBW(t3, cb_font1, 1) CBW(t4, cb_smallw, 1) CBW(t5, cb_bigw, 1) CBW(t6, cb_f1w, 1) CBW(t7, cb_entry, 1)
static int install_callbacks(void)
{
    uint32_t *tab = (uint32_t*)A_CB_HANDLERS;
    static const void *fn[16] = {g0, g1, g2, g3, g4, g5, g6, g7, t0, t1, t2, t3, t4, t5, t6, t7};
    int b, i;
    if (g_cb_base >= 0) return 1;
    for (b = CB_MAX - 16; b >= 32; b--) {
        for (i = 0; i < 16; i++) if (tab[b + i] != A_CB_ILLEGAL) break;
        if (i == 16) break;
    }
    if (b < 32) { dbg("no free callback slots\n"); return 0; }
    for (i = 0; i < 16; i++) tab[b + i] = (uint32_t)(uintptr_t)fn[i];
    g_cb_base = b;
    dbg("callbacks installed at %x\n", b);
    return 1;
}

/* ------------------------------------------------------------ コピーを作る */
static uint8_t *read_all(const char *path, uint32_t *len)
{
    FILE *f = fopen(path, "rb");
    uint8_t *b;
    long n;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    b = (uint8_t*)malloc(n ? n : 1);
    if (fread(b, 1, n, f) != (size_t)n) { fclose(f); free(b); return NULL; }
    fclose(f);
    *len = (uint32_t)n;
    return b;
}
static int write_all(const char *path, const uint8_t *b, uint32_t n)
{
    char tmp[MAX_PATH];
    FILE *f;
    wsprintfA(tmp, "%s.tmp", path);
    f = fopen(tmp, "wb");
    if (!f) return 0;
    if (fwrite(b, 1, n, f) != n) { fclose(f); return 0; }
    fclose(f);
    DeleteFileA(path);
    return MoveFileA(tmp, path);
}
/* 'E': size, count, {off u32, len u16, orig[len], new[len]}（元のバイトが合わなければ作らない）。FE 38 nn 00 の nn は 0x70 起点で書いてある */
static uint8_t *build_exe(const uint8_t *ep, uint8_t *b, uint32_t n)
{
    const uint8_t *p = ep + 8;
    uint32_t cnt = ((const uint32_t*)ep)[1], i;
    if (((const uint32_t*)ep)[0] != n) { dbg("exe size mismatch\n"); return NULL; }
    for (i = 0; i < cnt; i++) {
        uint32_t off = *(const uint32_t*)p, kk;
        uint16_t len = *(const uint16_t*)(p + 4);
        const uint8_t *o = p + 6, *nw = o + len;
        uint8_t tmp[256];
        if (off + len > n || memcmp(b + off, o, len) || len > sizeof tmp) { dbg("exe bytes mismatch at %x\n", off); return NULL; }
        memcpy(tmp, nw, len);
        for (kk = 0; kk + 3 < len; kk++)
            if (tmp[kk] == 0xfe && tmp[kk + 1] == 0x38 && tmp[kk + 3] == 0 && tmp[kk + 2] >= 0x70 && tmp[kk + 2] < 0x80) tmp[kk + 2] = (uint8_t)(tmp[kk + 2] - 0x70 + g_cb_base);
        memcpy(b + off, tmp, len);
        p = nw + len;
    }
    return b;
}

typedef FILE *(__cdecl *fopen_t)(const char *, const char *);
static fopen_t real_fopen;
static CRITICAL_SECTION g_cs;
static const char *base_name(const char *p)
{
    const char *b = p, *q;
    for (q = p; *q; q++) if (*q == '\\' || *q == '/' || *q == ':') b = q + 1;
    return b;
}
static void clean_old(const char *bn, const char *cur)
{
    char pat[MAX_PATH], old[MAX_PATH];
    WIN32_FIND_DATAA fd;
    HANDLE fh;
    wsprintfA(pat, "%s\\*_%s", g_dir, bn);
    fh = FindFirstFileA(pat, &fd);
    if (fh == INVALID_HANDLE_VALUE) return;
    do {
        if (_stricmp(fd.cFileName, cur)) { wsprintfA(old, "%s\\%s", g_dir, fd.cFileName); DeleteFileA(old); }
    } while (FindNextFileA(fh, &fd));
    FindClose(fh);
}
static const char *patched_path(const char *orig_path, char *buf)
{
    const char *bn = base_name(orig_path);
    char cur[64];
    uint32_t n;
    uint8_t *b;
    int i;
    for (i = 0; i < g_nfrep; i++) {
        frep_t *f = &g_frep[i];
        if (_stricmp(bn, f->name)) continue;
        if (f->osize) {
            WIN32_FILE_ATTRIBUTE_DATA a;
            if (!GetFileAttributesExA(orig_path, GetFileExInfoStandard, &a) || a.nFileSizeLow != f->osize) { dbg("size mismatch %s\n", bn); return NULL; }
        }
        wsprintfA(cur, "%08X_%s", g_blob_crc, f->name);
        wsprintfA(buf, "%s\\%s", g_dir, cur);
        if (GetFileAttributesA(buf) != INVALID_FILE_ATTRIBUTES) return buf;
        clean_old(f->name, cur);
        if (!write_all(buf, f->data, f->size)) return NULL;
        return buf;
    }
    for (i = 0; i < g_nep; i++) {
        epatch_t *e = &g_ep[i];
        if (_stricmp(bn, e->name)) continue;
        if (!install_callbacks()) return NULL;
        wsprintfA(cur, "%08X%02X_%s", g_blob_crc, g_cb_base, e->name);
        wsprintfA(buf, "%s\\%s", g_dir, cur);
        if (GetFileAttributesA(buf) != INVALID_FILE_ATTRIBUTES) return buf;
        clean_old(e->name, cur);
        b = read_all(orig_path, &n);
        if (!b) return NULL;
        if (!build_exe(e->p, b, n) || !write_all(buf, b, n)) { free(b); return NULL; }
        free(b);
        dbg("built %s\n", buf);
        return buf;
    }
    return NULL;
}
static FILE *__cdecl hook_fopen(const char *name, const char *mode)
{
    char buf[MAX_PATH];
    const char *pp;
    FILE *f;
    if (!name || !g_enabled || (mode && (strchr(mode, 'w') || strchr(mode, 'a')))) return real_fopen(name, mode);
    EnterCriticalSection(&g_cs);
    pp = patched_path(name, buf);
    LeaveCriticalSection(&g_cs);
    if (pp) {
        f = real_fopen(pp, (mode && strchr(mode, '+')) ? "rb" : mode);
        if (f) { dbg("redirect %s -> %s (%s)\n", name, pp, mode); return f; }
    }
    return real_fopen(name, mode);
}
static int hook_iat(void)
{
    uint8_t *base = (uint8_t*)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dh = (IMAGE_DOS_HEADER*)base;
    IMAGE_NT_HEADERS *nh = (IMAGE_NT_HEADERS*)(base + dh->e_lfanew);
    IMAGE_DATA_DIRECTORY *dd = &nh->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *id = (IMAGE_IMPORT_DESCRIPTOR*)(base + dd->VirtualAddress);
    int done = 0;
    for (; id->Name; id++) {
        const char *dll = (const char*)(base + id->Name);
        IMAGE_THUNK_DATA *ot, *ft;
        if (_stricmp(dll, "msvcrt.dll")) continue;
        ot = (IMAGE_THUNK_DATA*)(base + (id->OriginalFirstThunk ? id->OriginalFirstThunk : id->FirstThunk));
        ft = (IMAGE_THUNK_DATA*)(base + id->FirstThunk);
        for (; ot->u1.AddressOfData; ot++, ft++) {
            IMAGE_IMPORT_BY_NAME *ibn;
            DWORD old;
            if (ot->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            ibn = (IMAGE_IMPORT_BY_NAME*)(base + ot->u1.AddressOfData);
            if (strcmp((const char*)ibn->Name, "fopen")) continue;
            VirtualProtect(&ft->u1.Function, 4, PAGE_READWRITE, &old);
            ft->u1.Function = (DWORD)(uintptr_t)hook_fopen;
            VirtualProtect(&ft->u1.Function, 4, old, &old);
            done = 1;
        }
    }
    return done;
}

static void init(HMODULE self)
{
    char la[MAX_PATH];
#ifdef XC_TEST
    char v[8];
#endif
    HMODULE crt;
    InitializeCriticalSection(&g_cs);
    if (!GetEnvironmentVariableA("LOCALAPPDATA", la, MAX_PATH)) return;
    wsprintfA(g_dir, "%s\\XC_JP_APOC", la);
    CreateDirectoryA(g_dir, NULL);
#ifdef XC_TEST
    g_logon = GetEnvironmentVariableA("XC_LOG", v, sizeof v) > 0;
    if (GetEnvironmentVariableA("XC_NOJP", v, sizeof v) > 0) return;      /* テスト用: 英語のまま */
#endif
    if (!verify_dosbox()) { dbg("unknown DOSBox build\n"); return; }
    if (!load_blob(self)) { dbg("no patch data\n"); return; }
    crt = GetModuleHandleA("msvcrt.dll");
    if (!crt) return;
    real_fopen = (fopen_t)GetProcAddress(crt, "fopen");
    if (!real_fopen || !hook_iat()) { dbg("fopen import not found\n"); return; }
    g_enabled = 1;
    dbg("X-COM Apocalypse JP patch active, blob %08X\n", g_blob_crc);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        proxy_init();
        init(h);
#ifdef XC_TEST
        testio_init();        /* 試験版だけ: tools/win.py との受け渡し（testio.c） */
#endif
    }
    return TRUE;
}
