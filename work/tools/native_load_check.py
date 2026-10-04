#!/usr/bin/env python3
"""Exercise every ROM message through native allocating loader in isolated DeSmuME.

No ROM modification or rendering. Two guarded source-preserved controls also
exercise native formatting with controlled slot data. Register redirection schedules
ordinary Thumb ABI calls on the field caller's stack. The game is stopped when
finished; the suspended caller is never resumed. Reports stay in ignored build.
"""
import argparse
import hashlib
import json
import struct
import time
import opaque_control_proof as opaque
from pathlib import Path

NEW, READ, DELETE, FREE, TRAP = 0x0200BA98,0x0200BB40,0x0200BAE4,0x02026890,0x0200BB92
# Dispatcher entry and native archive resolver guards. Changed
# binaries require independent redisassembly, never automatic guard regeneration.
GUARDS = {NEW:'f8b501250e1c181c0c21171c0093',READ:'08b5031c18880a1c002802d0012805d00ae0',DELETE:'10b5041c0fd02088002802d0012804d006e0',FREE:'10b5041c01d1fff7',TRAP:'0000',0x02007838:'10b5041cf9f7aafc10494a78002a03d00f48a100405810bd0978002904d0201c491efff7cdff10bd00280ad021f06afd21f056fe011c002903dd201cfff7c0ff10bd0348a100405810bdc046f0fc1c021ce21002'}


CODE_RANGES = [(33600944, 33601944, '8ea3bc99e0228015967ee4a59da10c679b5f7f7b13c8ceb7ce20fe06af16878e'), (33601944, 33602504, 'f3b19e2e8c113503cfba9627e8f4ff64b16b98f277973cbaaf52ddca86a81cac'), (33712228, 33714360, '21071ab173f433c5206901cf3a603b543bf26bf06649a8616f9954b6a9771a7a'), (33584528, 33585292, '4c76c35b356864d5676cdf6dc6c02c843a1c0b02cbb9921c38c613eec325e457')]

def digest(data):return hashlib.sha256(data).hexdigest()
def identity(path):return {'path':str(Path(path).resolve()),'sha256':digest(Path(path).read_bytes())}
def unit_hash(units):return digest(struct.pack('<'+'H'*len(units),*units))

def unpack_units(units):
    """Independent 15-bit-container/9-bit-symbol oracle, preserving control data."""
    if not units:raise ValueError('empty storage')
    if units[0]!=0xF100:
        out=[];i=0
        while i<len(units):
            value=units[i]
            if value==0xffff:return out
            if value==0xfffe:
                if i+3>len(units):raise ValueError('short control header')
                stop=i+3+units[i+2]
                if stop>len(units):raise ValueError('short control args')
                out.extend(units[i:stop]);i=stop
            else:out.append(value);i+=1
        raise ValueError('no terminator')
    out=[];acc=bits=0
    for word in units[1:]:
        acc|=(word&0x7fff)<<bits;bits+=15
        while bits>=9:
            value=acc&511;acc>>=9;bits-=9
            if value==511:return out
            out.append(value)
    raise ValueError('no compressed terminator')


def inventory(rom):
    import text_binary_check as binary
    banks=[]
    for archive,narc_id,path in (('a027',27,'a/0/2/7'),('battle_string',277,'battle/string/battle_string.narc')):
        container=binary.inspect_narc(bytes(rom.files[rom.filenames.idOf(path)]))
        if container['errors']:raise ValueError(container['errors'])
        for member in container['members']:
            data=member['data'];checked=binary.inspect_bank(data)
            if checked['errors']:raise ValueError(checked['errors'])
            rows=[]
            for record in checked['records']:
                index=record['id'];start=record['offset'];length=record['stored_units']
                raw=[v[0]^((596947*(index+1)+i*18749)&65535) for i,v in enumerate(struct.iter_unpack('<H',data[start:start+length*2]))]
                semantic=unpack_units(raw)
                units=semantic if raw[0]==0xf100 else raw[:raw.index(65535)]
                rows.append({'ref':f'{archive}/{member["id"]:04d}#{index}','id':index,'units':units,'expected_units':len(units),'expected_sha256':unit_hash(units),'raw_payload_sha256':unit_hash(raw),'semantic_units':len(semantic),'semantic_gap':'terminator inside control arguments' if semantic!=units else None,'compressed':raw[0]==0xf100,'stored_expected_units':raw.index(65535),'stored_expected_sha256':unit_hash(raw[:raw.index(65535)])})
            banks.append({'narc':narc_id,'bank':member['id'],'records':rows})
    return banks


def verify_result(expected,actual):
    return len(actual)==expected['expected_units'] and unit_hash(actual)==expected['expected_sha256']


def coverage(expected,observed):
    refs=[row['ref'] for row in observed]
    return len(refs)==len(set(refs)) and set(refs)==set(expected) and all(row.get('status')=='pass' for row in observed)


