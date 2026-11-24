/*
 * X-COM: Enforcer 日本語化パッチ（実行時部分）
 * System フォルダに置く winmm.dll（本物の winmm.dll へ中継する。Core.dll が読み込む）。ゲームのファイルは書き換えない。
 *  - 文章: エンジンが読む翻訳ファイル（System の *.int と、マップの *.int）を開くとき、%LOCALAPPDATA%\XC_JP_ENF に作った
 *    日本語版（UTF-16）を渡す。.int が無いパッケージ（XMenu など）も、日本語版があれば渡す。
 *  - 字: 日本語の字の絵のパッケージ XCJP.u を読み込み、ゲームの各フォントのページの後ろに足す（fontmerge.h）。
 *  - 折り返し: ゲーム（UWindow・Canvas）は空白でしか折り返さないので、訳文の日本語の字の間に空白を入れてある。
 *    日本語の字のすぐ後の空白は、幅 0 の字に振り向けて見えなくする。
 */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "resource.h"

void proxy_init(void);

static wchar_t g_dir[MAX_PATH];
#ifdef XE_TEST
/* 試験版だけ: 環境変数 XE_LOG があれば g_dir\log.txt に記録する */
static FILE *g_log;
static int g_logon;
static CRITICAL_SECTION g_logcs;
static void dbg(const char *fmt, ...)
{
    va_list ap;
    if (!g_logon) return;
    EnterCriticalSection(&g_logcs);
    if (!g_log) {
        wchar_t p[MAX_PATH];
        wsprintfW(p, L"%s\\log.txt", g_dir);
        g_log = _wfopen(p, L"a");
    }
    if (g_log) { va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap); fflush(g_log); }
    LeaveCriticalSection(&g_logcs);
}
#else
#define g_logon 0
#define dbg(...) ((void)0)
#endif

/* ------------------------------------------------------------ 関数の入口に jmp を書く（戻り口つき） */
static void *hook_entry(uint8_t *p, int steal, const uint8_t *expect, void *to)
{
    uint8_t *t;
    DWORD old;
    if (!p || memcmp(p, expect, steal)) { if (p) dbg("unexpected entry bytes at %p: %02x %02x %02x %02x %02x\n", p, p[0], p[1], p[2], p[3], p[4]); return NULL; }
    t = (uint8_t*)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, p, steal);
    t[steal] = 0xe9; *(int32_t*)(t + steal + 1) = (int32_t)((p + steal) - (t + steal + 5));
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int32_t*)(p + 1) = (int32_t)((uint8_t*)to - (p + 5));
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    return t;
}
static const uint8_t HOT[] = {0x8b, 0xff, 0x55, 0x8b, 0xec};

#include "fontmerge.h"

/* ------------------------------------------------------------ パッチデータ
 * 'XEJ1', 件数, {u8 名前の長さ, 名前（ASCII）, u32 大きさ, 中身}
 *   *.int: 日本語の翻訳ファイル（UTF-16）。XCJP.u: 日本語の字のパッケージ
 */
