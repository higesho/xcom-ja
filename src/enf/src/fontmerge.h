/* ============================================================ 日本語の字（xe_jp.c から #include する）
 * UFont（Engine.dll, v420）: +0x28 CharactersPerPage, +0x2c Pages (TArray<FFontPage>: Data, Num, Max),
 *   +0x38 CharRemap (TMap<WORD,WORD>), +0x4c IsRemapped。FFontPage = {UTexture*, TArray<FFontCharacter>} 16 バイト、
 *   FFontCharacter = {StartU, StartV, USize, VSize} 16 バイト。
 * 字を描く・測る所（Canvas の WrappedPrint など）は、IsRemapped なら CharRemap の Find(&字) を呼んで字の番号を得る。
 * そこで: フォントを読み込んだとき（UFont::Serialize の後）に IsRemapped を立てておき、Find を差し替える。
 * 日本語の字が初めて来たら、そのフォントのページの後ろに日本語のフォント（XCJP.u の JPnn）のページを足し、
 * 足したフォントについては字の番号を自分で返す
 *   日本語の字 → 足したページの中の位置、日本語の字のすぐ後の空白 → 幅 0 の字、そのほか → そのまま。
 */
static int g_enabled;
static void (*g_tick)(void);                 /* 描くときにときどき呼ぶ（既定値の書き換え。uscript.h） */
static unsigned g_tickn;
typedef void *(__cdecl *loadpkg_t)(void*, const wchar_t*, DWORD);
typedef void *(__cdecl *findobj_t)(void*, void*, const wchar_t*, int);
typedef void *(__cdecl *staticclass_t)(void);
typedef uint16_t *(__fastcall *find_t)(void*, void*, const uint16_t*);
typedef void *(__fastcall *mmalloc_t)(void*, void*, DWORD, const wchar_t*);
typedef void *(__fastcall *mrealloc_t)(void*, void*, void*, DWORD, const wchar_t*);
typedef void (__fastcall *addroot_t)(void*, void*);
static loadpkg_t e_loadpkg; static findobj_t e_findobj; static staticclass_t e_fontclass; static void ***e_gmalloc; static addroot_t e_addroot;
static find_t o_find;
typedef void (__cdecl *wprint_t)(void*, int, int*, int*, uint8_t*, int, const uint16_t*);
typedef void (__cdecl *wprintex_t)(void*, int, int*, int*, uint8_t*, int, const uint16_t*, float, float);
static wprint_t o_wprint; static wprintex_t o_wprintex;

#define FT_CPP(f)   (*(int*)((f) + 0x28))
#define FT_PAGES(f) (*(uint8_t**)((f) + 0x2c))
#define FT_NPAGE(f) (*(int*)((f) + 0x30))
#define FT_MAXP(f)  (*(int*)((f) + 0x34))
#define FT_REMAP(f) (*(int*)((f) + 0x4c))
#define FT_NMAP(f)  (*(int*)((f) + 0x3c))      /* CharRemap に本当に入っている数 */

static void *gm_malloc(DWORD n) { void *m = *e_gmalloc; return ((mmalloc_t)(*(void***)m)[0])(m, NULL, n, L"XCJP"); }
static void *gm_realloc(void *p, DWORD n) { void *m = *e_gmalloc; return ((mrealloc_t)(*(void***)m)[1])(m, NULL, p, n, L"XCJP"); }

/* 日本語のフォント（大きさ順） */
#define NJF 8
static const int JF_SIZE[NJF] = {10, 12, 14, 16, 20, 24, 30, 40};
static uint8_t *g_jf[NJF];
static int g_jp_loaded;
static wchar_t g_xcjp_path[MAX_PATH];

static int load_jp_fonts(void)
{
    void *pkg, *fc;
    int i, n = 0;
    if (g_jp_loaded) return g_jp_loaded > 0;
    g_jp_loaded = -1;
    if (!e_loadpkg || !e_findobj || !e_fontclass || !g_xcjp_path[0]) return 0;
    pkg = e_loadpkg(NULL, g_xcjp_path, 0);
    fc = e_fontclass();
    dbg("XCJP package %p (%ls)\n", pkg, g_xcjp_path);
    if (!pkg) return 0;
    for (i = 0; i < NJF; i++) {
        wchar_t nm[16];
        wsprintfW(nm, L"JP%d", JF_SIZE[i]);
        g_jf[i] = (uint8_t*)e_findobj(fc, pkg, nm, 0);
        if (g_jf[i] && e_addroot) e_addroot(g_jf[i], NULL);    /* ごみ集めで消されないように（字の絵もこれから参照される） */
        if (g_jf[i]) { n++; dbg("  %ls %p pages %d cpp %d\n", nm, g_jf[i], FT_NPAGE(g_jf[i]), FT_CPP(g_jf[i])); }
    }
    g_jp_loaded = n ? 1 : -1;
    return n > 0;
}

