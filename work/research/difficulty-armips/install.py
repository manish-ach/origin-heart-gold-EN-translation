"""Guarded installer used by build.py; intentionally absent from production tools.

No instruction encoding here: armips owns every patch byte. ndspy only stages
logical sections and appends the resident autoload. No raw ROM writes in place.
"""
from pathlib import Path
import json
import os
import struct
import sys
import ndspy.rom
import ndspy.code
import ndspy.fnt
from publication import publish_pair, recover_publication
from publication import PublicationRecoveryRequired as PublicationRecoveryRequired
from build import (ROOT, SOURCE, OUTPUT, BASE, LIMIT, LLD, require, sha, pin, build,
                   DEV_LABEL, dev_tools, tool_mode, tool_env)

BASES = {'arm9.bin': 0x02000000, 'itcm.bin': 0x01FF8000,
         'overlay9.bin': 0x021E4DA0, 'overlay14.bin': 0x022007E0, 'overlay50.bin': 0x021E4980}
# Standard build of main after rc8 (trainer full names, D-2487). Every difference from
# the rc8 baseline (SHA-256 f23e2263...) is attributed in
# work/notes/main_difficulty_compatibility_20261013.md; the rc8 and rc7 reviews are
# work/notes/rc8_difficulty_compatibility_20261013.md and rc7_difficulty_compatibility_20261010.md.
# One accepted input per version: rebuild rc8 from its tag, whose pin is f23e2263.
INPUT_SHA = '96793c3981717374cebb71c361114165a18d91e646f99263bb6522866ded3c3c'
OV_PINS = {9: (39040, 'f66e9ff1ec5525797654017d246c4d61f2ae70382d25e83df0e1680dbb890b0d'),
           14: (337216, '7c98bd2050bc3ffc71ebe3a31be6dd9680d2bf090c2b2206ee7b36bbfe5c93c1')}
ITEM_RANGES = [(0x02202954,0x0220297E,'c0e1c2238dc930beb13445bd0e936066f3cd47b1b681472b6efa1255b5fd3304'),
               (0x02202AC2,0x02202ADC,'63d4cdb09516692fd75aa819fe3e632d9822e0698bd662377cbdffa7809c872c'),
               (0x02202BE0,0x02202BF4,'36db224ad0f945fe9d0ba83cf7ad5efb74e054c04a25b50612fe0b9bd39de2fc')]


def contracts():
    comp = json.loads((SOURCE/'compatibility.json').read_text())
    opts = json.loads((SOURCE/'native/options_hooks.json').read_text())
    rt = json.loads((SOURCE/'native/runtime_hooks.json').read_text())
    items = json.loads((SOURCE/'native/items_hooks.json').read_text())
    hooks = opts['hooks'] + rt['hooks'] + [dict(i, size=4, before=i['expect'], stub=i['target']) for i in items]
    edits = comp['edits'] + rt['edits']
    require([int(x,16) for x in rt['reservation']] == [BASE,LIMIT], 'reservation contract drift')
    return comp, hooks, edits


def sections(rom):
    arm = rom.loadArm9()
    overlays = rom.loadArm9Overlays()
    require(len(arm.sections) == 3, 'input has unexpected autoloads / already installed')
    require([s.ramAddress for s in arm.sections] == [0x02000000,0x01FF8000,0x027E0000], 'autoload layout')
    result = {'arm9.bin': bytes(arm.sections[0].data), 'itcm.bin': bytes(arm.sections[1].data)}
    for i in (9,14,50):
        o = overlays[i]
        require(o.ramAddress == BASES[f'overlay{i}.bin'] and not o.compressed, 'overlay layout/compression')
        require(bytes(rom.files[o.fileID]) == bytes(o.data), 'overlay logical file mismatch')
        result[f'overlay{i}.bin'] = bytes(o.data)
    return arm, overlays, result


