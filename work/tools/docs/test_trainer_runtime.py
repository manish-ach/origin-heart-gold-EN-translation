"""Regression coverage for the reviewed Chinese v4.0.3 trainer loader.

Synthetic tests run without game data. The optional local-ROM check pins the
reviewed code regions by hashes, without embedding or distributing ROM bytes.
"""
import hashlib
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import romdata as R


def record(level=20, form=0, iv=100, evs=(0, 0, 0, 0, 0, 0)):
    return (bytes([iv, 0, form, 255]) + struct.pack('<4H', 26, level, 479, 0)
            + bytes(8) + bytes(evs) + bytes(2))


class TrainerRuntimeTests(unittest.TestCase):
    def test_form_is_separate_byte(self):
        mon = R.parse_trpoke(record(form=4), 1)[0]
        self.assertEqual((mon['species'], mon['form']), (479, 4))

    def test_ev_display_order_follows_engine_stat_ids(self):
        mon = R.parse_trpoke(record(evs=(1, 2, 3, 4, 5, 6)), 1)[0]
        self.assertEqual(mon['evs'], [1, 2, 3, 5, 6, 4])

    def test_hp_iv_override_boundaries_and_other_ivs(self):
        for level, hp in [(1, 10), (40, 10), (41, 20), (79, 20), (80, 31), (100, 31)]:
            with self.subTest(level=level):
                mon = R.parse_trpoke(record(level=level), 1)[0]
                self.assertEqual(mon['hp_ivs'], hp)
                self.assertEqual(mon['ivs'], 12)
                self.assertEqual(mon['iv'], 100)

    @unittest.skipUnless(os.path.isfile(R.ROM_PATH), 'local CN ROM unavailable')
    def test_reviewed_loader_and_stat_calculator_code(self):
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(R.ROM_PATH).arm9
        regions = [
            # Form byte and initial scaled IV creation.
            (0x727A2, 0x7282E, '019c2e1a9247c2050612b1ca02b761a20f0c0ff7cec268b0bc9cbc2323412b43'),
            # Six EV fields, ids 13..18.
            (0x72880, 0x728C8, '3233058fd0f68914b722a1996931e956f135bc04ccc3d1afa736e5462ae2595c'),
            # Level-based HP override; loop repeatedly uses field 70.
            (0x728E0, 0x72914, 'd464f650d6a4f75925ce9aa1eb993eb1f743fc0f97f4c99ffdf135fe29c92661'),
            # Field 70 writes the low five IV bits only.
            (0x6E478, 0x6E48C, '1e94dc120e84cd25055fbf3daa59d80d9133ac777f73903543e4d2d6891e0769'),
            # EV reads and use with personal Speed/SpA/SpD bytes 3/4/5.
            (0x6D5FC, 0x6D644, '8453d0f451e8a5b81dec4d5b76c15a3c0f48c40693d38ad44da35f808e6d98fb'),
            (0x6D72A, 0x6D7E8, '48ee4de2af64a8c3f31280400c645e4c8109ef0e94091cedd4d5b2ddaad23b3d'),
        ]
        for start, end, expected in regions:
            with self.subTest(address=hex(0x02000000 + start)):
                self.assertEqual(hashlib.sha256(arm9[start:end]).hexdigest(), expected)


def mon(species, level, iv, abil_slot=0, form=0):
    return dict(species=species, level=level, iv=iv, abil_slot=abil_slot, form=form)


class TrainerPersonalityTests(unittest.TestCase):
    """Expected values were read from the CN ROM in the emulator (party loader, 2026-10-14)."""
    male_class = staticmethod(lambda c: 0)
    female_class = staticmethod(lambda c: 1)

    def pids(self, tid, cls, mons, class_gender, ratio=lambda s, f: 127):
        return R.trainer_personalities(tid, cls, mons, class_gender, ratio)

    def test_mod_carries_over_to_the_next_pokemon(self):
        # trainer 6 (class 2): the first record sets bit 0, the second keeps it
        self.assertEqual(self.pids(6, 2, [mon(396, 4, 10, 0x20), mon(19, 5, 10)], self.male_class),
                         [0x31B989, 0x52E689])

    def test_class_zero_shifts_the_seed(self):
        self.assertEqual(self.pids(167, 0, [mon(465, 26, 100), mon(40, 25, 100)], self.male_class),
                         [0x2F688, 0x14C88])

    def test_female_class_and_gender_nibble(self):
        self.assertEqual(self.pids(9, 50, [mon(40, 62, 150, 0x20)], self.female_class), [0xD21179])
        # trainer 165: nibble 3 -> ratio - 2 (Wobbuffet ratio 127)
        self.assertEqual(self.pids(165, 58, [mon(24, 26, 100), mon(108, 25, 100, 0x20), mon(202, 24, 232, 3)],
                                   self.male_class)[2], 0xC39C7D)

    def test_nature_gender_friendship(self):
        self.assertEqual(R.NATURES[R.nature_from_personality(0x31B989)], 'Hasty')
        self.assertEqual(R.gender_from_personality(127, 0xC39C7D), 'female')
        self.assertEqual(R.gender_from_personality(127, 0x52E689), 'male')
        self.assertEqual(R.gender_from_personality(255, 0), 'genderless')
        self.assertEqual(R.trainer_friendship([33, 218]), 0)
        self.assertEqual(R.trainer_friendship([216]), 255)

    @unittest.skipUnless(os.path.isfile(R.ROM_PATH), 'local CN ROM unavailable')
    def test_reviewed_personality_code(self):
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(R.ROM_PATH).arm9
        regions = [
            (0x72720, 0x7272C, '4a717fe5710fb25b03f9feea8586b758c0427599abec9064eac7eddd9630b70f'),  # class gender byte
            (0x72768, 0x727A2, '23c8b29a12916f7e562536c72d68603462e000dd6af2e56991e9528b29d137e0'),  # mod 0x78/0x88
            (0x7295C, 0x729A8, '69e29f58102296a06c9e4ae27c98c2c9dfacbcc3ad6dc7f75878eb5fd52cc7b8'),  # byte-1 nibbles
            (0x729A8, 0x729DA, '8af53e74828169ac7517441c4ef1f4078ca677f8887b1aabe5d04792612cc040'),  # friendship
            (0x20480, 0x204A4, 'ba864ed280f9a7a7ec345002e6c336940aeec06bf9a6e825ddc69f43e82f2b22'),  # LC RNG
            (0x6F1A0, 0x6F1EE, '677f127a7f706af1267f50ade5a8e395886bb2a691663ff84bcf19d5615ae2bd'),  # nature
            (0x6F344, 0x6F3DA, 'debe0527258f8241873ce23b2ab33261ef5600160d11ef46287083c3c85a3682'),  # gender
        ]
        for start, end, expected in regions:
            with self.subTest(address=hex(0x02000000 + start)):
                self.assertEqual(hashlib.sha256(arm9[start:end]).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
