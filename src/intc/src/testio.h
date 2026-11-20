/* ============================================================ テスト用の入力（環境変数 XI_TEST があるときだけ。xi_jp.c から #include する）
 * tools/win.py が共有メモリ "XI_TESTIO" に書いた要求を、DirectInput のキーボード・マウスの読み取りに混ぜる
 * （ゲームが前面にいなくても操作できるように。前面の窓は使わない）。
 *   共有メモリ: +0 'TEST', +4 要求の番号, +8 済んだ番号, +12 種類, +16 a, +20 b, +24 c
 *   種類 2 = キー (a = DIK, b = 1 押す / 0 離す)、5 = マウスのボタン (a = 0 左 / 1 右, b = 1 / 0)
 * DirectInputCreateA の入口に jmp を書き、作られた IDirectInput の CreateDevice を差し替え、
 * 作られた装置の GetDeviceState / GetDeviceData を差し替える。
 */
static volatile LONG *g_tio;
static volatile uint8_t g_tkey[256], g_tbtn[4];
typedef struct { DWORD ofs, data, time, seq; } didod_t;
static didod_t g_kq[64]; static volatile LONG g_kqh, g_kqt;     /* キーボードの出来事の待ち行列 */
static void *g_kbd, *g_mouse;
static const GUID G_KBD = {0x6F1D2B61, 0xD5A0, 0x11CF, {0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00}};
static const GUID G_MOUSE = {0x6F1D2B60, 0xD5A0, 0x11CF, {0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00}};
typedef HRESULT (__stdcall *gds_t)(void*, DWORD, void*);
typedef HRESULT (__stdcall *gdd_t)(void*, DWORD, didod_t*, DWORD*, DWORD);
typedef HRESULT (__stdcall *cdev_t)(void*, const GUID*, void**, void*);
typedef HRESULT (__stdcall *dicreate_t)(HINSTANCE, DWORD, void**, void*);
static gds_t o_gds; static gdd_t o_gdd; static cdev_t o_cdev; static dicreate_t o_dicreate;

static HRESULT __stdcall my_gds(void *dev, DWORD cb, void *data)
{
    HRESULT r = o_gds(dev, cb, data);
    int i;
    if (dev == g_kbd && cb == 256) {
        if (r != 0) { memset(data, 0, 256); r = 0; }
        for (i = 0; i < 256; i++) if (g_tkey[i]) ((uint8_t*)data)[i] |= 0x80;
    } else if (dev == g_mouse && cb >= 16) {
        if (r != 0) { memset(data, 0, cb); r = 0; }
        for (i = 0; i < 4 && 12 + i < (int)cb; i++) if (g_tbtn[i]) ((uint8_t*)data)[12 + i] |= 0x80;
    }
    return r;
}
static HRESULT __stdcall my_gdd(void *dev, DWORD cb, didod_t *buf, DWORD *n, DWORD fl)
{
    HRESULT r;
    DWORD cap = n ? *n : 0, got = 0;
    if (dev != g_kbd || !n) return o_gdd(dev, cb, buf, n, fl);
    r = o_gdd(dev, cb, buf, n, fl);
    if (r != 0 && r != 1) { *n = 0; r = 0; }
    got = *n;
    while (g_kqt != g_kqh && got < cap && buf) {      /* 待っているキーの出来事を後ろに足す */
        didod_t *d = (didod_t*)((uint8_t*)buf + got * cb);
        if (!(fl & 1)) {                              /* DIGDD_PEEK でなければ取り出す */
            *d = g_kq[g_kqt % 64]; InterlockedIncrement(&g_kqt);
        } else *d = g_kq[g_kqt % 64];
        got++;
        if (fl & 1) break;
    }
    *n = got;
    return r;
}
static void patch_vt(void **vt, int idx, void *to, void **orig)
{
    DWORD old;
    if (vt[idx] == to) return;
    VirtualProtect(&vt[idx], 4, PAGE_EXECUTE_READWRITE, &old);
    if (!*orig) *orig = vt[idx];
    vt[idx] = to;
    VirtualProtect(&vt[idx], 4, old, &old);
}
static HRESULT __stdcall my_cdev(void *di, const GUID *g, void **out, void *unk)
{
    HRESULT r = o_cdev(di, g, out, unk);
    if (r == 0 && out && *out) {
        void **vt = *(void***)*out;
        if (!memcmp(g, &G_KBD, sizeof(GUID))) g_kbd = *out;
        else if (!memcmp(g, &G_MOUSE, sizeof(GUID))) g_mouse = *out;
        patch_vt(vt, 9, (void*)my_gds, (void**)&o_gds);
        patch_vt(vt, 10, (void*)my_gdd, (void**)&o_gdd);
        dbg("test input: device %p kbd=%p mouse=%p\n", *out, g_kbd, g_mouse);
    }
    return r;
}
static HRESULT __stdcall my_dicreate(HINSTANCE h, DWORD ver, void **out, void *unk)
{
    HRESULT r = o_dicreate(h, ver, out, unk);
    if (r == 0 && out && *out) patch_vt(*(void***)*out, 3, (void*)my_cdev, (void**)&o_cdev);
    return r;
}
static DWORD WINAPI tio_thread(LPVOID p)
{
    LONG done = 0;
    (void)p;
    for (;;) {
        LONG req = g_tio[1];
        if (req != done) {
            LONG t = g_tio[3], a = g_tio[4], b = g_tio[5];
            if (t == 2 && a >= 0 && a < 256) {
                LONG h = g_kqh;
                g_tkey[a] = (uint8_t)(b != 0);
                g_kq[h % 64].ofs = (DWORD)a; g_kq[h % 64].data = b ? 0x80 : 0; g_kq[h % 64].time = GetTickCount(); g_kq[h % 64].seq = (DWORD)h + 1000;
                InterlockedIncrement(&g_kqh);
            } else if (t == 5 && a >= 0 && a < 4) g_tbtn[a] = (uint8_t)(b != 0);
            done = req; g_tio[2] = done;
        }
        Sleep(5);
    }
    return 0;
}
static void testio_init(void)
{
    HANDLE m = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, 64, "XI_TESTIO");
    HMODULE d = LoadLibraryA("dinput.dll");
    uint8_t *p, *t;
    DWORD old;
    if (!m || !d) return;
    g_tio = (volatile LONG*)MapViewOfFile(m, FILE_MAP_ALL_ACCESS, 0, 0, 64);
    if (!g_tio) return;
    g_tio[0] = 0x54534554; g_tio[1] = g_tio[2] = 0;
    p = (uint8_t*)GetProcAddress(d, "DirectInputCreateA");
    if (!p) return;
    /* 入口の命令を写して戻り口を作る（mov edi,edi / push ebp / mov ebp,esp の 5 バイトのときだけ） */
    if (memcmp(p, "\x8b\xff\x55\x8b\xec", 5)) { dbg("test input: unexpected DirectInputCreateA %02x %02x %02x %02x %02x\n", p[0], p[1], p[2], p[3], p[4]); return; }
    t = (uint8_t*)VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, p, 5); t[5] = 0xe9; *(int32_t*)(t + 6) = (int32_t)((p + 5) - (t + 10));
    o_dicreate = (dicreate_t)t;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int32_t*)(p + 1) = (int32_t)((uint8_t*)my_dicreate - (p + 5));
    VirtualProtect(p, 5, old, &old);
    CreateThread(NULL, 0, tio_thread, NULL, 0, NULL);
    dbg("test input ready\n");
}
