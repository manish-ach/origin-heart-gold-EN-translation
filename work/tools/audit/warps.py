import collections, json
import core, index
o=index.load(); Z=core.zones(); EV=o['ev']
G=collections.defaultdict(set); kinds={}
fz=collections.defaultdict(list)
for z in Z: fz[z['scripts_bank']].append(z['zone_id'])
for z in Z:
    e=EV[z['events_bank']]
    for w in e['warp']:
        if w['dest']<len(Z): G[z['zone_id']].add(w['dest']); kinds[(z['zone_id'],w['dest'])]='warp'
    for n in z['outdoor_neighbours']:
        G[z['zone_id']].add(n); kinds[(z['zone_id'],n)]='adj'
SW=collections.defaultdict(set)
for x in o['rec']:
    if x['kind'] in ('warp','dynwarp') and isinstance(x['id'],int) and x['id']<len(Z):
        for src in fz.get(x['file'],[]): SW[src].add(x['id'])
def bfs(start,graph):
    seen={start}; st=[start]
    while st:
        u=st.pop()
        for v in graph[u]:
            if v not in seen: seen.add(v); st.append(v)
    return seen
# reverse graph
R=collections.defaultdict(set)
for u,vs in G.items():
    for v in vs: R[v].add(u)
name=lambda i:'%d %s/%s'%(i,Z[i]['map_name_en'],Z[i]['vanilla_const'])
# one-way event warps: u->v where u not reachable from v via G
oneway=[]
for u,vs in list(G.items()):
    for v in vs:
        if kinds[(u,v)]!='warp': continue
        back=bfs(v,G)
        if u not in back: oneway.append((u,v,sorted(back)[:0]))
json.dump([(name(u),name(v)) for u,v,_ in oneway],open(core.D+'/oneway.json','w'),indent=0)
print('one-way event warps',len(oneway))
for u,v,_ in oneway: print('  ',name(u),'->',name(v), '| fly' if Z[v]['fly_allowed'] else '', '| scriptwarps from dest:',[name(x) for x in SW.get(v,[])][:3])
# full graph incl script warps
F=collections.defaultdict(set)
for u,vs in G.items(): F[u]|=vs
for u,vs in SW.items(): F[u]|=vs
S=bfs(64,F)
print('reachable from 64:',len(S),'of',len(Z))
traps=[]
for x in sorted(S):
    if 64 not in bfs(x,F): traps.append(x)
print('trap zones (no way back to start without Fly/Rope/Teleport):',len(traps))
for x in traps: print('  ',name(x),Z[x]['map_type'],'fly' if Z[x]['fly_allowed'] else '')
unreach=[z['zone_id'] for z in Z if z['zone_id'] not in S and EV[z['events_bank']]['warp']]
print('zones with warps but unreachable from start:',len(unreach))
for x in unreach: print('  ',name(x))