def bounds(arm, overlays):
    require(arm.codeSettingsOffs == 0xBA0, 'code settings address')
    main = arm.sections[0].data
    bss_start, bss_end, compressed = struct.unpack_from('<3I',main,arm.codeSettingsOffs+12)
    require((bss_start,bss_end,compressed) == (0x021106A0,0x021E4980,0), 'original main/BSS/compression bounds')
    require(len(main)+0x02000000 == bss_start, 'main must not extend into BSS')
    low = struct.unpack_from('<I',main,0xD1A1C)[0]
    high = struct.unpack_from('<I',main,0xD1970)[0]
    require((low,high) == (0x02264920,0x023E0000), 'original arena bounds / double install')
    # TEXT SPEED ends at 0x01FF8FC0; trainer display (work/tools/trainer_display.py) follows to 0x01FF9140.
    require(struct.unpack_from('<I',main,0xD1A28)[0] == 0x01FF9140, 'ITCM arena extent')
    max_overlay = max(o.ramAddress+o.ramSize+o.bssSize for o in overlays.values())
    require(bss_end <= max_overlay <= low < BASE < LIMIT == 0x023E0000, 'overlay/arena/resident overlap')
    require([(len(s.data),s.bssSize) for s in arm.sections] == [(1115808,0),(4416,0),(96,32)], 'autoload sizes')
    for s in arm.sections:
        require(s.ramAddress+len(s.data)+s.bssSize <= BASE or s.ramAddress >= 0x027E0000, 'autoload collision')
    return {'original_arena_low':low,'original_arena_high':high,'arena_high':BASE,
            'max_overlay_end_including_bss':max_overlay,'main_bss':[bss_start,bss_end],
            'arm7_excluded_span':[LIMIT,0x023F9EF0], 'arena_bytes_reserved':LIMIT-BASE}


def validate_item_binding(raw):
    """Independent native creator/save-clone/consumer contract for items.c."""
    pins = json.loads((SOURCE/'research/items-binding-pins.json').read_text())
    checked = []
    for row in pins['ranges']:
        data = raw[row['file']]
        lo = int(row['start'], 16) - BASES[row['file']]
        hi = int(row['end'], 16) - BASES[row['file']]
        require(0 <= lo < hi <= len(data) and sha(data[lo:hi]) == row['sha256'],
                f'item ownership dependency: {row["label"]}')
        checked.append(dict(row))
    return checked


def validate_item_revival(raw, source='en'):
    """Pin the synchronous effect-loop ABI and both native callback ancestries."""
    pins = json.loads((SOURCE/'research/items-revival-pins.json').read_text())
    require(source in ('cn', 'en'), 'unknown item revival source')
    for row in pins['ranges']:
        data = raw[row['file']]
        lo = int(row['start'], 16) - BASES[row['file']]
        hi = int(row['end'], 16) - BASES[row['file']]
        expected = row.get('historical_sha256', row['sha256']) if source == 'cn' else row['sha256']
        require(0 <= lo < hi <= len(data) and sha(data[lo:hi]) == expected,
                f'item revival dependency: {row["label"]}')
    return pins['ranges']


def validate_sections(raw, comp, hooks, edits):
    checked = []
    for name, p in comp['full_input_guards']['en'].items():
        data = raw[name+'.bin']
        require(len(data)==p['size'] and sha(data)==p['sha256'], f'EN whole-file guard: {name}')
        checked.append({'file':name+'.bin',**p})
    for i, (size,digest) in OV_PINS.items():
        require(len(raw[f'overlay{i}.bin'])==size and sha(raw[f'overlay{i}.bin'])==digest, f'whole overlay{i} guard')
        checked.append({'file':f'overlay{i}.bin','size':size,'sha256':digest})
    for d in comp['dependencies']:
        data = raw[d['file']]
        lo,hi = int(d['start'],16)-BASES[d['file']],int(d['end'],16)-BASES[d['file']]
        require(0 <= lo < hi <= len(data) and sha(data[lo:hi])==d['sha256']['en'], f'dependency guard: {d["purpose"]}')
    for lo,hi,digest in ITEM_RANGES:
        require(sha(raw['overlay14.bin'][lo-BASES['overlay14.bin']:hi-BASES['overlay14.bin']])==digest, 'item frame/control-flow dependency')
    checked.extend(validate_item_binding(raw))
    checked.extend(validate_item_revival(raw))
    seen = {f:set() for f in raw}
    for h in hooks+edits:
        f=h['file']; off=int(h['address'],16)-BASES[f]; expected=bytes.fromhex(h['before'])
        require(len(expected)==h['size'] and 0<=off<=len(raw[f])-len(expected), 'invalid declaration bounds')
        require(raw[f][off:off+len(expected)]==expected, f'hook/edit guard {f}:{h["address"]}')
        window=set(range(off,off+len(expected)))
        require(not seen[f]&window,'overlapping hook/edit declarations')
        seen[f].update(window)
    return checked


