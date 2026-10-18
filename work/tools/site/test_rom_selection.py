"""Which ROM the docs and the site data describe (romdata.select_rom and friends). No ROM needed: CI has none."""
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'docs'))
sys.path.insert(0, HERE)
import romdata as R  # noqa: E402

SHA_A, SHA_B = 'a' * 40, 'b' * 40


class Releases:
    """A temporary work/release with the given folders: {tag: latest.json data or None (no latest.json)}."""

    def __init__(self, folders):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name
        for tag, manifest in folders.items():
            os.makedirs(os.path.join(self.path, tag))
            if manifest is not None:
                with open(os.path.join(self.path, tag, 'latest.json'), 'w') as fh:
                    json.dump(manifest, fh)

    def __enter__(self):
        return self.path

    def __exit__(self, *a):
        self.tmp.cleanup()


def manifest(tag, sha1=SHA_A):
    return dict(tag=tag, file='Origin_HeartGold_v4.0.3_EN_%s.xdelta' % tag, size=1, sha1=SHA_B, patched_sha1=sha1)


class TagOrder(unittest.TestCase):
    def test_versions_sort_numerically_and_a_final_beats_its_rcs(self):
        tags = ['v1.0.0', 'v1.0.0-rc10', 'v1.0.0-rc9', 'v0.9.0', 'v1.0.1-rc1']
        self.assertEqual(sorted(tags, key=R.tag_key), ['v0.9.0', 'v1.0.0-rc9', 'v1.0.0-rc10', 'v1.0.0', 'v1.0.1-rc1'])

    def test_prep_and_tester_folders_are_not_tags(self):
        for bad in ('wip', 'v1.0.0-rc7-public-prep', 'v1.0.0-rc7-all-fixes-tester-2', '1.0.0'):
            with self.assertRaises(ValueError):
                R.tag_key(bad)


class ResolveSpec(unittest.TestCase):
    def test_default_is_the_newest_release_with_a_latest_json(self):
        folders = {'v1.0.0-rc8': manifest('v1.0.0-rc8'), 'v1.0.0-rc10': None,     # rc10 not packaged yet
                   'v1.0.0-rc9': manifest('v1.0.0-rc9', SHA_B), 'v1.0.0-rc9-tester': manifest('v1.0.0-rc9-tester'),
                   'wip': None}
        with Releases(folders) as rel:
            self.assertEqual(R.release_tags(rel), ['v1.0.0-rc8', 'v1.0.0-rc9'])
            sel = R.resolve_rom_spec(None, env={}, releases=rel)
            self.assertEqual((sel['kind'], sel['label'], sel['tag'], sel['sha1']), ('release', 'v1.0.0-rc9', 'v1.0.0-rc9', SHA_B))
            self.assertEqual(sel['path'], os.path.join(R.RELEASE_ROMS, 'v1.0.0-rc9.nds'))
            self.assertEqual(sel['patch'], os.path.join(rel, 'v1.0.0-rc9', 'Origin_HeartGold_v4.0.3_EN_v1.0.0-rc9.xdelta'))
            self.assertEqual(R.resolve_rom_spec('release:latest', env={}, releases=rel)['tag'], 'v1.0.0-rc9')

    def test_named_release_env_and_other_kinds(self):
        with Releases({'v1.0.0-rc8': manifest('v1.0.0-rc8'), 'v1.0.0-rc9': manifest('v1.0.0-rc9', SHA_B)}) as rel:
            self.assertEqual(R.resolve_rom_spec('release:v1.0.0-rc8', env={}, releases=rel)['sha1'], SHA_A)
            env = {R.ROM_ENV: 'release:v1.0.0-rc8'}
            self.assertEqual(R.resolve_rom_spec(None, env=env, releases=rel)['tag'], 'v1.0.0-rc8')
            self.assertEqual(R.resolve_rom_spec('cn', env=env, releases=rel)['kind'], 'cn')    # --rom beats the env
        self.assertEqual(R.resolve_rom_spec('cn', env={})['path'], R.ROM_PATH)
        build = R.resolve_rom_spec('build', env={})
        self.assertEqual((build['kind'], build['path']), ('build', R.BUILD_ROM))
        self.assertNotIn('sha1', build)
        f = R.resolve_rom_spec('some/dir/test.nds', env={})
        self.assertEqual((f['kind'], f['label'], f['path']), ('file', 'test.nds', os.path.abspath('some/dir/test.nds')))

    def test_refusals(self):
        with Releases({'v1.0.0-rc8': manifest('v1.0.0-rc7'), 'v1.0.0-rc9': dict(manifest('v1.0.0-rc9'), patched_sha1='x'),
                       'v1.0.0-rc10': None}) as rel:
            with self.assertRaisesRegex(ValueError, 'names release'):
                R.resolve_rom_spec('release:v1.0.0-rc8', env={}, releases=rel)
            with self.assertRaisesRegex(ValueError, 'patched_sha1'):
                R.resolve_rom_spec('release:v1.0.0-rc9', env={}, releases=rel)
            with self.assertRaises(FileNotFoundError):
                R.resolve_rom_spec('release:v1.0.0-rc10', env={}, releases=rel)
            with self.assertRaises(ValueError):
                R.resolve_rom_spec('release:wip', env={}, releases=rel)
        with Releases({}) as rel:
            with self.assertRaisesRegex(ValueError, 'no work/release'):
                R.resolve_rom_spec(None, env={}, releases=rel)
        with self.assertRaisesRegex(ValueError, 'unknown ROM spec'):
            R.resolve_rom_spec('latest', env={})


