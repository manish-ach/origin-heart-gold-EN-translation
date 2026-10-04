import json, struct, sys, os, pickle
import ndspy.rom, ndspy.narc
D=os.path.dirname(os.path.abspath(__file__))
C={int(k):v for k,v in json.load(open(D+'/cmds.json')).items()}
BR={22:1,23:1,24:1,25:1,26:0,28:0,29:0,225:0}  # 1 = unconditional
TERM={2,27,22}
def argsizes(op,data,p):
    c=C[op]
    if op in (400,401,402):
        a=data[p]; return [1,2] if a==2 else [1]
    if op==465:
        a=struct.unpack_from('<H',data,p)[0]
        return [2,2,2] if a<=3 else ([2] if a==6 else [2,2])
    if op==489:
        a=struct.unpack_from('<H',data,p)[0]
        return [2,2] if 1<=a<=3 else ([2,2,2] if a in (5,6) else [2])
    return c['args']
def disasm(data):
    # header
    entries=[];p=0
    while p+2<=len(data):
        if struct.unpack_from('<H',data,p)[0]==0xFD13: break
        off=struct.unpack_from('<i',data,p)[0]; entries.append(p+4+off); p+=4
    todo=list(entries); seen={}; errs=[]
    while todo:
        pc=todo.pop()
        while pc<len(data) and pc not in seen:
            if pc+2>len(data): errs.append(('eof',pc)); break
            op=struct.unpack_from('<H',data,pc)[0]
            if op not in C: errs.append(('badop',pc,op)); break
            q=pc+2; args=[]
            for s in argsizes(op,data,q):
                if q+s>len(data): errs.append(('trunc',pc)); break
                v=int.from_bytes(data[q:q+s],'little',signed=(s==4)); args.append(v); q+=s
            seen[pc]=(op,args,q)
            if op in BR:
                tgt=q+args[-1]; todo.append(tgt)
                if BR[op]: break
            if op in TERM: break
            pc=q
    return entries,seen,errs
def load_scripts(romkey, path):
    cache=D+'/scr_%s.pkl'%romkey
    if os.path.exists(cache): return pickle.load(open(cache,'rb'))
    rom=ndspy.rom.NintendoDSRom.fromFile(path)
    n=ndspy.narc.NARC(rom.getFileByName('a/0/1/2'))
    out={}
    for i,f in enumerate(n.files):
        try: out[i]=disasm(f)
        except Exception as e: out[i]=([],{},[('exc',str(e))])
    pickle.dump(out,open(cache,'wb')); return out
if __name__=='__main__':
    s=load_scripts(sys.argv[1],sys.argv[2])
    nerr=sum(1 for v in s.values() if v[2]); print('files',len(s),'with errors',nerr, 'cmds', sum(len(v[1]) for v in s.values()))
    for k,v in list(s.items()):
        if v[2]: print(k,v[2][:3])
