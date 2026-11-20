# linear disassembly of the code object (skips undecodable bytes) -> build/dis.txt
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from le import LE
L = LE()
code = bytes(L.img[0][:L.objs[0]['vsize']])
out = []; p = 0
while p < len(code):
    n = 0
    for i in L.md.disasm(code[p:], 0x10000 + p):
        out.append('%08x: %-20s %s %s' % (i.address, i.bytes.hex(), i.mnemonic, i.op_str)); n += i.size
    p += n
    if p < len(code): out.append('%08x: %02x ??' % (0x10000 + p, code[p])); p += 1
open(os.path.join(os.path.dirname(__file__), '..', 'build', 'dis.txt'), 'w').write('\n'.join(out))
print(len(out))