typedef HANDLE (WINAPI *cfw_t)(LPCWSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
static cfw_t o_cfw, k_cfw;
typedef struct { char name[40]; uint32_t size; const uint8_t *data; } frep_t;
static frep_t g_frep[256]; static int g_nfrep, g_enabled;
static uint32_t g_crc;
static uint32_t crc32(const uint8_t *p, uint32_t n)
{
    uint32_t c = 0xffffffffu, k;
    while (n--) { c ^= *p++; for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1))); }
    return ~c;
}
static int load_blob(HMODULE self)
{
    HRSRC r = FindResourceA(self, MAKEINTRESOURCEA(IDR_PATCH), (LPCSTR)RT_RCDATA);
    const uint8_t *b, *p, *e;
    uint32_t n, i, len;
    if (!r) return 0;
    b = (const uint8_t*)LockResource(LoadResource(self, r)); len = SizeofResource(self, r);
    if (!b || len < 8 || memcmp(b, "XEJ1", 4)) return 0;
    g_crc = crc32(b, len);
    n = *(const uint32_t*)(b + 4); p = b + 8; e = b + len;
    for (i = 0; i < n && p < e && g_nfrep < 256; i++) {
        frep_t *f = &g_frep[g_nfrep++];
        memcpy(f->name, p + 1, p[0]); f->name[p[0]] = 0;
        f->size = *(const uint32_t*)(p + 1 + p[0]); f->data = p + 5 + p[0];
        p = f->data + f->size;
    }
    return 1;
}
static int write_all(const wchar_t *path, const uint8_t *b, uint32_t n)
{
    HANDLE h = k_cfw(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD w = 0;
    if (h == INVALID_HANDLE_VALUE) return 0;
    WriteFile(h, b, n, &w, NULL); CloseHandle(h);
    return w == n;
}
/* 名前の付いたファイルを %LOCALAPPDATA%\XC_JP_ENF に書き出して、その場所を返す */
static int cache_path(frep_t *f, wchar_t *out)
{
    wsprintfW(out, L"%s\\%08X_%hs", g_dir, g_crc, f->name);
    if (GetFileAttributesW(out) == INVALID_FILE_ATTRIBUTES && !write_all(out, f->data, f->size)) return 0;
    return 1;
}
static frep_t *find_rep(const wchar_t *base)
{
    int i;
    char a[64];
    if (lstrlenW(base) >= 40) return NULL;
    WideCharToMultiByte(CP_ACP, 0, base, -1, a, sizeof a, NULL, NULL);
    for (i = 0; i < g_nfrep; i++) if (!lstrcmpiA(a, g_frep[i].name)) return &g_frep[i];
    return NULL;
}

/* ------------------------------------------------------------ ファイル */
static HANDLE WINAPI my_cfw(LPCWSTR name, DWORD acc, DWORD share, LPSECURITY_ATTRIBUTES sa, DWORD disp, DWORD fl, HANDLE tmpl)
{
    if (!g_engine_hooked) hook_engine();
    if (g_enabled && name && !(acc & GENERIC_WRITE)) {
        const wchar_t *b = name, *q;
        int n;
        for (q = name; *q; q++) if (*q == L'\\' || *q == L'/') b = q + 1;
        n = lstrlenW(b);
        if (n > 4 && !lstrcmpiW(b + n - 4, L".int")) {
            frep_t *f = find_rep(b);
            wchar_t p[MAX_PATH];
            if (f && cache_path(f, p)) {
                if (g_logon) dbg("redirect %ls\n", name);
                return o_cfw(p, acc, share, sa, disp, fl, tmpl);
            }
        }
    }
    return o_cfw(name, acc, share, sa, disp, fl, tmpl);
}

static void init(HMODULE self)
{
    wchar_t la[MAX_PATH];
#ifdef XE_TEST
    wchar_t v[8];
#endif
    HMODULE kb;
#ifdef XE_TEST
    InitializeCriticalSection(&g_logcs);
#endif
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", la, MAX_PATH)) return;
    wsprintfW(g_dir, L"%s\\XC_JP_ENF", la);
    CreateDirectoryW(g_dir, NULL);
#ifdef XE_TEST
    g_logon = GetEnvironmentVariableW(L"XE_LOG", v, 8) > 0;
    if (GetEnvironmentVariableW(L"XE_NOJP", v, 8) > 0) return;      /* テスト用: 英語のまま */
#endif
    if (!load_blob(self)) { dbg("no patch data\n"); return; }
    kb = GetModuleHandleW(L"kernelbase.dll");
    k_cfw = (cfw_t)GetProcAddress(kb, "CreateFileW");
    {
        frep_t *l = find_rep(L"lit.bin"), *t = find_rep(L"set.bin");
        frep_t *d = find_rep(L"draw.bin");
        if (l) load_lits(l->data, l->size);
        if (d) load_dsubs(d->data, d->size);
        if (t) { load_sets(t->data, t->size); g_tick = apply_sets; }
    }
    {
        frep_t *f = find_rep(L"XCJP.u");
        if (f && cache_path(f, g_xcjp_path)) dbg("font package %ls\n", g_xcjp_path);
        else g_xcjp_path[0] = 0;
    }
    g_enabled = 1;
    o_cfw = (cfw_t)hook_entry((uint8_t*)k_cfw, 5, HOT, (void*)my_cfw);
    if (!o_cfw) o_cfw = k_cfw;
    dbg("X-COM Enforcer JP patch: %d files, blob %08X\n", g_nfrep, g_crc);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        proxy_init();
        init(h);
    }
    return TRUE;
}
