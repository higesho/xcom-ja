/*
 * X-COM: Interceptor 日本語化パッチ（実行時部分）
 * ゲームのフォルダに置く winmm.dll（本物の winmm.dll へ中継する）。ゲームのファイルは書き換えない。
 *  - Text\LangFile1.txt などを開くとき（CreateFileA）、%LOCALAPPDATA%\XC_JP_INTC に作った日本語版を渡す。
 *    日本語の文章は独自の 2 バイト符号（1 バイト目 0x80-0x9F、2 バイト目 0xA0-0xFF）で書いてあり、
 *    ゲームの書式の記号（[ ] ( ) _ ~ % " \）とぶつからない。
 *  - 文字は GDI の DrawTextA / GetTextExtentPointA で描かれるので、この 2 つを差し替え、符号を Unicode に戻して
 *    DrawTextW / GetTextExtentPoint32W で描く。日本語の字があるときは、ゲームのフォントと同じ大きさの日本語のフォントを使う。
 *  - 日本語の文の折り返し: DrawText の折り返しは空白でしか切れないので、日本語の字の間に「幅 0 の空白」を入れて渡す
 *    （Unicode の U+200B）。
 */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "resource.h"
#include <intrin.h>

void proxy_init(void);

static char g_dir[MAX_PATH];
static FILE *g_log;
static int g_logon;
static void dbg(const char *fmt, ...)
{
    va_list ap;
    if (!g_logon) return;
    if (!g_log) {
        wchar_t p[MAX_PATH];
        char pa[MAX_PATH];
        wsprintfA(pa, "%s\\log.txt", g_dir);
        MultiByteToWideChar(CP_ACP, 0, pa, -1, p, MAX_PATH);
        g_log = _wfopen(p, L"a");
        if (!g_log) return;
    }
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fflush(g_log);
}

/* ------------------------------------------------------- パッチデータ
 * 'XIJ1', 節の数, 節 {u8 種類, u32 長さ, 中身}
 *  'C' 符号の表: u32 件数, {u16 符号（1 バイト目 << 8 | 2 バイト目）, u16 Unicode}, 禁則 u8[件数]（1 行頭に来ない 2 行末に来ない）
 *  'F' ファイル: u8 名前の長さ, 名前（Text フォルダの基本名）, u32 元の大きさ（0 = 見ない）, u32 大きさ, 中身
 */
static const uint8_t *g_blob;
static uint32_t g_blob_len, g_blob_crc;
static uint16_t g_uni[0x2000];               /* [(lead-0x80)<<8 | trail] → Unicode */
static uint8_t g_kin[0x2000];
#define IS_LEAD(c) ((c) >= 0x80 && (c) < 0xa0)
#define IS_TRAIL(c) ((c) >= 0xa0)
typedef struct { char name[32]; uint32_t osize, size; const uint8_t *data; } frep_t;
static frep_t g_frep[8]; static int g_nfrep;
static int g_enabled;

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
    if (!g_blob || g_blob_len < 8 || memcmp(g_blob, "XIJ1", 4)) return 0;
    g_blob_crc = crc32(g_blob, g_blob_len) ^ 0x1u;
    ns = *(const uint32_t*)(g_blob + 4);
    p = g_blob + 8;
    for (i = 0; i < ns && p + 5 <= g_blob + g_blob_len; i++) {
        uint8_t t = p[0];
        uint32_t len = *(const uint32_t*)(p + 1), k;
        const uint8_t *d = p + 5;
        if (t == 'C') {
            uint32_t n = *(const uint32_t*)d;
            const uint16_t *q = (const uint16_t*)(d + 4);
            for (k = 0; k < n; k++) {
                uint16_t c = q[k * 2];
                if ((c >> 8) < 0x80 || (c >> 8) >= 0xa0) continue;
                g_uni[((c >> 8) - 0x80) << 8 | (c & 0xff)] = q[k * 2 + 1];
                g_kin[((c >> 8) - 0x80) << 8 | (c & 0xff)] = d[4 + n * 4 + k];
            }
        } else if (t == 'F' && g_nfrep < 8) {
            frep_t *f = &g_frep[g_nfrep++];
            memcpy(f->name, d + 1, d[0]); f->name[d[0]] = 0;
            f->osize = *(const uint32_t*)(d + 1 + d[0]); f->size = *(const uint32_t*)(d + 5 + d[0]); f->data = d + 9 + d[0];
        }
        p = d + len;
    }
    return 1;
}