def tool_version(name,path):
    import subprocess
    argv=[str(path)] if name=='armips' else [str(path),'--version']
    result=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,env=tool_env(str(path)))
    lines=(result.stdout+result.stderr).strip().splitlines()
    require(lines,f'tool {name} printed no version line: {path}')
    return lines[0]


def check_tools(pinned):
    """Release: each tool must equal its pin. Development (DIFFICULTY_DEV_TOOLS=1):
    record the local tool and how it differs from the release pin instead."""
    result={}
    for name,p in pinned.items():
        # Tool paths are stored as $HOME/... so the pins work on any machine.
        path=Path(os.path.expandvars(p['path']))
        if not dev_tools():
            require(sha(path.read_bytes())==p['sha256'],f'tool guard {name}')
            result[name]=dict(pin(path),version=p['version'])
            continue
        local=pin(path)
        result[name]=dict(local,version=tool_version(name,path),release_sha256=p['sha256'],
                          release_version=p['version'],matches_release_pin=local['sha256']==p['sha256'])
    return result


def source_tools():
    old=json.loads((SOURCE/'research/options-source-pins.json').read_text())
    overrides=json.loads((SOURCE/'native/integration_contract.json').read_text())['source_overrides']
    checked={}
    for group in ('owned_sources','read_only_dependencies_and_protected_sources'):
        for name,p in old[group].items():
            # Handoff prose is documentary, not compiled code; progression's
            # obsolete binding paragraph is explicitly updated by this task.
            if name.endswith('.md'):
                if name.endswith('/README.md'):
                    require(sha((ROOT/name).read_bytes())==p['sha256'], f'protected provenance {name}')
                continue
            expected=overrides.get(name,{}).get('sha256',p['sha256'])
            require(sha((ROOT/name).read_bytes())==expected,f'source guard {name}')
            checked[name]=pin(ROOT/name)
    toolpins=check_tools(old['tools'])
    sources={str(p.relative_to(ROOT)):pin(p) for p in sorted(SOURCE.rglob('*'))
             if p.is_file() and p.suffix in ('.py','.c','.h','.asm','.ld','.json','.toml','.md')}
    # Capture the real Xcode compiler and Rust linker behind the small drivers.
    import subprocess
    realclang=subprocess.check_output(['/usr/bin/xcrun','--find','clang'],cwd=ROOT,text=True).strip()
    rustlld=Path(LLD).parent.parent/'rust-lld'
    toolpins['clang_real']=pin(realclang)
    require(rustlld.is_file(),'underlying rust-lld missing')
    toolpins['rust_lld_real']=pin(rustlld)
    libllvm=Path(LLD).parents[4]/'libLLVM.dylib'
    if dev_tools() and libllvm.is_file():
        toolpins['rust_libllvm']=pin(libllvm)
    toolpins['python']=dict(pin(sys.executable),version=sys.version)
    for module in (ndspy.rom,ndspy.code,ndspy.fnt):
        toolpins[module.__name__]=pin(module.__file__)
    return sources,toolpins


def changes(before, after, base=0):
    require(len(before)==len(after),'logical payload extent changed')
    result=[]; i=0
    while i<len(before):
        if before[i]==after[i]:
            i+=1; continue
        start=i
        while i<len(before) and before[i]!=after[i]: i+=1
        result.append({'offset':start,'address':base+start,'before':before[start:i].hex(),'after':after[start:i].hex()})
    return result


