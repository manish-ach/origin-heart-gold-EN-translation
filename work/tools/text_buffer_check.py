#!/usr/bin/env python3
"""Read-only check of item descriptions against all confirmed direct consumer String capacities."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import memcheck
import msgtool

SITE = 0x021FD8CE
OVERLAY = 17
BANK = 218
STRING_NEW = 0x02026864
COPY_GUARD = 0x02026ED4


CONSUMERS = (
    {"overlay": 3, "site": 0x02259B34, "call_offset": 4, "suffix": "200b21",
     "description_call": 0x02259B42, "context": "shop (runtime heap 11)", "shift": 0},
    {"overlay": 9, "site": 0x021EC12A, "call_offset": 4, "suffix": "202034",
     "description_call": 0x021EC14C, "context": "unknown screen; dynamic heap", "shift": 0},
    {"overlay": 17, "site": SITE, "call_offset": 4, "suffix": "200621",
     "description_call": 0x021FD8DC, "context": "bag (heap 6)", "shift": 0},
    {"overlay": 16, "site": 0x021E4E26, "call_offset": 6, "suffix": "2080020a21",
     "description_call": 0x021F49FE, "context": "PC; reused shared buffer (heap 10)", "shift": 10},
)


def consumer_capacity(data, base, consumer):
    offset = consumer["site"] - base
    call_offset = consumer["call_offset"]
    prefix = data[offset:offset + call_offset]
    if (len(prefix) != call_offset or prefix[1:] != bytes.fromhex(consumer["suffix"])
            or memcheck._bl_target(data, offset + call_offset, base) != STRING_NEW):
        raise ValueError(f"Unsupported overlay {consumer['overlay']} allocation code")
    capacity = prefix[0] << consumer["shift"]
    if capacity <= 0:
        raise ValueError("Invalid zero String capacity")
    # Validate the separately identified consumer still calls GetItemDescription.
    target_offset = consumer["description_call"] - base
    if memcheck._bl_target(data, target_offset, base) != 0x020763EC:
        raise ValueError(f"Unsupported overlay {consumer['overlay']} description consumer")
    if consumer["overlay"] == 16:
        # Verify the 1024-unit allocation is stored into the same reused +0x28 member.
        if data[offset + 10:offset + 14] != bytes.fromhex("616b8862"):
            raise ValueError("Unsupported PC shared-buffer assignment")
    return capacity


def capacity_from_code(data, base):
    offset = SITE - base
    code = data[offset:offset + 8]
    # Thumb movs r0,#capacity; movs r1,#6; bl String_New.
    if len(code) != 8 or code[1:4] != bytes.fromhex('200621') or memcheck._bl_target(data, offset + 4, base) != STRING_NEW:
        raise ValueError('Unsupported bag allocation code; investigate before trusting capacity')
    return code[0]


def check_lengths(strings, capacity):
    if capacity <= 0:
        raise ValueError('String capacity must be positive')
    findings = []
    for entry, units in enumerate(strings):
        if not units or units[-1] != msgtool.CODE_END:
            raise ValueError(f'Entry {entry}: missing terminator')
        if units[0] == msgtool.CODE_COMPRESSED:
            raise ValueError(f'Entry {entry}: compressed description needs explicit investigation')
        if len(units) > capacity:
            findings.append({'bank': BANK, 'id': entry, 'stored_units': len(units),
                             'capacity': capacity, 'excess_units': len(units) - capacity})
    return findings


def inspect_rom(path):
    import ndspy.rom
    import ndspy.narc
    rom = ndspy.rom.NintendoDSRom.fromFile(str(path))
    overlays = rom.loadArm9Overlays()
    consumers = []
    for spec in CONSUMERS:
        candidate = overlays[spec["overlay"]]
        capacity = consumer_capacity(bytes(candidate.data), candidate.ramAddress, spec)
        offset = spec["site"] - candidate.ramAddress
        consumers.append({"overlay": spec["overlay"], "context": spec["context"],
                          "allocation_site": f"{spec['site']:08X}", "allocation_offset": offset,
                          "allocation_code": bytes(candidate.data[offset:offset+spec["call_offset"]+4]).hex(),
                          "description_call": f"{spec['description_call']:08X}", "capacity": capacity})
    capacity = min(c["capacity"] for c in consumers)
    overlay = overlays[OVERLAY]
    arm9 = rom.loadArm9().sections[0]
    guard = arm9.data[COPY_GUARD - arm9.ramAddress:COPY_GUARD - arm9.ramAddress + 6]
    if guard != bytes.fromhex('2888844219D8'):
        raise ValueError('Unsupported String copy guard; investigate before applying length rule')
    archive = ndspy.narc.NARC(rom.getFileByName('a/0/2/7'))
    _, strings, _ = msgtool.decrypt_bank(archive.files[BANK])
    findings = check_lengths(strings, capacity)
    for consumer in consumers:
        consumer['overflow_ids'] = [f['id'] for f in check_lengths(strings, consumer['capacity'])]
    return {'schema_version': 1, 'status': 'failed' if findings else 'passed',
            'rom': memcheck.file_identity(path), 'allocation_site': f'{SITE:08X}',
            'copy_guard': f'{COPY_GUARD:08X}', 'overlay': OVERLAY,
            'allocation_offset': SITE - overlay.ramAddress,
            'allocation_code': bytes(overlay.data[SITE-overlay.ramAddress:SITE-overlay.ramAddress+8]).hex(),
            'capacity': capacity, 'consumers': consumers, 'checked_strings': len(strings),
            'maximum_stored_units': max(map(len, strings)), 'findings': findings}


def inspect_workspace(path, capacity, rom_path):
    document = json.loads(Path(path).read_text())
    cm = msgtool.Charmap.load([str(HERE / "charmap_en.tsv")])
    rows = document["strings"]
    if [row["id"] for row in rows] != list(range(len(rows))):
        raise ValueError("Workspace IDs must be contiguous and ordered")
    if any(row.get("en") is None for row in rows):
        raise ValueError("Workspace contains untranslated descriptions")
    units = [msgtool.encode_text(row["en"], cm) for row in rows]
    findings = check_lengths(units, capacity)
    import ndspy.rom
    import ndspy.narc
    rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
    _, built, _ = msgtool.decrypt_bank(ndspy.narc.NARC(rom.getFileByName("a/0/2/7")).files[BANK])
    return {"status": "failed" if findings else "passed", "checked_strings": len(rows),
            "maximum_stored_units": max(map(len, units)), "findings": findings,
            "rom_mismatch_ids": [i for i, (a, b) in enumerate(zip(units, built)) if a != b],
            "count_matches_rom": len(units) == len(built), "path": str(Path(path).resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', default=str(memcheck.DEF_ROM))
    parser.add_argument('--json')
    parser.add_argument('--workspace', help='also gate English workspace bank JSON against the same capacity')
    args = parser.parse_args(argv)
    try:
        report = inspect_rom(args.rom)
        if args.workspace:
            report["workspace"] = inspect_workspace(args.workspace, report["capacity"], args.rom)
            if report["workspace"]["status"] == "failed":
                report["status"] = "failed"
    except (Exception, SystemExit) as exc:
        report = {'schema_version': 1, 'status': 'incomplete', 'error': str(exc)}
    if args.json:
        destination = Path(args.json).resolve()
        if not destination.is_relative_to((memcheck.WORK / 'build').resolve()):
            parser.error('Reports must remain under ignored work/build')
        memcheck.atomic_report(destination, report)
    print(json.dumps(report, indent=2))
    return {'passed': 0, 'failed': 1, 'incomplete': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