/* ------------------------------------------------------------ 符号 → Unicode */
static int is_open_bracket(wchar_t c) { return c == 0x300c || c == 0x300e || c == 0xff08 || c == 0x3010 || c == 0x3014; }
/* s[0..n) を Unicode に。日本語の字どうしの間（禁則にかからない所）に U+200B を入れる（wrap = 1 のとき）。戻り値: 長さ */
static int to_wide(const char *s, int n, wchar_t *o, int cap, int wrap, int *hasjp)
{
    int i = 0, m = 0;
    const uint8_t *u = (const uint8_t*)s;
    int prevjp = 0; wchar_t prevc = 0;
    *hasjp = 0;
    while (i < n && m < cap - 2) {
        uint8_t c = u[i];
        if (IS_LEAD(c) && i + 1 < n && IS_TRAIL(u[i + 1])) {
            int idx = (c - 0x80) << 8 | u[i + 1];
            wchar_t w = g_uni[idx] ? g_uni[idx] : L'?';
            if (wrap && prevjp && !(g_kin[idx] & 1) && !is_open_bracket(prevc)) o[m++] = 0x200b;
            o[m++] = w; prevjp = 1; prevc = w; *hasjp = 1; i += 2;
            continue;
        }
        /* 日本語の字のあとの英数字の前にも切れ目を入れる（空白のない文で長い行を作らないように） */
        o[m++] = (wchar_t)(c < 0x80 ? c : c);   /* 0x80 以上の単独のバイトはそのまま（Latin-1） */
        prevjp = 0; prevc = 0; i++;
    }
    o[m] = 0;
    return m;
}

/* ------------------------------------------------------------ フォント */
typedef struct { LONG h; LONG w; LONG weight; BYTE q; HFONT jp; } fcache_t;
static fcache_t g_fc[32]; static int g_nfc;
static CRITICAL_SECTION g_fcs;
static HFONT jp_font_for(HDC dc)
{
    HFONT cur = (HFONT)GetCurrentObject(dc, OBJ_FONT);
    LOGFONTW lf;
    int i;
    if (!cur || !GetObjectW(cur, sizeof lf, &lf)) return NULL;
    EnterCriticalSection(&g_fcs);
    for (i = 0; i < g_nfc; i++)
        if (g_fc[i].h == lf.lfHeight && g_fc[i].weight == lf.lfWeight && g_fc[i].q == lf.lfQuality) { LeaveCriticalSection(&g_fcs); return g_fc[i].jp; }
    {
        LOGFONTW j = lf;
        HFONT f;
        j.lfCharSet = SHIFTJIS_CHARSET;
        j.lfWidth = 0;
        j.lfItalic = 0;
        j.lfPitchAndFamily = FIXED_PITCH | FF_MODERN;
        lstrcpyW(j.lfFaceName, L"\xff2d\xff33 \x30b4\x30b7\x30c3\x30af");   /* ＭＳ ゴシック（小さい字はビットマップで描かれる） */
        if (j.lfHeight > 0) {   /* セルの高さで指定されている: 日本語のフォントは同じ高さの字の高さに */
            TEXTMETRICW tm; GetTextMetricsW(dc, &tm);
            j.lfHeight = -(tm.tmHeight - tm.tmInternalLeading);
        }
        f = CreateFontIndirectW(&j);
        if (g_nfc < 32) { g_fc[g_nfc].h = lf.lfHeight; g_fc[g_nfc].weight = lf.lfWeight; g_fc[g_nfc].q = lf.lfQuality; g_fc[g_nfc].jp = f; g_nfc++; }
        LeaveCriticalSection(&g_fcs);
        return f;
    }
}

