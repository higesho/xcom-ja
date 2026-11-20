import sys, capstone
m=open(sys.argv[1] if len(sys.argv)>3 else 'work/mem.bin','rb').read()
a=int(sys.argv[-2],16); n=int(sys.argv[-1])
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
c=0
for ins in md.disasm(m[a-0x400000:a-0x400000+n*8],a):
    print('%08x: %-20s %s %s'%(ins.address,ins.bytes.hex(),ins.mnemonic,ins.op_str)); c+=1
    if c>=n: break