class Materialize(unittest.TestCase):
    def test_an_existing_release_rom_with_the_right_hash_is_used_as_is(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'v1.0.0-rc8.nds')
            with open(path, 'wb') as fh:
                fh.write(b'rom bytes')
            sel = dict(kind='release', label='v1.0.0-rc8', path=path, sha1=hashlib.sha1(b'rom bytes').hexdigest(),
                       patch=os.path.join(d, 'missing.xdelta'))
            self.assertEqual(R.materialize_rom(sel, us_rom=os.path.join(d, 'missing-us.nds')), path)
            # a stale file is rebuilt, which needs the USA ROM and the patch
            sel['sha1'] = SHA_A
            with self.assertRaisesRegex(FileNotFoundError, 'needs'):
                R.materialize_rom(sel, us_rom=os.path.join(d, 'missing-us.nds'))

    def test_other_kinds_must_exist(self):
        with self.assertRaises(FileNotFoundError):
            R.materialize_rom(dict(kind='build', label='standard build (unreleased)', path='/nonexistent/rom.nds'))


class Identity(unittest.TestCase):
    def test_identity_and_mismatch(self):
        sel = dict(kind='release', label='v1.0.0-rc8', tag='v1.0.0-rc8', path='x', sha1=SHA_A)
        ident = R.rom_identity(sel, SHA_A)
        self.assertEqual(ident, dict(label='v1.0.0-rc8', kind='release', sha1=SHA_A, tag='v1.0.0-rc8'))
        self.assertIsNone(R.identity_mismatch(ident, ident))
        self.assertIn('records no ROM', R.identity_mismatch(None, ident))
        self.assertIn('records no ROM', R.identity_mismatch(dict(label='old'), ident))
        other = R.rom_identity(dict(kind='cn', label='Chinese hack v4.0.3 (untouched)'), SHA_B)
        msg = R.identity_mismatch(other, ident)
        self.assertIn('documents Chinese hack v4.0.3 (untouched) (SHA-1 %s), wanted v1.0.0-rc8' % SHA_B, msg)


def loader(fields):
    """An arm9 with the party builder's six `movs r1, #field; adds r2, #20+i` pairs at LOADER_EV_MOVS."""
    arm9 = bytearray(R.LOADER_EV_MOVS - R.ARM9_BASE + 12 * 6)
    for i, field in enumerate(fields):
        struct.pack_into('<4B', arm9, R.LOADER_EV_MOVS - R.ARM9_BASE + 12 * i, field, 0x21, 0x14 + i, 0x32)
    return bytes(arm9)


