"""Read-only native screenshot/save oracles. No host-generated game outcomes."""
import binascii
from pathlib import Path
import struct
from PIL import Image
from support import OPTIONS_ROWS


def validate_page_navigation(run):
    """Both retained native row drafts and difficulty drafts share Confirm/Back."""
    points=run['points']
    names=['normal-entry','normal-draft','difficulty-entry','difficulty-draft',
           'normal-retained','confirmed','cancel-drafts','cancelled','restored']
    assert [p['name'] for p in points]==names,'page navigation sequence incomplete'
    assert all(a['frame']<b['frame'] for a,b in zip(points,points[1:]))
    p=dict(zip(names,points));before=p['normal-entry']['word']
    owner=p['normal-entry']['options_owner'];state=p['normal-entry']['state']
    assert 0x02000000<=owner<0x02400000 and 0x02000000<=state<0x02400000
    for name in names:
        row=p[name]
        assert row['options_owner']==owner,'page navigation replaced Options owner'
        if name in ('confirmed','cancelled','restored'):
            assert row['field'] and row['state']==0 and row['nav_live']==0,'footer/owner survived native exit'
        else:
            assert row['state'] and row['nav_live']==1
            assert len(row['counts'])==7 and all(1<=n<=32 for n in row['counts'])
            nav=bytes.fromhex(row['nav'])
            assert len(nav)==16 and nav[4:10]==bytes([1,1,21,12,3,13])
            assert int.from_bytes(nav[10:12],'little')&0x7fff==634
            assert 0x02000000<=int.from_bytes(nav[12:16],'little')<0x02400000
    for name in names[:5]:assert p[name]['state']==state
    assert [p[n]['mode'] for n in names[:5]]==[0,0,1,1,0]
    draft=p['normal-draft']['choices'];initial=p['normal-entry']['choices']
    assert draft[0]==(initial[0]+1)%p['normal-entry']['counts'][0] and draft[0]!=initial[0]
    assert draft[1:]==initial[1:]
    assert all(p[n]['choices']==draft for n in names[2:5]),'page flip lost a native draft'
    assert all(p[n]['word']==before for n in names[:5]),'page change wrote saved settings'
    expected=((before&~3)|draft[0])^0x20
    assert p['confirmed']['word']==expected,'Confirm failed to merge both drafts'
    assert p['cancel-drafts']['mode']==0 and p['cancel-drafts']['word']==expected
    assert p['cancel-drafts']['choices'][0]!=draft[0],'Cancel lacks a changed normal draft'
    assert p['cancelled']['word']==expected,'Back committed a draft'
    assert p['restored']['word']==before,'native controls did not restore settings'
    inputs=run['inputs']
    assert {'L','R','RIGHT'}<={i.get('key') for i in inputs}
    assert {89,18}<={i['touch'][0] for i in inputs if i.get('touch',[0,0])[1]==180}
    assert not any('write' in i or 'address' in i for i in inputs),'navigation used direct outcome writes'


def focus_regions(path, focus):
    """Track the original red outline separately from the font dash/focus.

    Regions are screen coordinates measured from the existing Options geometry;
    a moving font dash cannot excuse a stationary first-row highlight.
    Manual review still owns readability and intended emphasis.
    """
    im=Image.open(path).convert('RGB')
    assert im.size==(256,384), im.size
    red=lambda p:p[0]>190 and p[1]<100 and p[2]<110
    regions={}
    for row in range(OPTIONS_ROWS):
        y=192+24+20*row
        pixels=[im.getpixel((x,yy)) for yy in range(y,y+18) for x in range(0,5)]
        regions['row'+str(row)+'_left_red']=sum(map(red,pixels))
    return {'focus':focus,'path':str(path),'regions':regions}


def inspect_battery(path, options_offset):
    """Independent literal Origin layout, checked against save-core's selector.

    Each slot is reported even when it is intentionally an older generation.
    No checksum, counter, field or selection result is rewritten.
    """
    import save_core
    data=Path(path).read_bytes()
    assert len(data)==0x80000,len(data)
    selected=save_core.request('inspectSave',data)
    slots=[]
    for base in (0,0x40000):
        blocks=[]
        for offset,size,ident in ((0,0xf7cc,0),(0xf800,0x18408,1)):
            start=base+offset;footer=start+size-16
            counter,length,magic,blockid,stored=struct.unpack_from('<IIIHH',data,footer)
            crc=binascii.crc_hqx(data[start:footer],0xffff)
            blocks.append({'id':ident,'counter':counter,'size':length,'magic':magic,
                           'stored_crc':stored,'actual_crc':crc,
                           'valid':length==size and magic==0x20060623 and blockid==ident and stored==crc})
        slots.append({'base':base,'options':struct.unpack_from('<H',data,base+options_offset)[0],
                      'blocks':blocks,'coherent':all(b['valid'] for b in blocks) and blocks[0]['counter']==blocks[1]['counter']})
    active=next(s for s in slots if s['base']==selected['base'])
    assert active['coherent'],'shared selector chose invalid block pair'
    return {'selected_base':selected['base'],'counter':selected['counter'],'slots':slots,
            'options':active['options'],'options_offset':options_offset,
            'layout_source':'work/save-core/src/layout.ts; native Origin general/storage paired generation'}
