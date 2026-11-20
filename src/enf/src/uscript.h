/* ============================================================ スクリプトの中の英語（xe_jp.c から #include する）
 *  1. 文字列の定数: UnrealScript の命令 EX_StringConst（GNatives[0x1F]）を差し替え、英語の定数が表にあれば日本語にする
 *     （「Please Name Your Enforcer!」「Next Upgrade: 」など、.int で訳せない画面の文）。lit.bin
 *  2. localized でない既定値（武器の強化の名前など）: クラスが読み込まれたら UObject::GlobalSetProperty で書き換える。set.bin
 *     （コンソールの set と同じ仕組み。配列の要素は Offset + 番号 × 12）
 * FString = {TCHAR* Data; INT Num（終わりの 0 を含む）; INT Max}
 */
typedef struct { uint16_t *data; int num, max; } fstr_t;
typedef struct { const uint16_t *en, *ja; int enlen, jalen; } lit_t;
static lit_t g_lit[512]; static int g_nlit;
typedef void (__fastcall *native_t)(void*, void*, void*, void*);
static native_t o_strconst;
static int g_lit_hits;

static void __fastcall my_strconst(void *self, void *edx, void *stack, void *result)
{
    fstr_t *r = (fstr_t*)result;
    int i;
    o_strconst(self, edx, stack, result);
    if (!r || !r->data || r->num < 2) return;
    for (i = 0; i < g_nlit; i++) {
        lit_t *l = &g_lit[i];
        if (r->num - 1 == l->enlen && !memcmp(r->data, l->en, l->enlen * 2)) {
            uint16_t *d = (uint16_t*)gm_realloc(r->data, (l->jalen + 1) * 2);
            if (!d) return;
            memcpy(d, l->ja, l->jalen * 2); d[l->jalen] = 0;
            r->data = d; r->num = r->max = l->jalen + 1;
            g_lit_hits++;
            return;
        }
    }
}

typedef struct { const uint16_t *pkg, *cls, *prop, *val; int idx, done; } set_t;
static set_t g_set[1024]; static int g_nset, g_set_left;
typedef void (__cdecl *gsp_t)(const uint16_t*, void*, void*, int, int);
static gsp_t e_gsp; static staticclass_t e_classclass, e_propclass;

static void apply_sets(void)
{
    int i;
    wchar_t buf[512];
    if (!g_set_left || !e_gsp || !e_findobj || !e_classclass || !e_propclass) return;
    for (i = 0; i < g_nset; i++) {
        set_t *s = &g_set[i];
        uint8_t *pkg, *cls, *c, *prop = NULL;
        if (s->done) continue;
        pkg = (uint8_t*)e_findobj(NULL, NULL, (const wchar_t*)s->pkg, 0);
        if (!pkg) continue;
        cls = (uint8_t*)e_findobj(e_classclass(), pkg, (const wchar_t*)s->cls, 0);
        if (!cls) continue;
        for (c = cls; c && !prop; c = *(uint8_t**)(c + 0x28)) prop = (uint8_t*)e_findobj(e_propclass(), c, (const wchar_t*)s->prop, 0);
        s->done = 1; g_set_left--;
        if (!prop) { dbg("set: no property %ls in %ls\n", s->prop, s->cls); continue; }
        lstrcpynW(buf, (const wchar_t*)s->val, 512);          /* この版の ImportText は引用符をそのまま残すので付けない */
        e_gsp((const uint16_t*)buf, cls, prop, *(int*)(prop + 0x48) + s->idx * 12, 1);
    }
    if (!g_set_left) dbg("all defaults set\n");
}

/* パッチデータの lit.bin / set.bin を読む（文字列は UTF-16、u16 の長さつき。最後に 0 を付けた写しを作る） */
static const uint16_t *take_str(const uint8_t **pp)
{
    uint16_t n = *(const uint16_t*)*pp;
    uint16_t *s = (uint16_t*)malloc((n + 1) * 2);
    memcpy(s, *pp + 2, n * 2); s[n] = 0;
    *pp += 2 + n * 2;
    return s;
}
static void load_lits(const uint8_t *p, uint32_t size)
{
    uint32_t n = *(const uint32_t*)p, i;
    const uint8_t *q = p + 4;
    (void)size;
    for (i = 0; i < n && g_nlit < 512; i++) {
        lit_t *l = &g_lit[g_nlit++];
        l->en = take_str(&q); l->ja = take_str(&q);
        l->enlen = lstrlenW((const wchar_t*)l->en); l->jalen = lstrlenW((const wchar_t*)l->ja);
    }
}
static void load_dsubs(const uint8_t *p, uint32_t size)
{
    uint32_t n = *(const uint32_t*)p, i;
    const uint8_t *q = p + 4;
    (void)size;
    for (i = 0; i < n && g_ndsub < 256; i++) { g_dsub[g_ndsub].en = take_str(&q); g_dsub[g_ndsub].ja = take_str(&q); g_ndsub++; }
}
static void load_sets(const uint8_t *p, uint32_t size)
{
    uint32_t n = *(const uint32_t*)p, i;
    const uint8_t *q = p + 4;
    (void)size;
    for (i = 0; i < n && g_nset < 1024; i++) {
        set_t *s = &g_set[g_nset++];
        s->pkg = take_str(&q); s->cls = take_str(&q); s->prop = take_str(&q);
        s->idx = *(const int32_t*)q; q += 4;
        s->val = take_str(&q); s->done = 0;
    }
    g_set_left = g_nset;
}

static void hook_uscript(HMODULE core, HMODULE eng)
{
    void **gn = (void**)GetProcAddress(core, "?GNatives@@3PAP8UObject@@AEXAAUFFrame@@QAX@ZA");
    uint8_t *sc = (uint8_t*)GetProcAddress(core, "?execStringConst@UObject@@QAEXAAUFFrame@@QAX@Z");
    DWORD old;
    e_gsp = (gsp_t)GetProcAddress(core, "?GlobalSetProperty@UObject@@SAXPBGPAVUClass@@PAVUProperty@@HH@Z");
    e_classclass = (staticclass_t)GetProcAddress(core, "?StaticClass@UClass@@SAPAV1@XZ");
    e_propclass = (staticclass_t)GetProcAddress(core, "?StaticClass@UProperty@@SAPAVUClass@@XZ");
    (void)eng;
    if (g_nlit && gn && sc && (gn[0x1f] == sc || gn[0x1f] == thunk_target(sc))) {
        VirtualProtect(&gn[0x1f], 4, PAGE_READWRITE, &old);
        o_strconst = (native_t)gn[0x1f];
        gn[0x1f] = (void*)my_strconst;
        VirtualProtect(&gn[0x1f], 4, old, &old);
        dbg("string const hook, %d literals\n", g_nlit);
    } else if (g_nlit) dbg("GNatives[0x1f] differs (%p %p)\n", gn ? gn[0x1f] : NULL, sc);
}
