# 動いているゲームのメモリから Interceptor.exe の像（0x400000〜）を取り出す（DRM で暗号化されたコードを調べるため）
import ctypes, ctypes.wintypes as W, sys, os
k = ctypes.windll.kernel32
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
pid = int(open(os.path.join(ROOT, 'test', 'pid.txt')).read())
h = k.OpenProcess(0x0410, False, pid)
base = 0x400000
import pefile
pe = pefile.PE(os.path.join(ROOT, 'orig', 'Interceptor.exe'), fast_load=True)
size = pe.OPTIONAL_HEADER.SizeOfImage
buf = ctypes.create_string_buffer(size)
out = bytearray(size)
step = 0x1000
for off in range(0, size, step):
    n = ctypes.c_size_t()
    if k.ReadProcessMemory(h, ctypes.c_void_p(base + off), buf, step, ctypes.byref(n)):
        out[off:off + step] = buf.raw[:step]
open(os.path.join(ROOT, 'work', 'mem.bin'), 'wb').write(out)
print('dumped', hex(size))