class TrainerEvOrder(unittest.TestCase):
    RECORD = bytes(20) + bytes([6, 252, 1, 2, 3, 250]) + bytes(2)   # the record's six EV bytes

    def test_chinese_rom_and_rc8(self):
        order = R.trainer_ev_order(loader([13, 14, 15, 16, 17, 18]))
        self.assertEqual(order, R.CN_EV_ORDER)
        # byte 3 goes to Speed (field 16), bytes 4/5 to Sp. Atk / Sp. Def; shown HP/Atk/Def/SpA/SpD/Spe
        self.assertEqual(R.parse_trpoke(self.RECORD, 1, order)[0]['evs'], [6, 252, 1, 3, 250, 2])
        self.assertEqual(R.parse_trpoke(self.RECORD, 1)[0]['evs'], [6, 252, 1, 3, 250, 2])

    def test_fix_trainer_ev_order(self):
        # work/patches/trainer-ev-order: record bytes 3/4/5 -> fields 0x11 (SpA), 0x12 (SpD), 0x10 (Spe)
        order = R.trainer_ev_order(loader([13, 14, 15, 17, 18, 16]))
        self.assertEqual(order, (0, 1, 2, 3, 4, 5))
        self.assertEqual(R.parse_trpoke(self.RECORD, 1, order)[0]['evs'], [6, 252, 1, 2, 3, 250])

    def test_unknown_code_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'not `movs'):
            R.trainer_ev_order(loader([13, 14, 15, 16, 17, 19]))
        with self.assertRaisesRegex(ValueError, 'permutation'):
            R.trainer_ev_order(loader([13, 14, 15, 16, 17, 17]))


class EnglishText(unittest.TestCase):
    def rom(self, lang, texts):
        rom = object.__new__(R.Rom)
        rom.lang, rom._texts = lang, {9999: texts}
        return rom

    def test_english_rom_text_replaces_the_workspace_but_never_leaks_chinese(self):
        rows = {1: dict(id=1, zh='甲', en='Old name', status='draft'), 2: dict(id=2, zh='乙', en=None),
                3: dict(id=3, zh='丙', en='Kept')}
        old = R.load_bank_full, R.load_bank
        R.load_bank_full = lambda num: {k: dict(v) for k, v in rows.items()}
        R.load_bank = lambda num: {k: v['en'] or v['zh'] for k, v in rows.items()}
        try:
            rom = self.rom('en', {0: '', 1: 'New name', 2: '乙'})
            full = rom.bank_full(9999)
            self.assertEqual((full[1]['en'], full[1]['status']), ('New name', 'draft'))
            self.assertIsNone(full[2]['en'])                 # still Chinese in the ROM: no English
            self.assertEqual(full[3]['en'], 'Kept')          # an id the ROM lacks keeps the workspace row
            self.assertEqual(full[0]['en'], '')
            self.assertEqual(rom.bank(9999), {0: '', 1: 'New name', 2: '乙', 3: 'Kept'})
            cn = self.rom('zh', {1: '甲'})
            self.assertEqual(cn.bank(9999), {1: 'Old name', 2: '乙', 3: 'Kept'})
            self.assertEqual(cn.bank_full(9999)[1]['en'], 'Old name')
        finally:
            R.load_bank_full, R.load_bank = old


class ExportCheck(unittest.TestCase):
    def test_committed_rom_reads_meta(self):
        import export_data as E
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(E.committed_rom(d))
            with open(os.path.join(d, 'meta.json'), 'w') as fh:
                json.dump(dict(game='x', rom=dict(label='v1.0.0-rc8', kind='release', sha1=SHA_A)), fh)
            self.assertEqual(E.committed_rom(d)['sha1'], SHA_A)


if __name__ == '__main__':
    unittest.main()