/* ------------------------------------------------------------ 差し替える関数 */
static int WINAPI my_DrawTextA(HDC dc, LPCSTR s, int n, LPRECT rc, UINT fmt)
{
    wchar_t buf[8192];
    int m, jp, r;
    HFONT old = NULL, jf;
    if (n < 0) n = s ? lstrlenA(s) : 0;
    if (n > 4000) n = 4000;
    m = to_wide(s, n, buf, 8192, (fmt & DT_WORDBREAK) != 0, &jp);
    if (g_logon) dbg("DrawTextA %.*s| n=%d fmt=%x from %p\n", n, s, n, fmt, _ReturnAddress());
    if (jp && (jf = jp_font_for(dc))) old = (HFONT)SelectObject(dc, jf);
    r = DrawTextW(dc, buf, m, rc, fmt & ~DT_MODIFYSTRING);
    if (old) SelectObject(dc, old);
    return r;
}
static BOOL WINAPI my_GetTextExtentPointA(HDC dc, LPCSTR s, int n, LPSIZE sz)
{
    wchar_t buf[8192];
    int m, jp;
    BOOL r;
    HFONT old = NULL, jf;
    if (n > 4000) n = 4000;
    m = to_wide(s, n, buf, 8192, 0, &jp);
    if (jp && (jf = jp_font_for(dc))) old = (HFONT)SelectObject(dc, jf);
    r = GetTextExtentPoint32W(dc, buf, m, sz);
    if (old) SelectObject(dc, old);
    return r;
}

#include "fonthook.h"
#include "testio.h"

/* ------------------------------------------------------------ ファイル */
static const char *base_name(const char *p)
{
    const char *b = p, *q;
    for (q = p; *q; q++) if (*q == '\\' || *q == '/' || *q == ':') b = q + 1;
    return b;
}
static int write_all_w(const wchar_t *path, const uint8_t *b, uint32_t n)
{
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD w;
    if (h == INVALID_HANDLE_VALUE) return 0;
    WriteFile(h, b, n, &w, NULL);
    CloseHandle(h);
    return w == n;
}
static HANDLE WINAPI my_CreateFileA(LPCSTR name, DWORD acc, DWORD share, LPSECURITY_ATTRIBUTES sa, DWORD disp, DWORD fl, HANDLE tmpl)
{
    wchar_t wn[MAX_PATH * 2];
    int i;
    hook_game();
    if (name && g_enabled && !(acc & GENERIC_WRITE)) {
        const char *bn = base_name(name);
        for (i = 0; i < g_nfrep; i++) {
            frep_t *f = &g_frep[i];
            wchar_t wp[MAX_PATH];
            char pa[MAX_PATH];
            if (lstrcmpiA(bn, f->name)) continue;
            if (f->osize) {
                WIN32_FILE_ATTRIBUTE_DATA a;
                MultiByteToWideChar(CP_ACP, 0, name, -1, wn, MAX_PATH * 2);
                if (!GetFileAttributesExW(wn, GetFileExInfoStandard, &a) || a.nFileSizeLow != f->osize) { dbg("size mismatch %s\n", bn); break; }
            }
            wsprintfA(pa, "%s\\%08X_%s", g_dir, g_blob_crc, f->name);
            MultiByteToWideChar(CP_ACP, 0, pa, -1, wp, MAX_PATH);
            if (GetFileAttributesW(wp) == INVALID_FILE_ATTRIBUTES) write_all_w(wp, f->data, f->size);
            dbg("redirect %s -> %s\n", name, pa);
            return CreateFileW(wp, acc, share, sa, disp, fl, tmpl);
        }
    }
    MultiByteToWideChar(CP_ACP, 0, name ? name : "", -1, wn, MAX_PATH * 2);
    return CreateFileW(wn, acc, share, sa, disp, fl, tmpl);
}

