import pickle,capstone,struct,sys
a=pickle.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'raw.pkl'),'rb'))['arm9']; base=0x02000000
T=int(sys.argv[1],16) if len(sys.argv)>1 else 0x02029428
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
def blt(pc,h1,h2):
    if (h1>>11)!=0x1E or (h2>>11) not in (0x1F,0x1D): return None
    off=((h1&0x7FF)<<12)|((h2&0x7FF)<<1)
    if off&0x400000: off-=0x800000
    return pc+4+off
for p in range(0,len(a)-4,2):
    h1,h2=struct.unpack_from('<HH',a,p)
    t=blt(p+base,h1,h2)
    if t==T:
        ins=list(md.disasm(a[p-12:p+4],p+base-12))
        print(hex(p+base),' | '.join('%s %s'%(i.mnemonic,i.op_str) for i in ins[-6:]))
