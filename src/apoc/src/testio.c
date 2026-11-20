/*
 * テスト用: DOSBox の画面（SDL の画面サーフェス）を BMP に書き出す。環境変数 XC_TEST=1 のときだけ動く。
 * 共有メモリ "XC_TESTIO": magic, req, ack, frame, path[260]
 *   tools/win.py shot が path を書いて req を増やす → ここで path に BMP を書き、ack = req にする。
 * ウィンドウの描画（PrintWindow や画面の取り込み）に頼らないので、ウィンドウが白いままでも撮れる。
 */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* +276: 入力の受け渡し（tools/win.py が ev を書いて ereq を増やす → SDL_PushEvent → eack = ereq）
 *   ev[0] 種類（2 キー押す, 3 キー離す, 4 マウス移動, 5 ボタン押す, 6 ボタン離す）, ev[1] sym/ボタン, ev[2] scancode/x, ev[3] y */
typedef struct { uint32_t magic; volatile int32_t req, ack, frame; char path[260]; volatile int32_t ereq, eack; int32_t ev[4]; volatile int32_t gx, gy, gok, pad; } shm_t;   /* +300: ゲームのマウス位置（xc_jp.c が書く） */
typedef struct { uint8_t r, g, b, unused; } sdl_color;
typedef struct { int ncolors; sdl_color *colors; } sdl_palette;
typedef struct {
    sdl_palette *palette; uint8_t bpp, Bpp, Rloss, Gloss, Bloss, Aloss, Rshift, Gshift, Bshift, Ashift;
    uint32_t Rmask, Gmask, Bmask, Amask;
} sdl_format;
typedef struct { uint32_t flags; sdl_format *format; int w, h; uint16_t pitch; void *pixels; } sdl_surface;

static shm_t *g_shm;
void testio_mouse(int x, int y) { if (g_shm) { g_shm->gx = x; g_shm->gy = y; g_shm->gok = 1; } }
static sdl_surface *volatile g_screen;
typedef void (__cdecl *upd_t)(void *, int, void *);
typedef int (__cdecl *flip_t)(void *);
static upd_t real_upd;
static flip_t real_flip;

static void save_bmp(const sdl_surface *s, const char *path);
static volatile LONG g_busy;
static DWORD g_req_tick;
/* 画面を更新した直後に撮る（描きかけの画面を撮らないように）。更新がないときは shot_thread が撮る */
static void frame_done(void *s)
{
    g_screen = (sdl_surface*)s;
    if (!g_shm) return;
    g_shm->frame++;
    if (g_shm->req != g_shm->ack && !InterlockedExchange(&g_busy, 1)) {
        int r = g_shm->req;
        save_bmp(g_screen, g_shm->path);
        g_shm->ack = r;
        InterlockedExchange(&g_busy, 0);
    }
}
static void __cdecl hook_upd(void *s, int n, void *r) { real_upd(s, n, r); frame_done(s); }
static int __cdecl hook_flip(void *s) { int v = real_flip(s); frame_done(s); return v; }

