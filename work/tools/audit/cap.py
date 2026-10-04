import pickle,capstone,struct,sys
a=pickle.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'raw.pkl'),'rb'))['arm9']; base=0x02000000
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB)
def dis(addr,n=40):
    for i in md.disasm(a[addr-base:addr-base+2*n],addr):
        extra=''
        if i.mnemonic.startswith('ldr') and 'pc' in i.op_str:
            off=int(i.op_str.split('#')[1].rstrip(']'),16); lit=((i.address+4)&~3)+off
            extra=' ; =0x%08X'%struct.unpack_from('<I',a,lit-base)[0]
        print(hex(i.address),i.mnemonic,i.op_str,extra)
if __name__=='__main__':
    for x in sys.argv[1:]:
        if x.startswith('op'):
            op=int(x[2:]); p=struct.unpack_from('<I',a,0x020F793C-base+4*op)[0]&~1; print('--- op',op,hex(p)); dis(p)
        else: print('---',x); dis(int(x,16))
