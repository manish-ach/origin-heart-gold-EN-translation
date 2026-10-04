import collections, json
import core, index
o=index.load(); R=o['rec']; EV=o['ev']; Z=core.zones()
FL=core.consts('flags.h','FLAG_')
def rng(f):
    if 1<=f<=0x40: return 'maptemp'
    if f<0x64: return 'misc'
    if f<0x190: return 'story'
    if f<0x320: return 'hideshow'
    if f<0x420: return 'hidden'
    if f<0x550: return 'itemball'
    if f<0x960: return 'trainer'
    if f<0xAA0: return 'system'
    if f<0xB60: return 'daily'
    if 0x4000<=f<0x4040: return 'temp'
    return 'other'
S=collections.defaultdict(lambda: collections.defaultdict(list))
for x in R:
    if x['kind'] in ('flag_set','flag_clear','flag_check') and isinstance(x['id'],int):
        S[x['id']][x['kind']].append((x['file'],x['pc'],tuple(x['entries'])))
# objects hide flags
objflag=collections.defaultdict(list)
evzones=collections.defaultdict(list)
for z in Z: evzones[z['events_bank']].append(z['zone_id'])
for b,e in EV.items():
    for i,ob in enumerate(e['obj']):
        if ob['flag']: objflag[ob['flag']].append((b,i,ob['script'],ob['sprite']))
res={'checked_never_set':[], 'obj_never_shown':[], 'obj_flag_never_set':[]}
for f,d in S.items():
    r=rng(f)
    if r in ('maptemp','temp','trainer','daily'): continue
    if d['flag_check'] and not d['flag_set']:
        res['checked_never_set'].append((f,FL.get(f),r,len(d['flag_check']),d['flag_check'][:3],len(objflag.get(f,[]))))
for f,objs in objflag.items():
    d=S.get(f,{})
    r=rng(f)
    if r in ('maptemp','temp','trainer','itemball','hidden'): continue
    sets=d.get('flag_set',[]) if d else []; clears=d.get('flag_clear',[]) if d else []
    if sets and not clears:
        res['obj_never_shown'].append((f,FL.get(f),r,objs,len(sets),sets[:3]))
json.dump(res,open(core.D+'/flags%s.json'%core.SUF,'w'),indent=0,default=str)
for k,v in res.items(): print(k,len(v))