static void save_bmp(const sdl_surface *s, const char *path)
{
    int w = s->w, h = s->h, x, y, stride = (w * 3 + 3) & ~3;
    const sdl_format *f = s->format;
    BITMAPFILEHEADER fh = {0}; BITMAPINFOHEADER ih = {0};
    uint8_t *row;
    FILE *o;
    /* ハードウェアのサーフェスは鍵をかけないと画素が読めない */
    static int (__cdecl *lock)(void *); static void (__cdecl *unlock)(void *);
    if (!lock) { HMODULE m = GetModuleHandleA("SDL.dll"); lock = (int (__cdecl*)(void*))GetProcAddress(m, "SDL_LockSurface"); unlock = (void (__cdecl*)(void*))GetProcAddress(m, "SDL_UnlockSurface"); }
    if (lock && lock((void*)s) < 0) return;
    if (!s->pixels || !f) { if (unlock) unlock((void*)s); return; }
    row = (uint8_t*)malloc(stride);
    o = fopen(path, "wb");
    if (!o || !row) { if (o) fclose(o); free(row); return; }
    fh.bfType = 0x4d42; fh.bfOffBits = sizeof fh + sizeof ih; fh.bfSize = fh.bfOffBits + stride * h;
    ih.biSize = sizeof ih; ih.biWidth = w; ih.biHeight = -h; ih.biPlanes = 1; ih.biBitCount = 24;
    fwrite(&fh, sizeof fh, 1, o); fwrite(&ih, sizeof ih, 1, o);
    for (y = 0; y < h; y++) {
        const uint8_t *p = (const uint8_t*)s->pixels + y * s->pitch;
        memset(row, 0, stride);
        for (x = 0; x < w; x++) {
            uint32_t v; uint8_t r, g, b;
            if (f->Bpp == 1) {
                sdl_color c = f->palette->colors[p[x]]; r = c.r; g = c.g; b = c.b;
            } else {
                if (f->Bpp == 2) v = ((const uint16_t*)p)[x];
                else if (f->Bpp == 3) v = p[x * 3] | (p[x * 3 + 1] << 8) | (p[x * 3 + 2] << 16);
                else v = ((const uint32_t*)p)[x];
                r = (uint8_t)(((v & f->Rmask) >> f->Rshift) << f->Rloss);
                g = (uint8_t)(((v & f->Gmask) >> f->Gshift) << f->Gloss);
                b = (uint8_t)(((v & f->Bmask) >> f->Bshift) << f->Bloss);
            }
            row[x * 3] = b; row[x * 3 + 1] = g; row[x * 3 + 2] = r;
        }
        fwrite(row, 1, stride, o);
    }
    fclose(o); free(row);
    if (unlock) unlock((void*)s);
}

/* テスト中の窓に固有の題名を付ける（他の DOSBox と取り違えないように）。DOSBox が題名を変えるたびに頭に付ける */
typedef void (__cdecl *cap_t)(const char *, const char *);
static cap_t real_cap;
static void __cdecl hook_cap(const char *t, const char *i)
{
    char b[300];
    wsprintfA(b, "XCOMJP-TEST %u | %s", GetCurrentProcessId(), t ? t : "");
    real_cap(b, i);
}
static int (__cdecl *sdl_push)(void *);
static int g_lx, g_ly;            /* 最後に送ったカーソルの位置（640x480） */
static void push_event(void)
{
    uint8_t e[24];
    int t = g_shm->ev[0];
    memset(e, 0, sizeof e);
    e[0] = (uint8_t)t;
    if (t == 2 || t == 3) {                  /* SDL_KeyboardEvent: type, which, state, keysym{scancode u8, sym i32 @4, mod @8, unicode u16 @12} */
        e[2] = t == 2 ? 1 : 0;
        e[4] = (uint8_t)g_shm->ev[2];
        *(int32_t*)(e + 8) = g_shm->ev[1];
    } else if (t == 8) {                     /* カーソルを左上へ（相対で大きく動かす。ゲームが位置を変えてもずれない） */
        e[0] = 4;
        *(int16_t*)(e + 8) = -2000; *(int16_t*)(e + 10) = -2000;
        if (sdl_push) sdl_push(e);
        memset(e, 0, sizeof e); e[0] = 4;
        g_lx = 0; g_ly = 0;
    } else if (t == 4 || t == 7) {           /* SDL_MouseMotionEvent: type, which, state, x u16 @4, y @6, xrel @8, yrel @10 */
        int nx = t == 7 ? g_lx + g_shm->ev[2] : g_shm->ev[2], ny = t == 7 ? g_ly + g_shm->ev[3] : g_shm->ev[3];
        e[0] = 4;
        *(int16_t*)(e + 8) = (int16_t)(t == 7 ? g_shm->ev[2] : nx - g_lx);
        *(int16_t*)(e + 10) = (int16_t)(t == 7 ? g_shm->ev[3] : ny - g_ly);
        if (nx < 0) nx = 0;
        if (ny < 0) ny = 0;
        if (nx > 639) nx = 639;
        if (ny > 479) ny = 479;
        *(uint16_t*)(e + 4) = (uint16_t)nx;
        *(uint16_t*)(e + 6) = (uint16_t)ny;
        g_lx = nx; g_ly = ny;
    } else if (t == 5 || t == 6) {           /* SDL_MouseButtonEvent: type, which, button, state, x u16 @4, y @6 */
        e[2] = (uint8_t)g_shm->ev[1];
        e[3] = t == 5 ? 1 : 0;
        *(uint16_t*)(e + 4) = (uint16_t)g_shm->ev[2];
        *(uint16_t*)(e + 6) = (uint16_t)g_shm->ev[3];
    }
    if (sdl_push) sdl_push(e);
}
static DWORD WINAPI shot_thread(LPVOID p)
{
    (void)p;
    int last = 0;
    for (;;) {
        Sleep(30);
        if (g_shm->ereq != g_shm->eack) { int r = g_shm->ereq; push_event(); g_shm->eack = r; }
        if (g_shm->req == g_shm->ack) { last = g_shm->req; g_req_tick = 0; continue; }
        if (!g_req_tick) { g_req_tick = GetTickCount(); continue; }
        if (GetTickCount() - g_req_tick < 400) continue;          /* 400ms 画面の更新がなければここで撮る */
        if (g_screen && !InterlockedExchange(&g_busy, 1)) {
            int r = g_shm->req;
            if (r != g_shm->ack) { save_bmp(g_screen, g_shm->path); g_shm->ack = r; }
            InterlockedExchange(&g_busy, 0);
        }
        (void)last;
    }
}