/* 足したフォントの記録 */
typedef struct { uint8_t *font, *jf, *pages; int base, cpp, zero, total; } merged_t;
static merged_t g_mf[64]; static int g_nmf;
static uint8_t *g_nomerge[64]; static int g_nnm;
static merged_t *find_merged(uint8_t *f)
{
    int i;
    for (i = 0; i < g_nmf; i++) if (g_mf[i].font == f) {
        if (FT_PAGES(f) == g_mf[i].pages && FT_NPAGE(f) == g_mf[i].total) return &g_mf[i];
        g_mf[i] = g_mf[--g_nmf];                  /* 同じ場所に別のフォントが読み込まれた: 記録を消して足し直す */
        return NULL;
    }
    return NULL;
}
static int font_height(uint8_t *f)
{
    int h = 0, p, c;
    for (p = 0; p < FT_NPAGE(f) && p < 8; p++) {
        uint8_t *pg = FT_PAGES(f) + p * 16;
        int nc = *(int*)(pg + 8);
        int *ch = *(int**)(pg + 4);
        for (c = 0; c < nc; c++) if (ch[c * 4 + 3] > h) h = ch[c * 4 + 3];
    }
    return h;
}
static void merge_font(uint8_t *f)
{
    int i, best = -1, h, n, pj, total;
    uint8_t *jf, *data;
    merged_t *m;
    if (!f || find_merged(f) || g_nmf >= 64) return;
    for (i = 0; i < g_nnm; i++) if (g_nomerge[i] == f && FT_CPP(f) <= 0) return;
    if (!load_jp_fonts()) return;
    for (i = 0; i < NJF; i++) if (g_jf[i] == f) return;            /* 日本語のフォントそのもの */
    if (FT_NMAP(f) || FT_CPP(f) <= 0) { if (g_nnm < 64) g_nomerge[g_nnm++] = f; return; }
    h = font_height(f);
    for (i = 0; i < NJF; i++) if (g_jf[i] && (best < 0 || abs(JF_SIZE[i] - h) < abs(JF_SIZE[best] - h))) best = i;
    if (best < 0) return;
    jf = g_jf[best];
    n = FT_NPAGE(f); pj = FT_NPAGE(jf);
    total = n + pj + 1;
    if ((long)total * FT_CPP(f) > 65535) { dbg("font %p too many pages\n", f); if (g_nnm < 64) g_nomerge[g_nnm++] = f; return; }
    data = (uint8_t*)gm_realloc(FT_PAGES(f), total * 16);
    if (!data) return;
    for (i = 0; i < pj; i++) {
        uint8_t *src = FT_PAGES(jf) + i * 16, *dst = data + (n + i) * 16;
        int nc = *(int*)(src + 8);
        void *chars = nc ? gm_malloc(nc * 16) : NULL;
        if (nc && chars) memcpy(chars, *(void**)(src + 4), nc * 16);
        *(void**)dst = *(void**)src;
        *(void**)(dst + 4) = chars; *(int*)(dst + 8) = chars ? nc : 0; *(int*)(dst + 12) = chars ? nc : 0;
    }
    {   /* 幅 0 の字が 1 つだけのページ */
        uint8_t *dst = data + (n + pj) * 16;
        int *chars = (int*)gm_malloc(16);
        memset(chars, 0, 16);
        *(void**)dst = *(void**)FT_PAGES(jf);
        *(void**)(dst + 4) = chars; *(int*)(dst + 8) = 1; *(int*)(dst + 12) = 1;
    }
    FT_PAGES(f) = data; FT_NPAGE(f) = total; FT_MAXP(f) = total;
    m = &g_mf[g_nmf];
    m->font = f; m->jf = jf; m->base = n; m->cpp = FT_CPP(f); m->zero = (n + pj) * FT_CPP(f); m->pages = data; m->total = total;
    g_nmf++;                                                   /* 記録してから IsRemapped を立てる */
    FT_REMAP(f) = 1;
    dbg("merged font %p (h %d, %d pages, cpp %d) with JP%d\n", f, h, n, FT_CPP(f), JF_SIZE[best]);
}

