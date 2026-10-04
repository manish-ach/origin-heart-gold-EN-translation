import sys,re
# usage: win.py file:pc[:before[:after]] ...
for spec in sys.argv[1:]:
    p=spec.split(':'); f=int(p[0]); pc=int(p[1]); b=int(p[2]) if len(p)>2 else 6; a=int(p[3]) if len(p)>3 else 10
    L=open('dump/%04d.txt'%f).read().split('\n')
    print('########',f,pc,L[0])
    for i,l in enumerate(L):
        m=re.match(r'\s+(\d+) ',l)
        if m and int(m.group(1))==pc:
            print('\n'.join(x[:180] for x in L[max(0,i-b):i+a+1])); break