def run(args):
    import ndspy.rom
    import memcheck
    from desmume.emulator import DeSmuME
    from desmume.controls import Keys,keymask
    out=args.out.resolve()
    if not out.is_relative_to(Path('work/build').resolve()):raise ValueError('Output must be under work/build')
    out.mkdir(parents=True,exist_ok=True)
    source=identity(args.rom);script=identity(__file__);save=identity(args.save)
    rom=ndspy.rom.NintendoDSRom.fromFile(str(args.rom));banks=inventory(rom)
    expected=[r['ref'] for b in banks for r in b['records']]
    reference=identity(args.reference)
    original=ndspy.rom.NintendoDSRom.fromFile(str(args.reference))
    original_records={row['ref']:row for b in inventory(original) for row in b['records']}
    semantic_gaps=[]
    for bank in banks:
        for row in bank['records']:
            if row['semantic_gap']:
                row['semantic_source_matches']=row['raw_payload_sha256']==original_records[row['ref']]['raw_payload_sha256']
                if not row['semantic_source_matches']:raise ValueError('Changed opaque payload: '+row['ref'])
                semantic_gaps.append({'ref':row['ref'],'semantic_units':row['semantic_units'],'native_units':row['expected_units'],'source_matches':True,'raw_payload_sha256':row['raw_payload_sha256']})
    code=rom.loadArm9().sections[0].data
    opaque_proof=opaque.inspect_code(code)
    resolved_controls=[row for row in semantic_gaps if opaque.eligible(row['ref'], row['raw_payload_sha256'], original_records[row['ref']]['raw_payload_sha256'], opaque_proof)]
    semantic_gaps=[row for row in semantic_gaps if row not in resolved_controls]
    memcheck._check_code(args.rom)
    for first,last,sha in CODE_RANGES:
        if digest(code[first-0x02000000:last-0x02000000])!=sha:raise ValueError(f'Native code range changed {first:08X}')
    for address,signature in GUARDS.items():
        sig=bytes.fromhex(signature)
        if code[address-0x02000000:address-0x02000000+len(sig)]!=sig:raise ValueError(f'Code guard mismatch {address:08X}')
    if args.limit:
        remaining=args.limit;selected=[]
        for b in banks:
            if remaining<=0:break
            selected.append(dict(b,records=b['records'][:remaining]));remaining-=len(selected[-1]['records'])
        banks=selected
    report={'schema_version':1,'scope':'native allocating String loader and bank handles plus six guarded opaque-control formatter cases; no renderer, scene-specific buffers or other heaps','source':source,'reference':reference,'semantic_gaps':semantic_gaps,'script':script,'save':save,'expected_count':len(expected),'expected_refs':expected,'records':[],'lifecycles':[],'stress':[],'errors':[],'status':'incomplete','code_guards_passed':True,'archive_paths_observed':{}}
    report.update(resolved_controls=resolved_controls, opaque_code_proof=opaque_proof, opaque_formatter_cases=[], opaque_cleanup={})
    e=DeSmuME();e.open(source['path']);e.backup.import_file(save['path'],524288);e.reset()
    def step(n):
        for _ in range(n):e.cycle(with_joystick=False)
    def press(k):
        mask=keymask(getattr(Keys,'KEY_'+k));e.input.keypad_add_key(mask);step(6);e.input.keypad_rm_key(mask)
    step(2400);press('START');step(400);press('A');step(300);press('A');step(300)
    p=memcheck.Probe(e);p.armed=True;R=e.memory.register_arm9;u=e.memory.unsigned
    started=done=False;pending=None;heap_id=None;baseline_sp=None;calls=1;started_at=time.monotonic()
    def snapshot():
        bad=p.heap_walk()
        if bad:raise ValueError(bad)
        handles=u.read_long(memcheck.HEAP_INFO);idxs=u.read_long(memcheck.HEAP_INFO+16)
        heap=u.read_long(handles+4*u.read_byte(idxs+heap_id))
        blocks=[];cursor=u.read_long(heap+0x2c)
        while cursor:
            blocks.append([cursor,u.read_long(cursor+4)]);cursor=u.read_long(cursor+12)
        return {'heap':heap,'used_blocks':sorted(blocks),'largest_free':p._largest_free(heap)}
    def invoke(address,values):
        nonlocal calls
        calls+=1
        for i,v in enumerate(values):setattr(R,'r'+str(i),v)
        R.lr=TRAP|1;e.memory.set_next_instruction(address)
    def commands():
        for b in banks:
            before=snapshot();handle=yield NEW,[0,b['narc'],b['bank'],heap_id]
            if not handle or u.read_short(handle)!=1:raise ValueError('Not an on-demand handle')
            for row in b['records']:
                pointer=yield READ,[handle,row['id']]
                if not 0x02000000<=pointer<0x023ffff8:raise ValueError('Invalid native String pointer')
                capacity=u.read_short(pointer);length=u.read_short(pointer+2)
                if length>capacity or length>65534 or pointer+8+2*(length+1)>0x02400000:raise ValueError('Invalid String bounds')
                stored=[u.read_short(pointer+8+i*2) for i in range(length)]
                stored_hash=unit_hash(stored)
                if length!=row['stored_expected_units'] or stored_hash!=row['stored_expected_sha256']:raise ValueError('Native storage load differs: '+row['ref'])
                packed_pointer=pointer
                if row['compressed']:
                    pointer=yield 0x02026864,[row['expected_units']+1,heap_id]
                    if not 0x02000000<=pointer<0x023ffff8:raise ValueError('Invalid decompression buffer')
                    yield 0x0202703C,[pointer,packed_pointer]
                    capacity=u.read_short(pointer);length=u.read_short(pointer+2)
                    if length>capacity:raise ValueError('Native decompression exceeds capacity')
                actual=[u.read_short(pointer+8+i*2) for i in range(length)]
                terminator=u.read_short(pointer+8+length*2)
                result={k:v for k,v in row.items() if k!='units'}
                result.update(stored_actual_units=len(stored),stored_actual_sha256=stored_hash,decompression_called=row['compressed'],actual_units=length,actual_sha256=unit_hash(actual),capacity=capacity,terminator=terminator,native_call_completed=True,status='pass' if terminator==65535 and verify_result(row,actual) else 'fail')
                report['records'].append(result)
                yield FREE,[pointer]
                if row['compressed']:yield FREE,[packed_pointer]
                if result['status']!='pass':raise ValueError('Native decode differs: '+row['ref'])
            yield DELETE,[handle]
            after=snapshot();same=before==after
            report['lifecycles'].append({'narc':b['narc'],'bank':b['bank'],'before':before,'after':after,'balanced':same})
            if not same:raise ValueError('Bank lifecycle changed heap allocation state')
            if len(report['lifecycles'])%10==0:
                (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps({'banks':len(report['lifecycles']),'entries':len(report['records']),'seconds':round(time.monotonic()-started_at,1)}),flush=True)
        if resolved_controls:
            before=snapshot()
            handle=yield NEW,[0,27,763,heap_id]
            formatter=yield 0x0200BCA8,[heap_id]
            destination=yield 0x02026864,[64,heap_id]
            slot=u.read_long(u.read_long(formatter+8)+4)
            for message_id in (66,80):
                source_string=yield READ,[handle,message_id]
                raw=[u.read_short(source_string+8+2*i) for i in range(6)]
                if raw != list(opaque.PAYLOAD):raise ValueError('Opaque full copied payload differs')
                for count in (0,7,31):
                    # Controlled fixture data in a real native-allocated slot;
                    # no production save, ROM or executable code is changed.
                    e.memory.write_short(slot+2,count)
                    for i in range(count):e.memory.write_short(slot+8+2*i,0x012b)
                    e.memory.write_short(slot+8+2*count,65535)
                    yield 0x0200C738,[formatter,destination,source_string]
                    length=u.read_short(destination+2)
                    if length>63:raise ValueError('Opaque formatter output out of bounds')
                    actual=[u.read_short(destination+8+2*i) for i in range(length)]
                    report['opaque_formatter_cases'].append(dict(ref=f'a027/0763#{message_id}',slot_units=count,source_string_length=u.read_short(source_string+2),source_capacity=u.read_short(source_string),full_copied_payload=raw,actual_units=actual,terminator=u.read_short(destination+8+2*length),native_call_completed=True))
                    snapshot()
                yield FREE,[source_string]
            yield FREE,[destination]
            yield 0x0200BD40,[formatter]
            yield DELETE,[handle]
            report['opaque_cleanup']=dict(before=before,after=snapshot())
            if not opaque.native_evidence_ok(report['opaque_formatter_cases'],report['opaque_cleanup']):raise ValueError('Opaque formatter evidence failed')
        # Hold four bank handles concurrently, alternate archive/bank reads, and
        # release in reverse order. 20 cycles gives200+ allocations per group.
        available=[b for b in banks if b['records']]
        choices=[]
        for pool in (available,[b for b in available if b['narc']==277],[b for b in available if any(r['compressed'] for r in b['records'])],list(reversed(available))):
            if pool:
                choice=max(pool,key=lambda b:max(r['expected_units'] for r in b['records']))
                if choice not in choices:choices.append(choice)
        for b in sorted(available,key=lambda b:max(r['expected_units'] for r in b['records']),reverse=True):
            if len(choices)>=4:break
            if b not in choices:choices.append(b)
        for round_id in range(args.stress_rounds):
            before=snapshot();opened=[]
            for b in choices:
                handle=yield NEW,[round_id%2,b['narc'],b['bank'],heap_id]
                if not handle or u.read_short(handle)!=1:raise ValueError('Stress handle not lazy')
                opened.append((b,handle))
            reads=0
            for _ in range(3):
                for b,handle in opened:
                    row=max(b['records'],key=lambda r:r['expected_units']);pointer=yield READ,[handle,row['id']]
                    if not 0x02000000<=pointer<0x023ffff8:raise ValueError('Stress invalid String pointer')
                    length=u.read_short(pointer+2)
                    if length!=row['stored_expected_units']:raise ValueError('Stress length differs')
                    actual=[u.read_short(pointer+8+i*2) for i in range(length)]
                    if unit_hash(actual)!=row['stored_expected_sha256']:raise ValueError('Stress storage differs')
                    yield FREE,[pointer];reads+=1
            for b,handle in reversed(opened):yield DELETE,[handle]
            after=snapshot();report['stress'].append({'round':round_id,'handles':len(opened),'bank_refs':[[b['narc'],b['bank']] for b,h in opened],'reads':reads,'before':before,'after':after,'balanced':before==after})
            if before!=after:raise ValueError('Stress lifecycle changed heap state')
    generator=None
    def advance(value=None):
        nonlocal pending,done
        try:
            if R.sp!=baseline_sp:raise ValueError('Native call did not restore caller stack')
            pending=generator.send(value);invoke(*pending)
        except StopIteration:done=True;e.pause()
        except Exception as error:report['errors'].append(str(error));done=True;e.pause()
    def begin(address,size):
        nonlocal started,heap_id,baseline_sp,generator
        if started:return
        started=True;heap_id=R.r3;baseline_sp=R.sp
        # First constructor is about to execute: reuse this safe caller boundary,
        # request our first bank and route its normal ABI return to the trap.
        generator=commands()
        try:
            addr,values=next(generator)
            for i,v in enumerate(values):setattr(R,'r'+str(i),v)
            R.lr=TRAP|1
        except Exception as error:report['errors'].append(str(error));e.pause()
    def trap(address,size):advance(R.r0)
    def resolved(address,size):
        if R.r4 not in (27,277):return
        path=bytes(u.read_byte(R.r0+i) for i in range(64)).split(b'\0')[0].decode('ascii')
        wanted={27:'a/0/2/7',277:'battle/string/battle_string.narc'}[R.r4]
        report['archive_paths_observed'][str(R.r4)]=path
        if path!=wanted:report['errors'].append('Native archive path differs: '+path)
    e.memory.register_exec(0x02007880,resolved)
    e.memory.register_exec(0x0200784E,resolved)
    e.memory.register_exec(NEW,begin);e.memory.register_exec(TRAP,trap)
    press('X')
    for frame in range(args.max_frames):
        if done:break
        e.cycle(with_joystick=False);p.frame=frame
    if not done:report['errors'].append('Native sweep timed out or never reached caller')
    report.update(minimum_spare_by_heap=p.minspare,native_calls=calls,heap_id=heap_id,heap_checks=p.heap_checks,allocation_failures=p.fails,null_writes=p.nullw,heap_table_errors=p.heap_table_errors,seconds=round(time.monotonic()-started_at,2),source_unchanged=identity(args.rom)==source,script_unchanged=identity(__file__)==script,save_unchanged=identity(args.save)==save,reference_unchanged=identity(args.reference)==reference)
    report['coverage_complete']=coverage(expected,report['records'])
    report['status']='pass' if done and report['coverage_complete'] and not any((report['errors'],p.fails,p.nullw,p.heap_table_errors)) and report['source_unchanged'] and report['script_unchanged'] and report['save_unchanged'] and report['reference_unchanged'] and len(report['stress'])==args.stress_rounds and args.stress_rounds>0 and report['archive_paths_observed']=={'27':'a/0/2/7','277':'battle/string/battle_string.narc'} else 'incomplete' if args.limit and not report['errors'] else 'fail'
    if report['status']=='pass' and semantic_gaps:report['status']='passed_with_semantic_gaps'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');e.destroy()
    print(json.dumps({k:report[k] for k in ('status','seconds','native_calls','coverage_complete','errors')}),flush=True)
    return 0 if report['status'] in ('pass','passed_with_semantic_gaps') else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True);p.add_argument('--reference',type=Path,default=Path('work/rom/origin_v4.0.3_cn.nds'));p.add_argument('--save',type=Path,default=Path('work/build/memcheck/trainer.sav'));p.add_argument('--out',type=Path,required=True);p.add_argument('--limit',type=int,default=0);p.add_argument('--stress-rounds',type=int,default=20);p.add_argument('--max-frames',type=int,default=100000)
    return run(p.parse_args())
if __name__=='__main__':raise SystemExit(main())