static int is_wide(uint16_t c) { return c >= 0x2e80; }
static uint16_t g_prev, g_out;
static uint16_t *__fastcall my_find(void *map, void *edx, const uint16_t *key)
{
    uint8_t *f = (uint8_t*)map - 0x38;
    merged_t *m;
    uint16_t c;
    if (FT_NMAP(f)) return o_find(map, edx, key);            /* 本当の対応表を持つフォント（日本語のフォントなど） */
    m = find_merged(f);
    c = *key;
    if (!m && c >= 0x100) { merge_font(f); m = find_merged(f); }
    if (!m) { g_out = c < 0x100 ? c : '?'; g_prev = c; return &g_out; }
    if (c == ' ' && is_wide(g_prev)) g_out = (uint16_t)m->zero;
    else if (c >= 0x100) {
        uint16_t *g = o_find(m->jf + 0x38, NULL, key);
        if (g) {
            int jcpp = FT_CPP(m->jf);
            g_out = (uint16_t)((m->base + *g / jcpp) * m->cpp + *g % jcpp);
        } else g_out = '?';
    } else g_out = c;
    g_prev = c;
    return &g_out;
}
/* 描くときの置き換え（文全体が一致したとき。マップの主目標が LevelInfo.Author に入っているなど、訳せない所の文） */
typedef struct { const uint16_t *en, *ja; } dsub_t;
static dsub_t g_dsub[256]; static int g_ndsub;
static const uint16_t *draw_sub(const uint16_t *t)
{
    int i;
    if (!t || !g_ndsub) return t;
    for (i = 0; i < g_ndsub; i++) if (!lstrcmpW((const wchar_t*)t, (const wchar_t*)g_dsub[i].en)) return g_dsub[i].ja;
    return t;
}
static int text_has_wide(const uint16_t *s)
{
    if (!s) return 0;
    for (; *s; s++) if (*s >= 0x100) return 1;
    return 0;
}
static void __cdecl my_wprint(void *cv, int style, int *xl, int *yl, uint8_t *font, int center, const uint16_t *text)
{
    text = draw_sub(text);
    if (font && text_has_wide(text)) merge_font(font);
    if (g_tick && !(g_tickn++ & 63)) g_tick();
    g_prev = 0;
    o_wprint(cv, style, xl, yl, font, center, text);
}
static void __cdecl my_wprintex(void *cv, int style, int *xl, int *yl, uint8_t *font, int center, const uint16_t *text, float a, float b)
{
    text = draw_sub(text);
    if (font && text_has_wide(text)) merge_font(font);
    if (g_tick && !(g_tickn++ & 63)) g_tick();
    g_prev = 0;
    o_wprintex(cv, style, xl, yl, font, center, text, a, b);
}

/* フォントを読み込んだら IsRemapped を立てる（文字はすべて Find を通るようになる） */
typedef void (__fastcall *fser_t)(uint8_t*, void*, void*);
static fser_t o_fser;
static void __fastcall my_fser(uint8_t *f, void *edx, void *ar)
{
    o_fser(f, edx, ar);
    if (g_enabled && f && !FT_NMAP(f) && FT_CPP(f) > 0) FT_REMAP(f) = 1;
}
static uint8_t *thunk_target(uint8_t *p)
{
    if (p && p[0] == 0xe9) return p + 5 + *(int32_t*)(p + 1);
    return p;
}
#include "uscript.h"
static int g_engine_hooked;
static void hook_engine(void)
{
    HMODULE core = GetModuleHandleW(L"Core.dll"), eng = GetModuleHandleW(L"Engine.dll");
    static const uint8_t X_FIND[] = {0x8b, 0x44, 0x24, 0x04, 0x56};
    static const uint8_t X_WP[] = {0x55, 0x8b, 0xec, 0x6a, 0xff};
    uint8_t *find, *wp, *wpx;
    if (g_engine_hooked || !core || !eng) return;
    g_engine_hooked = 1;
    e_loadpkg = (loadpkg_t)GetProcAddress(core, "?LoadPackage@UObject@@SAPAV1@PAV1@PBGK@Z");
    e_findobj = (findobj_t)GetProcAddress(core, "?StaticFindObject@UObject@@SAPAV1@PAVUClass@@PAV1@PBGH@Z");
    e_gmalloc = (void***)GetProcAddress(core, "?GMalloc@@3PAVFMalloc@@A");
    e_fontclass = (staticclass_t)GetProcAddress(eng, "?StaticClass@UFont@@SAPAVUClass@@XZ");
    e_addroot = (addroot_t)GetProcAddress(core, "?AddToRoot@UObject@@QAEXXZ");
    /* Find は書き出されていないので、WrappedPrint の中の呼び出しから探す（Engine.dll の版を確かめる） */
    wp = thunk_target((uint8_t*)GetProcAddress(eng, "?WrappedPrint@UCanvas@@AAAXW4ERenderStyle@@AAH1PAVUFont@@HPBG@Z"));
    wpx = thunk_target((uint8_t*)GetProcAddress(eng, "?WrappedPrintEx@UCanvas@@AAAXW4ERenderStyle@@AAH1PAVUFont@@HPBGMM@Z"));
    if (!wp || !wpx || memcmp(wp + 0x18d, "\x39\x78\x4c\x74\x1a\x8d\x4d\xc8\x51\x8d\x48\x38\xe8", 13)) { dbg("Engine.dll differs\n"); return; }
    find = thunk_target(wp + 0x199 + 5 + *(int32_t*)(wp + 0x19a));
    o_find = (find_t)hook_entry(find, 5, X_FIND, (void*)my_find);
    o_wprint = (wprint_t)hook_entry(wp, 5, X_WP, (void*)my_wprint);
    o_wprintex = (wprintex_t)hook_entry(wpx, 5, X_WP, (void*)my_wprintex);
    o_fser = (fser_t)hook_entry(thunk_target((uint8_t*)GetProcAddress(eng, "?Serialize@UFont@@UAEXAAVFArchive@@@Z")), 5, X_WP, (void*)my_fser);
    dbg("engine hooks: find %p wprint %p wprintex %p serialize %p\n", o_find, o_wprint, o_wprintex, o_fser);
    hook_uscript(core, eng);
}
