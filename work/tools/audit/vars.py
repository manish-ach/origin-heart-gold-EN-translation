import collections, json
import core, index
o=index.load(); R=o['rec']; EV=o['ev']; Z=core.zones(); LV=o['lv']
VA=core.consts('vars.h','VAR_')
sets=collections.defaultdict(set); adds=collections.defaultdict(list); copies=collections.defaultdict(list); cmps=collections.defaultdict(list)
for x in R:
    k=x['kind']
    if k=='var_set': sets[x['id']].add(x['v'])
    elif k in ('var_add','var_sub'): adds[x['id']].append((x['file'],x['pc']))
    elif k=='var_copy': copies[x['id']].append((x['file'],x['pc'],x['v']))
    elif k=='var_cmp': cmps[x['id']].append((x['v'],x['file'],x['pc']))
def reachable_vals(v):
    s=set(sets[v])|{0}
    return s, bool(adds[v] or copies[v])
evz=collections.defaultdict(list)
for z in Z: evz[z['events_bank']].append(z['zone_id'])
out={'coord_perm':[], 'coord_never':[], 'scene_never':[], 'cmp_never':[]}
for b,e in EV.items():
    for i,c in enumerate(e['coord']):
        v=c['var']; vals,dyn=reachable_vals(v)
        if dyn: continue
        if c['val'] not in vals: out['coord_never'].append((evz[b],i,c,VA.get(v),sorted(vals)))
        elif vals=={c['val']}: out['coord_perm'].append((evz[b],i,c,VA.get(v)))
hz=collections.defaultdict(list)
for z in Z: hz[z['script_header_bank']].append(z['zone_id'])
for f,lv in LV.items():
    for t,val in lv:
        if t==1:
            for (v1,v2,s) in val:
                if v2<0x4000:
                    vals,dyn=reachable_vals(v1)
                    if not dyn and v2 not in vals: out['scene_never'].append((hz[f],v1,VA.get(v1),v2,s,sorted(vals)))
for v,L in cmps.items():
    if v<0x4020 or v>=0x8000: continue
    vals,dyn=reachable_vals(v)
    if dyn: continue
    miss=sorted(set(c[0] for c in L if c[0] not in vals and c[0]<0x4000))
    if miss: out['cmp_never'].append((hex(v),VA.get(v),miss,sorted(vals),[c for c in L if c[0] in miss][:4]))
json.dump(out,open(core.D+'/vars%s.json'%core.SUF,'w'),default=str,indent=0)
for k,v in out.items(): print(k,len(v))