static void patch_iat(HMODULE m, const char *dll, const char *fn, void *hook, void **orig)
{
    uint8_t *b = (uint8_t*)m;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS*)(b + ((IMAGE_DOS_HEADER*)b)->e_lfanew);
    IMAGE_DATA_DIRECTORY dd = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR*)(b + dd.VirtualAddress);
    for (; d->Name; d++) {
        IMAGE_THUNK_DATA *ot, *ft;
        if (lstrcmpiA((const char*)(b + d->Name), dll)) continue;
        ot = (IMAGE_THUNK_DATA*)(b + d->OriginalFirstThunk); ft = (IMAGE_THUNK_DATA*)(b + d->FirstThunk);
        for (; ot->u1.AddressOfData; ot++, ft++) {
            IMAGE_IMPORT_BY_NAME *ibn;
            DWORD old;
            if (ot->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            ibn = (IMAGE_IMPORT_BY_NAME*)(b + ot->u1.AddressOfData);
            if (strcmp((const char*)ibn->Name, fn)) continue;
            *orig = (void*)ft->u1.Function;
            VirtualProtect(&ft->u1.Function, 4, PAGE_READWRITE, &old);
            ft->u1.Function = (DWORD)(uintptr_t)hook;
            VirtualProtect(&ft->u1.Function, 4, old, &old);
        }
    }
}

void testio_init(void)
{
    char v[8];
    HANDLE h;
    if (!GetEnvironmentVariableA("XC_TEST", v, sizeof v) || v[0] != '1') return;
    h = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(shm_t), "XC_TESTIO");
    if (!h) return;
    g_shm = (shm_t*)MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(shm_t));
    if (!g_shm) return;
    g_shm->magic = 0x54534554;
    g_shm->req = g_shm->ack = 0;
    patch_iat(GetModuleHandleA(NULL), "SDL.dll", "SDL_UpdateRects", (void*)hook_upd, (void**)&real_upd);
    patch_iat(GetModuleHandleA(NULL), "SDL.dll", "SDL_Flip", (void*)hook_flip, (void**)&real_flip);
    patch_iat(GetModuleHandleA(NULL), "SDL.dll", "SDL_WM_SetCaption", (void*)hook_cap, (void**)&real_cap);
    sdl_push = (int (__cdecl*)(void*))GetProcAddress(GetModuleHandleA("SDL.dll"), "SDL_PushEvent");
    CreateThread(NULL, 0, shot_thread, NULL, 0, NULL);
}