/* ------------------------------------------------------------ 関数の入口を書き換える（jmp） */
static int hook(const char *dll, const char *fn, void *to)
{
    HMODULE m = GetModuleHandleA(dll);
    uint8_t *p;
    DWORD old;
    if (!m) m = LoadLibraryA(dll);
    if (!m) return 0;
    p = (uint8_t*)GetProcAddress(m, fn);
    if (!p) return 0;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int32_t*)(p + 1) = (int32_t)((uint8_t*)to - (p + 5));
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
    dbg("hooked %s!%s\n", dll, fn);
    return 1;
}

static BOOL WINAPI my_TextOutA(HDC dc, int x, int y, LPCSTR s, int n)
{
    wchar_t buf[4096]; int m, jp;
    m = to_wide(s, n > 4000 ? 4000 : n, buf, 4096, 0, &jp);
    if (g_logon) dbg("TextOutA n=%d from %p\n", n, _ReturnAddress());
    return TextOutW(dc, x, y, buf, m);
}
static BOOL WINAPI my_ExtTextOutA(HDC dc, int x, int y, UINT o, const RECT *rc, LPCSTR s, UINT n, const INT *dx)
{
    wchar_t buf[4096]; int m, jp;
    m = to_wide(s, n > 4000 ? 4000 : (int)n, buf, 4096, 0, &jp);
    if (g_logon) dbg("ExtTextOutA n=%d from %p\n", n, _ReturnAddress());
    return ExtTextOutW(dc, x, y, o, rc, buf, m, NULL);
}
static LONG CALLBACK veh(EXCEPTION_POINTERS *e)
{
    static int n;
    CONTEXT *c = e->ContextRecord;
    if (e->ExceptionRecord->ExceptionCode == 0xC0000005 && n++ < 5) {
        uint32_t *sp = (uint32_t*)c->Esp; int i;
        dbg("AV at %08X addr %08X eax=%08X ebx=%08X ecx=%08X edx=%08X esi=%08X edi=%08X ebp=%08X esp=%08X\n",
            (unsigned)c->Eip, (unsigned)e->ExceptionRecord->ExceptionInformation[1], (unsigned)c->Eax, (unsigned)c->Ebx, (unsigned)c->Ecx,
            (unsigned)c->Edx, (unsigned)c->Esi, (unsigned)c->Edi, (unsigned)c->Ebp, (unsigned)c->Esp);
        for (i = 0; i < 24; i++) dbg(" %08X", sp[i]);
        dbg("\n");
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
static void init(HMODULE self)
{
    char la[MAX_PATH], v[8];
    InitializeCriticalSection(&g_fcs);
    if (!GetEnvironmentVariableA("LOCALAPPDATA", la, MAX_PATH)) return;
    wsprintfA(g_dir, "%s\\XC_JP_INTC", la);
    CreateDirectoryA(g_dir, NULL);
    g_logon = GetEnvironmentVariableA("XI_LOG", v, sizeof v) > 0;
    if (GetEnvironmentVariableA("XI_TEST", v, sizeof v) > 0) testio_init();
    if (GetEnvironmentVariableA("XI_NOJP", v, sizeof v) > 0) return;
    if (!load_blob(self)) { dbg("no patch data\n"); return; }
    g_enabled = 1;
    hook("user32.dll", "DrawTextA", (void*)my_DrawTextA);
    hook("gdi32.dll", "GetTextExtentPointA", (void*)my_GetTextExtentPointA);
    hook("kernel32.dll", "CreateFileA", (void*)my_CreateFileA);
    if (g_logon) { hook("gdi32.dll", "TextOutA", (void*)my_TextOutA); hook("gdi32.dll", "ExtTextOutA", (void*)my_ExtTextOutA); }
    dbg("X-COM Interceptor JP patch active, blob %08X\n", g_blob_crc);
    if (g_logon) AddVectoredExceptionHandler(1, veh);
    hook_game();
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
