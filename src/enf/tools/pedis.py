# DLL の関数を逆アセンブル: python tools/pedis.py DLL 名前|0xVA [行数]   （増分リンクの jmp をたどる）
import sys, pefile
from capstone import *
pe = pefile.PE(sys.argv[1]); base = pe.OPTIONAL_HEADER.ImageBase
sym = {e.name.decode(): e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
a = sys.argv[2]
va = int(a, 16) if a.startswith('0x') else base + sym[a]
md = Cs(CS_ARCH_X86, CS_MODE_32)
data = pe.get_data(va - base, 5)
if data[0] == 0xe9: va = va + 5 + int.from_bytes(data[1:5], 'little', signed=True)
n = int(sys.argv[3]) if len(sys.argv) > 3 else 60
data = pe.get_data(va - base, n * 8)
for i, ins in enumerate(md.disasm(data, va)):
    print(hex(ins.address), ins.bytes.hex(), ins.mnemonic, ins.op_str)
    if i >= n: break
