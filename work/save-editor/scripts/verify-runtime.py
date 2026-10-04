#!/usr/bin/env python3
"""Boot an edited save in an isolated existing DeSmuME installation.

Run from this worktree's root. --out must be a NEW directory underneath
work/save-editor/local. --expect is JSON containing one four-move array per
party member, in order. No ROMs are built or downloaded. Add --persistence
to verify an in-game save counter increase and reset/reload of party moves.
--expect-stats additionally compares independently decoded full party stats at
load and reload; all records are copied before emulator destruction.
"""
import argparse
import hashlib
import json
import itertools
import os
from pathlib import Path
import subprocess
import struct
import sys


def identity(path):
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


STAT_KEYS = ("hp", "attack", "defense", "speed", "spAttack", "spDefense")
STAT_FIELDS = ("pid", "speciesId", "ivs", "evs", "nature", "form", "experience", "party")


def decode_party_stats(blob):
    """Independently decrypt a copied native record; never write emulator memory."""
    if not isinstance(blob, bytes) or len(blob) != 236:
        raise ValueError("Expected a full 236-byte party record")
    pid, flags, checksum = struct.unpack_from("<IHH", blob)
    if flags:
        raise ValueError("Pokemon record is open, corrupt or has unknown flags")

    def decrypt(payload, seed):
        words = []
        for word in struct.unpack("<%dH" % (len(payload) // 2), payload):
            seed = (seed * 1103515245 + 24691) & 0xffffffff
            words.append(word ^ (seed >> 16))
        return struct.pack("<%dH" % len(words), *words)

    payload = decrypt(blob[8:136], checksum)
    if sum(struct.unpack("<64H", payload)) & 0xffff != checksum:
        raise ValueError("Pokemon checksum mismatch")
    # Physical order is the lexicographic permutation selected by PID.
    permutation = list(itertools.permutations(range(4)))[((pid >> 13) & 31) % 24]
    a, b = (payload[permutation.index(block) * 32:permutation.index(block) * 32 + 32]
            for block in (0, 1))
    iv_word = struct.unpack_from("<I", b, 16)[0]
    nature_override = (struct.unpack_from("<I", b, 20)[0] >> 25) & 63
    tail = decrypt(blob[136:], pid)
    return {"pid": pid, "speciesId": struct.unpack_from("<H", a)[0],
            "ivs": {key: (iv_word >> (5 * index)) & 31 for index, key in enumerate(STAT_KEYS)},
            "evs": dict(zip(STAT_KEYS, a[16:22])),
            "nature": nature_override - 1 if nature_override else pid % 25,
            "form": b[24] >> 3, "experience": struct.unpack_from("<I", a, 8)[0],
            "party": {"level": tail[4], "currentHp": struct.unpack_from("<H", tail, 6)[0],
                      "stats": dict(zip(STAT_KEYS, struct.unpack_from("<6H", tail, 8))),
                      "status": struct.unpack_from("<I", tail)[0]}}



def decode_party_traits(blob):
    """Independently decode copied data; never mutate emulator memory."""
    stats = decode_party_stats(blob)
    pid = stats["pid"]
    seed = struct.unpack_from("<H", blob, 6)[0]
    words = []
    for word in struct.unpack("<64H", blob[8:136]):
        seed = (seed * 1103515245 + 24691) & 0xffffffff
        words.append(word ^ (seed >> 16))
    payload = struct.pack("<64H", *words)
    permutation = list(itertools.permutations(range(4)))[((pid >> 13) & 31) % 24]
    a, b, d = (payload[permutation.index(block)*32:permutation.index(block)*32+32] for block in (0, 1, 3))
    trainer = struct.unpack_from("<I", a, 4)[0]
    natural = ((pid & 65535) ^ (pid >> 16) ^ (trainer & 65535) ^ (trainer >> 16)) < 8
    override = bool(struct.unpack_from("<I", b, 20)[0] >> 31)
    raw = d[26]
    return {"shiny": natural or override, "naturalShiny": natural, "shinyOverride": override,
            "pokerus": {"raw": raw, "strain": raw >> 4, "days": raw & 15,
                        "status": "infected" if raw & 15 else "cured" if raw else "none"}}


def expected_traits_rows(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
        raise ValueError("Expected 1–6 complete party-trait rows")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"shiny", "naturalShiny", "shinyOverride", "pokerus"}:
            raise ValueError("Expected complete trait fields")
        if any(type(row[key]) is not bool for key in ("shiny", "naturalShiny", "shinyOverride")):
            raise ValueError("Shiny expectations must be booleans")
        if row["shiny"] != (row["naturalShiny"] or row["shinyOverride"]):
            raise ValueError("Inconsistent shiny expectation")
        virus = row["pokerus"]
        if not isinstance(virus, dict) or set(virus) != {"raw", "strain", "days", "status"}:
            raise ValueError("Expected full Pokérus fields")
        raw = virus["raw"]
        if type(raw) is not int or not 0 <= raw <= 255:
            raise ValueError("Invalid Pokérus byte")
        if (type(virus["strain"]) is not int or type(virus["days"]) is not int or
                virus["strain"] != raw >> 4 or virus["days"] != raw & 15 or
                virus["status"] != ("infected" if raw & 15 else "cured" if raw else "none")):
            raise ValueError("Inconsistent Pokérus expectation")
    return rows


def checked_traits(checkpoint, expected, gaps, label):
    evidence = checkpoint.get("stats", {})
    before = len(gaps)
    checked_stats(checkpoint, [row.get("decoded") for row in evidence.get("slots", [])], gaps, label)
    if len(gaps) != before:
        return None
    try:
        observed = [decode_party_traits(bytes.fromhex(row["record_hex"])) for row in evidence["slots"]]
        if observed != expected:
            gaps.append(f"{label} party traits differ from expectation")
        return observed
    except (ValueError, KeyError, TypeError, struct.error) as exc:
        gaps.append(f"{label} trait evidence unavailable: {exc}")
        return None


def snapshot_stats(probe, memcheck):
    party = probe.party_snapshot()
    result = {"status": "incomplete", "party_address": party.get("address"),
              "observed_frame": probe.frame, "slots": []}
    if party.get("status") != "passed":
        return dict(result, error="Missing bounded party owner")
    # Revalidate native header and all identities before copying full records.
    if memcheck.read_party_snapshot(probe.mem, party["address"]) != party:
        return dict(result, error="Party owner changed before stat copy")
    try:
        for slot, pid in enumerate(party["identities"]):
            address = party["address"] + 8 + 236 * slot
            blob = bytes(probe.mem.read_byte(address + offset) for offset in range(236))
            decoded = decode_party_stats(blob)
            if decoded["pid"] != pid:
                raise ValueError("Party identity changed during stat copy")
            result["slots"].append({"slot": slot, "address": address,
                                    "record_hex": blob.hex(), "decoded": decoded})
        if memcheck.read_party_snapshot(probe.mem, party["address"]) != party:
            raise ValueError("Party owner changed after stat copy")
        return dict(result, status="passed")
    except Exception as exc:
        return dict(result, error=f"Party stats unavailable: {exc}")


def expected_stats_rows(rows):
    """Validate required expectation fields; unrelated decoder fields are ignored."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
        raise ValueError("Expected 1–6 full party-stat records")
    result = []
    def bounded(value, maximum):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError("Expected bounded integer stat fields")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Expected party-stat objects")
        clean = {key: row[key] for key in STAT_FIELDS}
        for key, maximum in (("pid", 0xffffffff), ("speciesId", 65535), ("nature", 62),
                             ("form", 31), ("experience", 0xffffffff)):
            bounded(clean[key], maximum)
        for group, maximum in (("ivs", 31), ("evs", 255)):
            if not isinstance(clean[group], dict) or set(clean[group]) != set(STAT_KEYS):
                raise ValueError("Expected all six IV/EV fields")
            for value in clean[group].values():
                bounded(value, maximum)
        party = clean["party"]
        if (not isinstance(party, dict) or set(party) != {"level", "currentHp", "stats", "status"} or
                not isinstance(party["stats"], dict) or set(party["stats"]) != set(STAT_KEYS)):
            raise ValueError("Expected complete party stats")
        for key, maximum in (("level", 255), ("currentHp", 65535), ("status", 0xffffffff)):
            bounded(party[key], maximum)
        for value in party["stats"].values():
            bounded(value, 65535)
        result.append(clean)
    return result


def checked_stats(checkpoint, expected, gaps, label):
    evidence, party = checkpoint.get("stats", {}), checkpoint.get("party", {})
    try:
        if (evidence.get("status") != "passed" or party.get("status") != "passed" or
                evidence.get("party_address") != party.get("address") or
                evidence.get("observed_frame") != checkpoint.get("frame") or
                len(evidence.get("slots", [])) != party.get("count")):
            raise ValueError("Complete bounded party stats unavailable")
        observed = []
        for slot, record in enumerate(evidence["slots"]):
            decoded = decode_party_stats(bytes.fromhex(record["record_hex"]))
            if (record["slot"] != slot or record["address"] != party["address"] + 8 + 236 * slot or
                    decoded["pid"] != party["identities"][slot] or decoded != record["decoded"]):
                raise ValueError("Stat evidence disagrees with copied record or owner")
            observed.append(decoded)
        if observed != expected:
            gaps.append(f"{label} party stats differ from expectation")
        return observed
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        gaps.append(f"{label} stat evidence incomplete: {exc}")
        return None


# Offsets independently established from the untouched Origin ARM9 pocket dispatch.
INVENTORY_POCKETS = {
    "items": (0, 165), "keyItems": (0x294, 50), "tmHm": (0x35c, 151),
    "mail": (0x5b8, 12), "medicine": (0x5e8, 40), "berries": (0x688, 64),
    "balls": (0x788, 24), "battle": (0x7e8, 30),
}


def decode_inventory(bag, money):
    if len(bag) != 0x864 or len(money) != 4:
        raise ValueError("Incomplete bounded inventory records")
    pockets = {}
    for name, (offset, count) in INVENTORY_POCKETS.items():
        rows = []
        for index in range(count):
            item, quantity = struct.unpack_from("<HH", bag, offset + index * 4)
            if item or quantity:
                rows.append({"id": item, "quantity": quantity})
        pockets[name] = rows
    return {"money": struct.unpack("<I", money)[0], "pockets": pockets,
            "registeredItems": list(struct.unpack_from("<HH", bag, 0x860))}


def expected_inventory_row(row):
    if not isinstance(row, dict) or set(row) - {"money", "pockets", "registeredItems"}:
        raise ValueError("Expected inventory object")
    if type(row.get("money")) is not int or not 0 <= row["money"] <= 9999999:
        raise ValueError("Expected money in 0–9999999")
    if not isinstance(row.get("pockets"), dict) or set(row["pockets"]) != set(INVENTORY_POCKETS):
        raise ValueError("Expected all eight inventory pockets")
    for name, (_, capacity) in INVENTORY_POCKETS.items():
        rows = row["pockets"][name]
        if not isinstance(rows, list) or len(rows) > capacity:
            raise ValueError("Inventory pocket exceeds capacity")
        seen = set()
        for entry in rows:
            if (not isinstance(entry, dict) or set(entry) != {"id", "quantity"} or
                    type(entry["id"]) is not int or not 1 <= entry["id"] <= 790 or
                    type(entry["quantity"]) is not int or
                    not 1 <= entry["quantity"] <= (99 if name == "tmHm" else 999) or
                    entry["id"] in seen):
                raise ValueError("Invalid inventory expectation slot")
            seen.add(entry["id"])
    if "registeredItems" in row and (not isinstance(row["registeredItems"], list) or
            len(row["registeredItems"]) != 2 or any(type(x) is not int or not 0 <= x <= 790
                                                   for x in row["registeredItems"])):
        raise ValueError("Expected two registered item IDs")
    return row


def snapshot_inventory(probe, owners):
    result = {"status": "incomplete", "observed_frame": probe.frame}
    try:
        if len(owners) != 1:
            raise ValueError("Missing or ambiguous native save owner")
        owner = next(iter(owners))
        def read(address, size):
            if not 0x02000000 <= address <= 0x02400000 - size:
                raise ValueError("Native inventory address outside main RAM")
            return bytes(probe.mem.read_byte(address + i) for i in range(size))
        def address(index):
            offset = struct.unpack("<I", read(owner + 0x2e01c + 16 * index, 4))[0]
            if offset > 0xf7bc:
                raise ValueError("Invalid native save-array offset")
            return owner + 0x10 + offset
        party = address(2)
        if probe.party_snapshot().get("address") != party:
            raise ValueError("Native save owner disagrees with bounded party")
        bag_address, money_address = address(3), address(1) + 0x18
        bag, money = read(bag_address, 0x864), read(money_address, 4)
        if bag != read(bag_address, 0x864) or money != read(money_address, 4):
            raise ValueError("Inventory changed during copy")
        return dict(result, status="passed", owner=owner, bag_address=bag_address,
                    money_address=money_address, bag_hex=bag.hex(), money_hex=money.hex(),
                    decoded=decode_inventory(bag, money))
    except (ValueError, struct.error) as exc:
        return dict(result, error=str(exc))


def checked_inventory(checkpoint, expected, gaps, label):
    try:
        evidence = checkpoint.get("inventory", {})
        if evidence.get("status") != "passed" or evidence.get("observed_frame") != checkpoint.get("frame"):
            raise ValueError("Missing complete inventory snapshot")
        decoded = decode_inventory(bytes.fromhex(evidence["bag_hex"]), bytes.fromhex(evidence["money_hex"]))
        if decoded != evidence["decoded"]:
            raise ValueError("Copied native inventory disagrees with decoded evidence")
        if any(decoded[key] != value for key, value in expected.items()):
            gaps.append(f"{label} inventory differs from expectation")
        return decoded
    except (ValueError, TypeError, KeyError, struct.error) as exc:
        gaps.append(f"{label} inventory evidence incomplete: {exc}")
        return None


def exported_inventory(path):
    general_counter(path)  # Independently validates native battery CRCs first.
    data = path.read_bytes()
    base = max((0, 0x40000), key=lambda offset: struct.unpack_from("<I", data, offset + 0xf7bc)[0])
    return decode_inventory(data[base + 0x644:base + 0xea8], data[base + 0x78:base + 0x7c])


def worker(args):
    # Parent establishes isolation before this fresh interpreter imports tools.
    sys.path.insert(0, str(args.repo / "work/tools"))
    import memcheck
    memcheck._check_code(args.rom)
    if args.expect_traits:
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(str(args.rom)).loadArm9().sections[0].data
        for address, signature in {
            0x0206dc2c: "6869c40f98e1",
            0x0206de7c: "8c7e71e0",
            0x0206e394: "6969da4814b001402078c00708436861f8bd",
            0x0206e754: "207814b0b076f8bd",
            0x0206f3f8: "38b5bd210022051cfef7a2fa012801d1012038bd281c07210022fef799fa0021041c281c0a1cfef793fa011c201c00f001f838bd094b0a041940034000041b0c000c090c5840120c48405040082801d2012000e000200006000e7047",
            0x02070cf0: "08b59a210022fcf727fe0f21084201d0012008bd002008bd",
            0x02070d10: "08b59a210022fcf717fe0006010e0f20084201d0002008bdf020084201d0012008bd002008bd",
        }.items():
            want = bytes.fromhex(signature)
            if arm9[address - 0x02000000:address - 0x02000000 + len(want)] != want:
                raise ValueError(f"Unsupported trait code at {address:08x}")
    if args.expect_inventory:
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(str(args.rom)).loadArm9().sections[0].data
        for address, signature in {
            0x0202933c: "08b50121fef7fef9001d08bd",
            0x020294b4: "40697047034a914200d9111c4161081c7047c0467f969800",
            0x02076e28: "014b03211847c04641770202",
        }.items():
            want = bytes.fromhex(signature)
            # The common SaveArrayGet signature is checked by memcheck too.
            if arm9[address - 0x02000000:address - 0x02000000 + len(want)] != want:
                raise ValueError(f"Unsupported inventory code at {address:08x}")
    if args.persistence or args.expect_stats or args.expect_traits or args.expect_inventory:
        raw = persistence_run(args, memcheck)
    else:
        probe = memcheck.run_scenario(str(args.rom), str(args.save),
                                     "boot; shot loaded", str(args.out), "runtime")
        raw = memcheck.probe_data(probe)
    print("MEMCHECK " + json.dumps(raw), flush=True)


def general_counter(path):
    """Validate both general blocks, then return their newest bounded counter."""
    data = path.read_bytes()
    if len(data) != 524288:
        raise ValueError("Native export is not a raw 512 KiB save")
    counters = []
    for base in (0, 0x40000):
        footer = base + 0xf7cc - 16
        counter, size, magic, block, checksum = struct.unpack_from("<IIIHH", data, footer)
        crc = 0xffff
        for value in data[base:footer]:
            crc ^= value << 8
            for _ in range(8):
                crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
        if (size, magic, block, checksum) != (0xf7cc, 0x20060623, 0, crc):
            raise ValueError("Native export general-block footer/CRC invalid")
        counters.append(counter)
    if abs(counters[0] - counters[1]) >= 0x80000000:
        raise ValueError("Save counter rollover is unsupported")
    return max(counters)


def persistence_run(args, memcheck):
    from desmume.controls import Keys, keymask
    from desmume.emulator import DeSmuME
    isolation = memcheck.reproducibility.begin_worker(os.environ["XDG_CONFIG_HOME"])
    game = args.out / "game.nds"
    game.symlink_to(args.rom)
    emu = DeSmuME()
    try:
        environment = memcheck.reproducibility.worker_environment(emu, isolation)
        emu.open(str(game))
        if not emu.backup.import_file(str(args.save), 524288):
            raise RuntimeError("Save import failed")
        emu.reset()
        probe = memcheck.Probe(emu)
        probe.environment = environment
        inventory_owners = set()
        if args.expect_inventory:
            def save_array_return(address, size):
                probe._on_save_array_return(address, size)
                if probe.R.r4 in (1, 2, 3):
                    inventory_owners.add(probe.R.r5)
            emu.memory.register_exec(memcheck.PARTY_GET_RETURN, save_array_return)
        trait_calls = []
        pending_traits = {}
        if args.observe_traits:
            def trait_entry(kind):
                def callback(address, size):
                    party = probe.party_snapshot()
                    pointer = probe.R.r0
                    if party.get("status") != "passed":
                        return
                    slot = (pointer - party["address"] - 8) // 236
                    if not 0 <= slot < party["count"] or pointer != party["address"] + 8 + slot * 236:
                        return
                    pid = probe.mem.read_long(pointer)
                    if pid != party["identities"][slot]:
                        return
                    pending_traits[(kind, probe.R.sp)] = {"kind": kind, "slot": slot, "address": pointer,
                        "pid": pid, "entry_frame": probe.frame, "party_address": party["address"]}
                return callback
            def trait_return(kind, stack_size):
                def callback(address, size):
                    entry = pending_traits.pop((kind, probe.R.sp + stack_size), None)
                    if entry is None:
                        return
                    party = probe.party_snapshot()
                    if (party.get("status") != "passed" or party["address"] != entry["party_address"] or
                            entry["slot"] >= party["count"] or party["identities"][entry["slot"]] != entry["pid"]):
                        return
                    trait_calls.append(dict(entry, return_frame=probe.frame, result=probe.R.r0, return_address=address))
                return callback
            for kind, entry, returns, stack_size in [
                ("shiny", 0x0206f3f8, (0x0206f40a, 0x0206f42a), 16),
                ("infected", 0x02070cf0, (0x02070d02, 0x02070d06), 8),
                ("cured", 0x02070d10, (0x02070d26, 0x02070d30, 0x02070d34), 8),
            ]:
                emu.memory.register_exec(entry, trait_entry(kind))
                for address in returns:
                    emu.memory.register_exec(address, trait_return(kind, stack_size))
        boot_start_frame = probe.frame

        def step(frames):
            for _ in range(frames):
                emu.cycle(with_joystick=False)
                probe.frame += 1
                if probe.frame - boot_start_frame >= 600 and probe.frame % 30 == 0 and probe.corrupt is None:
                    bad = probe.heap_walk()
                    if bad:
                        probe.corrupt = (probe.frame, bad)

        def press(name, wait=90):
            mask = keymask(getattr(Keys, "KEY_" + name))
            emu.input.keypad_add_key(mask)
            step(6)
            emu.input.keypad_rm_key(mask)
            step(wait)

        def shot(name):
            path = args.out / ("runtime_" + name + ".png")
            emu.screenshot().save(str(path))
            probe.screenshots.append(str(path))
            probe.checkpoints[name] = {"frame": probe.frame, "party": probe.party_snapshot(),
                                       "moves": probe.move_snapshot(), "screenshot": str(path),
                                       "screenshot_captured": path.is_file()}
            if args.expect_stats or args.expect_traits:
                probe.checkpoints[name]["stats"] = snapshot_stats(probe, memcheck)

            if args.expect_inventory:
                probe.checkpoints[name]["inventory"] = snapshot_inventory(probe, inventory_owners)

        def observe_summary(label):
            for _ in range(3):
                press("B", 200)
            press("X")
            press("DOWN", 30)
            press("A", 200)
            press("A", 60)
            press("A", 200)
            count = probe.party_snapshot().get("count", 0)
            for slot in range(count):
                shot(f"{label}_summary_{slot}")
                if slot + 1 < count:
                    press("DOWN", 200)
            for _ in range(3):
                press("B", 200)

        def boot():
            step(2400)
            press("START", 400)
            for _ in range(4):
                press("A", 300)
            step(600)
            probe.armed = True

        boot()
        shot("loaded")
        if args.observe_traits:
            observe_summary("loaded")
        if not args.persistence:
            probe.script_completed = True
            raw = memcheck.probe_data(probe)
            raw["native_trait_calls"] = trait_calls
            return raw
        for _ in range(3):
            press("B", 200)
        press("X")
        if args.observe_traits:
            press("UP", 30)
        press("RIGHT", 30)
        press("DOWN", 30)
        press("A", 200)
        shot("save_prompt")
        press("A", 1500)
        shot("save_first_confirmation")
        press("A", 1500)
        shot("saved")
        export = args.out / "saved-in-game.sav"
        if not emu.backup.export_file(str(export)):
            raise RuntimeError("Native battery export failed")
        before, after = general_counter(args.save), general_counter(export)
        persistence = {"counter_before": before, "counter_after": after,
                       "counter_increased": after > before, "export": identity(export)}
        # Native reset reruns initialization that legitimately writes low memory.
        # Preserve accumulated failure evidence, but discard live-call contexts.
        probe.armed = False
        probe._pending = None
        probe._item_contexts.clear()
        probe.summary_screen = probe.summary_context = None
        probe.summary_observed_frame = -1
        probe.party_addresses.clear()
        inventory_owners.clear()
        pending_traits.clear()
        boot_start_frame = probe.frame
        emu.reset()
        boot()
        shot("reloaded")
        if args.observe_traits:
            observe_summary("reloaded")
        probe.script_completed = True
        raw = memcheck.probe_data(probe)
        raw["persistence"] = persistence
        raw["native_trait_calls"] = trait_calls
        return raw
    finally:
        emu.destroy()



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expect", type=Path)
    parser.add_argument("--observe-traits", action="store_true", help="Open every party summary and capture guarded native trait getter returns")
    parser.add_argument("--expect-traits", type=Path, help="JSON shiny/Pokérus traits to verify at load and reset/reload")
    parser.add_argument("--expect-stats", type=Path, help="JSON decoded party stats to verify at load and reset/reload")
    parser.add_argument("--expect-inventory", type=Path, help="JSON money and all eight pockets to verify at load/reload and native export")
    parser.add_argument("--persistence", action="store_true", help="Save through game menu, reset, and verify party again")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for field in ("repo", "rom", "save", "out", "expect_stats", "expect_traits", "expect_inventory"):
        value = getattr(args, field)
        if value is not None:
            setattr(args, field, value.resolve())
    if args.observe_traits and not args.expect_traits:
        parser.error("--observe-traits requires --expect-traits")
    if args.worker:
        worker(args)
        return 0
    local = (Path.cwd() / "work/save-editor/local").resolve()
    if not args.out.is_relative_to(local) or args.out == local:
        parser.error("--out must be a new subdirectory of work/save-editor/local")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not args.save.is_file() or args.save.stat().st_size != 524288:
        parser.error("--save must be a raw 512 KiB save")
    python = args.repo / ".venv/bin/python"
    if not python.is_file() or not args.rom.is_file():
        parser.error("Existing repository .venv/bin/python and --rom are required")
    expected = json.loads(args.expect.read_text()) if args.expect else None
    if expected is not None and not (
            isinstance(expected, list) and 1 <= len(expected) <= 6 and
            all(isinstance(row, list) and len(row) == 4 and
                all(type(move) is int and 0 <= move <= 65535 for move in row)
                for row in expected)):
        parser.error("--expect must contain 1–6 arrays of four integer move IDs")
    try:
        expected_stats = expected_stats_rows(json.loads(args.expect_stats.read_text())) if args.expect_stats else None
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(f"Invalid --expect-stats: {exc}")
    try:
        expected_inventory = expected_inventory_row(json.loads(args.expect_inventory.read_text())) if args.expect_inventory else None
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(f"Invalid --expect-inventory: {exc}")
    try:
        expected_traits = expected_traits_rows(json.loads(args.expect_traits.read_text())) if args.expect_traits else None
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(f"Invalid --expect-traits: {exc}")
    args.out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for variable, directory in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"),
                                ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"),
                                ("TMPDIR", "tmp")):
        path = args.out / directory
        path.mkdir()
        env[variable] = str(path)
    before = {"rom": identity(args.rom), "save": identity(args.save)}
    command = [str(python), str(Path(__file__).resolve()), "--worker",
               "--repo", str(args.repo), "--rom", str(args.rom),
               "--save", str(args.save), "--out", str(args.out)]
    if args.persistence:
        command.append("--persistence")
    if args.observe_traits:
        command.append("--observe-traits")
    if args.expect_traits:
        command.extend(["--expect-traits", str(args.expect_traits)])
    if args.expect_stats:
        command.extend(["--expect-stats", str(args.expect_stats)])
    if args.expect_inventory:
        command.extend(["--expect-inventory", str(args.expect_inventory)])
    try:
        result = subprocess.run(command, env=env, capture_output=True,
                                text=True, timeout=args.timeout)
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        stdout, stderr, returncode = text(exc.stdout), text(exc.stderr), None
    (args.out / "stdout.log").write_text(stdout)
    (args.out / "stderr.log").write_text(stderr)
    records = [line[9:] for line in stdout.splitlines() if line.startswith("MEMCHECK ")]
    raw = json.loads(records[-1]) if records else {}
    sys.path.insert(0, str(args.repo / "work/tools"))
    import memcheck
    gaps = memcheck.evidence_gaps(raw)
    if returncode != 0:
        gaps.append("Worker timed out" if returncode is None else f"Worker exited {returncode}")
    checkpoint = raw.get("checkpoints", {}).get("loaded", {})
    party, moves = checkpoint.get("party", {}), checkpoint.get("moves", {})
    if party.get("status") != "passed" or moves.get("status") != "passed":
        gaps.append("Complete bounded party/move snapshots unavailable")
    observed = [slot.get("moves") for slot in moves.get("slots", [])]
    if len(observed) != party.get("count"):
        gaps.append("Move snapshots do not cover the entire party")
    if expected is not None and observed != expected:
        gaps.append("Runtime party moves differ from expectation")
    observed_stats = checked_stats(checkpoint, expected_stats, gaps, "Loaded") if expected_stats is not None else None
    observed_inventory = checked_inventory(checkpoint, expected_inventory, gaps, "Loaded") if expected_inventory is not None else None
    reloaded_inventory = native_inventory = None
    observed_traits = checked_traits(checkpoint, expected_traits, gaps, "Loaded") if expected_traits is not None else None
    reloaded_traits = None
    reloaded_stats = None
    if not checkpoint.get("screenshot_captured"):
        gaps.append("Loaded checkpoint screenshot missing")
    for key in ("fails", "nullw", "corrupt"):
        if raw.get(key):
            gaps.append(f"Runtime guard reported {key}")
    if memcheck.reproducibility.worker_environment_status(raw.get("environment")) != "passed":
        gaps.append("Native runtime environment evidence incomplete")
    if args.persistence:
        evidence = raw.get("persistence", {})
        reload_state = raw.get("checkpoints", {}).get("reloaded", {})
        reload_party, reload_moves = reload_state.get("party", {}), reload_state.get("moves", {})
        if expected_traits is not None:
            reloaded_traits = checked_traits(reload_state, expected_traits, gaps, "Reloaded")
        if expected_stats is not None:
            reloaded_stats = checked_stats(reload_state, expected_stats, gaps, "Reloaded")
        if expected_inventory is not None:
            reloaded_inventory = checked_inventory(reload_state, expected_inventory, gaps, "Reloaded")
            try:
                native_inventory = exported_inventory(args.out / "saved-in-game.sav")
                if any(native_inventory[key] != value for key, value in expected_inventory.items()):
                    gaps.append("Native battery inventory differs from expectation")
            except (OSError, ValueError, struct.error) as exc:
                gaps.append(f"Native battery inventory unavailable: {exc}")
        reloaded = [slot.get("moves") for slot in reload_moves.get("slots", [])]
        if not evidence.get("counter_increased"):
            gaps.append("In-game save counter did not increase")
        if (reload_party.get("status") != "passed" or reload_moves.get("status") != "passed" or
                reloaded != observed or reload_party.get("identities") != party.get("identities")):
            gaps.append("Reset/reload party identities or moves differ or are unavailable")
    native_traits = raw.get("native_trait_calls", [])
    if args.observe_traits:
        for slot, row in enumerate(expected_traits):
            for kind, wanted in (("shiny", row["shiny"]), ("infected", row["pokerus"]["status"] == "infected"),
                                 ("cured", row["pokerus"]["status"] == "cured")):
                if kind == "infected" and row["pokerus"]["status"] == "cured":
                    continue  # Native summary short-circuits infected check when cured is true.
                calls = [call for call in native_traits if call.get("slot") == slot and call.get("kind") == kind]
                if not calls:
                    gaps.append(f"Native {kind} getter not observed for party slot {slot}")
                elif any(call.get("result") != int(wanted) for call in calls):
                    gaps.append(f"Native {kind} getter mismatch for party slot {slot}")
    after = {"rom": identity(args.rom), "save": identity(args.save)}
    if before != after:
        gaps.append("Input ROM or save changed")
    report = {"status": "passed" if not gaps else "incomplete", "gaps": gaps,
              "expected_moves": expected, "observed_moves": observed,
              "expected_inventory": expected_inventory, "observed_inventory": observed_inventory,
              "reloaded_inventory": reloaded_inventory, "native_export_inventory": native_inventory,
              "inventory_expectation_check": "checked" if expected_inventory is not None else "not_requested",
              "native_trait_observation": "checked" if args.observe_traits else "not_requested",
              "expected_traits": expected_traits, "observed_traits": observed_traits, "reloaded_traits": reloaded_traits,
              "trait_expectation_check": "checked" if expected_traits is not None else "not_requested",
              "expected_stats": expected_stats, "observed_stats": observed_stats, "reloaded_stats": reloaded_stats,
              "stat_expectation_check": "checked" if expected_stats is not None else "not_requested",
              "expectation_check": "checked" if expected is not None else "not_requested",
              "in_game_save_reload": ("passed" if not gaps else "incomplete") if args.persistence else "not_verified", "inputs_before": before,
              "inputs_after": after, "returncode": returncode, "runtime": raw}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "gaps", "observed_moves", "in_game_save_reload")}, indent=2))
    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
