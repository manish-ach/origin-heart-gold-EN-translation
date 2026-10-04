import index,core,collections,sdis,sys
o=index.load(); Z=core.zones(); IT=core.consts('items.h','ITEM_')
fz=collections.defaultdict(list)
for z in Z: fz[z['scripts_bank']].append(z['map_name_en'] or z['vanilla_const'])
A=sdis.all_files()
balls={}
for pc,(op,a,n,t) in A[141]['ins'].items():
    if op==41 and a[0]==0x8008: balls.setdefault(a[1],[]).append(pc)
def item(i):
    print('==',i,IT.get(i))
    for x in o['rec']:
        v=None
        if x['kind'] in ('item_give','item_has','item_take','item_space'): v=x['id']
        if x['kind']=='callstd' and x['id'] in (2033,2008,2007): v=x.get('v8004')
        if v==i: print('  ',x['kind'] if x['kind']!='callstd' else 'give_std',x['file'],x['pc'],fz.get(x['file']),x['entries'])
    if i in balls: print('   itemball',balls[i])
for a in sys.argv[1:]: item(int(a))