def verify_stage(raw, staged, hooks, edits, report, comp):
    allowed={f:set() for f in raw}
    for h in hooks+edits:
        f=h['file']; off=int(h['address'],16)-BASES[f]
        allowed[f].update(range(off,off+h['size']))
    diff={}
    for f,before in raw.items():
        after=staged[f]
        require(len(before)==len(after),f'stage extent {f}')
        require(all(i in allowed[f] for i,(a,b) in enumerate(zip(before,after)) if a!=b),f'undeclared ASM write {f}')
        diff[f]=changes(before,after,BASES[f])
    for h in hooks:
        address=int(h['address'],16); off=address-BASES[h['file']]
        data=staged[h['file']][off:off+4]
        target=report['asm_symbols'][h['stub'].lower()]
        require(BASE<=target<LIMIT and target%4==0,f'stub target range/state {h["stub"]}')
        if h['kind']=='thumb_pointer':
            require(struct.unpack('<I',data)[0]==target+1,'Thumb pointer target')
        else:
            a,b=struct.unpack('<HH',data)
            require(a&0xF800==0xF000 and b&0xF800==0xF800,'not Thumb BL')
            delta=((a&0x7FF)<<12)|((b&0x7FF)<<1)
            if delta&0x400000: delta-=0x800000
            require(address+4+delta==target and -0x400000<=target-address-4<0x400000,'BL target/reach')
    for e in edits:
        off=int(e['address'],16)-BASES[e['file']]
        require(staged[e['file']][off:off+e['size']].hex()==e['after'],'compat/arena emitted value')
    return diff


def verify_rom(original, result, raw, staged, payload, report):
    a=original.loadArm9(); b=result.loadArm9()
    require(b.codeSettingsOffs==a.codeSettingsOffs and len(b.sections)==4,'reopened autoload layout')
    require(len(b.sections[0].data)==len(a.sections[0].data),'main extension')
    cso=a.codeSettingsOffs
    expected_main=bytearray(staged['arm9.bin'])
    # Exactly the three native loader bookkeeping words may differ on serialize.
    expected_main[cso:cso+12]=b.sections[0].data[cso:cso+12]
    require(bytes(b.sections[0].data)==expected_main,'reopened main delta')
    table_start,table_end,data_start=struct.unpack_from('<3I',b.sections[0].data,cso)
    require(data_start==0x021106A0 and table_end-table_start==36,'autoload bookkeeping')
    require(table_start==data_start+sum(len(s.data) for s in b.sections[1:]),'autoload data/table boundary')
    for i in (0,1,2):
        require((a.sections[i].ramAddress,a.sections[i].bssSize,a.sections[i].implicit)==
                (b.sections[i].ramAddress,b.sections[i].bssSize,b.sections[i].implicit),'original section metadata')
    require(bytes(b.sections[1].data)==staged['itcm.bin'],'ITCM exact delta')
    require(bytes(b.sections[2].data)==bytes(a.sections[2].data),'DTCM changed')
    s=b.sections[3]
    require(s.ramAddress==BASE and bytes(s.data)==payload and s.bssSize==0 and not s.implicit,'resident autoload mismatch')
    for start,end in report['zero_ranges']:
        require(not any(s.data[start-BASE:end-BASE]),'autoload interior BSS nonzero')
    # Compare every native logical field, including ARM7, both overlay tables,
    # banner/debug/postdata/logo; only ARM9 and the declared files may differ.
    for k,v in vars(original).items():
        if k in ('arm9','files','filenames','sortedFileIds','pad200'): continue
        require(getattr(result,k)==v,f'ROM field changed: {k}')
    # ndspy relocates its NSMBe RSA-signature container pointer at ROM+1000.
    # This is a container offset, never executable/game payload. All other
    # header padding and the RSA bytes themselves must remain identical.
    padding=bytearray(original.pad200)
    padding[0xE00:0xE04]=result.pad200[0xE00:0xE04]
    require(bytes(padding)==result.pad200,'undeclared post-header padding delta')
    require(ndspy.fnt.save(original.filenames)==ndspy.fnt.save(result.filenames),'filename table changed')
    require(len(original.files)==len(result.files),'file count changed')
    changed_files={original.loadArm9Overlays()[i].fileID:f'overlay{i}.bin' for i in (9,14,50)}
    for i,(before,after) in enumerate(zip(original.files,result.files)):
        expected=staged[changed_files[i]] if i in changed_files else before
        require(bytes(after)==bytes(expected),f'undeclared ROM file delta {i}')
    # Full table equality above means all overlay entrypoints/sizes/BSS and ARM7
    # tables are preserved. Item archive is among the byte-identical files.
    return {'verified_files':len(result.files), 'changed_file_ids':sorted(changed_files),
            'arm7_sha256':sha(result.arm7),'arm9_overlay_table_sha256':sha(result.arm9OverlayTable),
            'arm7_overlay_table_sha256':sha(result.arm7OverlayTable),
            'main_exact_diff':changes(raw['arm9.bin'],bytes(b.sections[0].data),0x02000000),
            'autoload_bookkeeping':[table_start,table_end,data_start],
            'container_RSA_pointer_diff':changes(original.pad200,result.pad200,0x200),
            'all_other_logical_payloads_unchanged':True}


