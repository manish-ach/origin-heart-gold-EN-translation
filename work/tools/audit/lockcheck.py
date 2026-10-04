"""Abstract-interpret lock state; find paths that End while LockAll is active, or abort."""
import sys, collections, json
sys.setrecursionlimit(100000)
import core, sdis as dis
A=dis.all_files(); STD=core.std_mapping()
def std_target(sid):
    for lo,sb,mb in STD:
        if sid>=lo: return sb, sid-lo
    return None
MEMO={}
RESULTS=collections.defaultdict(set)  # (file,entry) -> set of (kind, pc)
def run(f,pc,locked,depth=0):
    """returns set of lock states at Return; records End states. path-insensitive over pc with memo."""
    key=(f,pc,locked)
    if key in MEMO: return MEMO[key]
    MEMO[key]=set()  # cycle guard
    d=A.get(f); ins=d['ins'] if d else {}
    rets=set(); ends=set()
    st=[(pc,locked)]; seen=set()
    while st:
        p,l=st.pop()
        if (p,l) in seen: continue
        seen.add((p,l))
        if p not in ins:
            ends.add(('abort',p,l)); continue
        op,a,n,t=ins[p]
        if op==96: l=True
        elif op==97: l=False
        elif op==176: l=None   # warp: map reload
        if op==2: ends.add(('end',p,l)); continue
        if op==27: rets.add(l); continue
        if op in (26,29):  # call
            sub=run(f,t,l,depth+1)
            for s in sub: st.append((n,s))
            if op==29: st.append((n,l))
            continue
        if op==20:
            tg=std_target(a[0])
            if tg and tg[0] in A and A[tg[0]]['kind']=='script' and tg[1]<len(A[tg[0]]['entries']):
                sub=run(tg[0],A[tg[0]]['entries'][tg[1]],l,depth+1)
                # std scripts end with End? treat End inside std as return
                for s in sub: st.append((n,s))
                for e in STDENDS.get((tg[0],tg[1],l),()): st.append((n,e))
                if not sub and not STDENDS.get((tg[0],tg[1],l)): st.append((n,l))
            else: st.append((n,l))
            continue
        if t is not None:
            st.append((t,l))
            if dis.JUMPS[op]: continue
        st.append((n,l))
    MEMO[key]=rets
    ENDS[key]=ends
    return rets
ENDS={}
STDENDS={}
def std_ends(f,ei,l):
    e=A[f]['entries'][ei]; run(f,e,l)
    return set(x[2] for x in ENDS.get((f,e,l),()) if x[0]=='end')
if __name__=='__main__':
    # pass 1: std files end states (CallStd: std script's End returns to caller? no -> CallStd is a call; std scripts end with Return)
    out=[]
    for f,d in A.items():
        if d['kind']!='script': continue
        for ei,e in enumerate(d['entries']):
            run(f,e,False)
            for kind,p,l in ENDS.get((f,e,False),()):
                if l and kind=='end': out.append(('END_LOCKED',f,ei+1,p))
                if kind=='abort': out.append(('ABORT',f,ei+1,p,l))
    json.dump(out,open(core.D+'/lockcheck.json','w'))
    c=collections.Counter(x[0] for x in out); print(c)
    for x in out[:40]: print(x)