def negative_checks(raw,comp,hooks,edits,arm,overlays,result):
    count=0
    for h in hooks+edits:
        bad=dict(raw); f=h['file']; data=bytearray(raw[f]); data[int(h['address'],16)-BASES[f]]^=1;bad[f]=bytes(data)
        try: validate_sections(bad,comp,hooks,edits)
        except ValueError: count+=1
        else: raise ValueError('negative hook mutation accepted')
    # Outside-site corruption must fail too, not just four-byte signatures.
    for f in raw:
        bad=dict(raw); data=bytearray(raw[f]); data[-1]^=1; bad[f]=bytes(data)
        try: validate_sections(bad,comp,hooks,edits)
        except ValueError: count+=1
        else: raise ValueError('whole file corruption accepted')
    try: sections(result)
    except ValueError: count+=1
    else: raise ValueError('double install accepted')
    old=overlays[14].bssSize
    overlays[14].bssSize=LIMIT
    try:
        try: bounds(arm,overlays)
        except ValueError: count+=1
        else: raise ValueError('bad overlay bounds accepted')
    finally: overlays[14].bssSize=old
    return {'rejections':count,'coverage':'every hook/edit, each full-file outside-site byte, double install, overlay overlap'}


def execute(input_path, stage):
    recover_publication(OUTPUT)
    require(not input_path.is_relative_to(OUTPUT),'candidate cannot be its own input')
    input_data=input_path.read_bytes()
    require(sha(input_data)==INPUT_SHA,'completed-English full ROM guard (WIP/partial/double installation rejected)')
    sources,tools=source_tools()
    comp,hooks,edits=contracts()
    original=ndspy.rom.NintendoDSRom(input_data)
    arm,overlays,raw=sections(original)
    layout=bounds(arm,overlays)
    guards=validate_sections(raw,comp,hooks,edits)
    for f,b in raw.items(): (stage/f).write_bytes(b)
    payload,report=build(stage)
    staged={f:(stage/f).read_bytes() for f in raw}
    diff=verify_stage(raw,staged,hooks,edits,report,comp)
    # Validate all literal C targets in emitted thunks. Item adapters use ARM
    # LDR literals; armips symbols provide exact pool targets via disassembly.
    from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
    c=Cs(CS_ARCH_ARM,CS_MODE_ARM); c.detail=True
    for span in report['stub_spans']:
        blob=(stage/span['file']).read_bytes()
        if span['file']=='options-stubs.bin':
            opts=json.loads((SOURCE/'native/options_hooks.json').read_text())['hooks']
            for i,h in enumerate(opts):
                require(blob[8*i:8*i+4]==bytes.fromhex('004b1847') and
                        struct.unpack_from('<I',blob,8*i+4)[0]==report['elf_labels'][h['target']], 'Options C veneer target')
        else:
            # Every external C address referenced by this ASM must appear as
            # an actual LDR r12 literal followed by BLX r12, not just pool data.
            expected=([report['elf_labels'][n] for n in ('dg_bag_item_attr','dg_bag_remembered','dg_bag_accept','dg_bag_commit_item','dg_bag_commit_target','dg_bag_effect_attr')]
                      if span['file']=='item_stubs.bin' else
                      [report['elf_labels'][n] for n in ('dg_battle_begin','dg_battle_root_free','dg_growth_share_enabled','dg_growth_eligible')])
            found=[]
            for off in range(0,len(blob)-8,4):
                ins=list(c.disasm(blob[off:off+8],span['start']+off))
                if len(ins)==2 and ins[0].mnemonic=='ldr' and ins[0].op_str.startswith('ip, [pc,') and ins[1].mnemonic=='blx' and ins[1].op_str=='ip':
                    literal=ins[0].address+8+ins[0].operands[1].mem.disp-span['start']
                    require(0<=literal<=len(blob)-4,'veneer literal outside stub')
                    found.append(struct.unpack_from('<I',blob,literal)[0])
            require(found==expected,f'actual C veneer targets: {span["file"]}')
    # Only declared logical edits and one autoload insertion.
    output=ndspy.rom.NintendoDSRom(input_data)
    target=output.loadArm9()
    target.sections[0].data=bytearray(staged['arm9.bin'])
    target.sections[1].data=bytearray(staged['itcm.bin'])
    target.sections.append(ndspy.code.MainCodeFile.Section(payload,BASE,0))
    output.arm9=target.save(compress=False)
    for i in (9,14,50): output.files[overlays[i].fileID]=staged[f'overlay{i}.bin']
    temp=stage/'candidate.pending.nds'
    output.saveToFile(temp)
    reopened=ndspy.rom.NintendoDSRom.fromFile(temp)
    packed=temp.read_bytes()
    rsa_offset=struct.unpack_from('<I',packed,0x1000)[0]
    require(packed[rsa_offset:rsa_offset+len(original.rsaSignature)]==original.rsaSignature and
            rsa_offset+len(original.rsaSignature)==len(packed),'container RSA pointer')
    verification=verify_rom(original,reopened,raw,staged,payload,report)
    negatives=negative_checks(raw,comp,hooks,edits,arm,overlays,reopened)
    # Reject sources/tools/input changing underneath compilation/verification.
    require(sha(input_path.read_bytes())==INPUT_SHA,'input changed while building')
    for p in list(sources.values())+list(tools.values()):
        require(pin(p['path'])['sha256']==p['sha256'],f'build input changed: {p["path"]}')
    status='built, installed, reopened and logically verified; native acceptance pending'
    receipt={'format':1,'status':DEV_LABEL+'; '+status if dev_tools() else status,'tool_mode':tool_mode(),
             'input':pin(input_path),'output':dict(pin(temp),path=str(OUTPUT/'candidate.nds')),
             'input_selection':'pinned main standard build after rc8; work/notes/main_difficulty_compatibility_20261013.md',
             'sources':sources,'tools':tools,'layout':layout,'build':report,'guards':guards,
             'dependency_guards':comp['dependencies'],
             'item_frame_guards':[{'start':a,'end':b,'sha256':h} for a,b,h in ITEM_RANGES],
             'build_artifacts':{p.name:pin(p) for p in sorted(stage.iterdir()) if p.is_file() and p != temp},
             'hook_declarations':hooks,'compatibility_and_arena_edits':edits,'stage_exact_diff':diff,
             'verification':verification,'negative_checks':negatives,
             'candy':'deferred D-2304; native unchanged','day_care':'skipped D-2304; native unchanged',
             'artifacts':str(stage),'native_gameplay_acceptance':False}
    (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    publish_pair(temp, stage/'receipt.json', OUTPUT)
    return {'candidate':str(OUTPUT/'candidate.nds'),'sha256':receipt['output']['sha256'],
                      'status':receipt['status'],'tool_mode':receipt['tool_mode'],
                      'resident_bytes':len(payload),'reservation_bytes':LIMIT-BASE,
                      'negative_rejections':negatives['rejections'],'artifacts':str(stage)}
