"""Check Pickup layout and prevent conditional weights becoming per-check odds."""
import struct
import unittest

import pickup as P


def bl(addr, target):
    off = (target - addr - 4) & 0x7FFFFF
    return struct.pack('<HH', 0xF000 | (off >> 12), 0xF800 | ((off >> 1) & 0x7FF))


class PickupTests(unittest.TestCase):
    def fixture(self):
        base = P.GATE_ADDRESS
        data = bytearray(P.WEIGHTS_ADDRESS - base + 220)
        data[:2] = b'\x0a\x20'
        data[2:6] = bl(base + 2, P.CHANCE_FN)
        struct.pack_into('<22H', data, P.ITEMS_ADDRESS - base, *range(1, 23))
        for band in range(10):
            data[P.WEIGHTS_ADDRESS - base + band] = 30
            data[P.WEIGHTS_ADDRESS - base + 10 + band] = 70
        return base, data

    def test_item_major_layout_and_conditional_rates(self):
        base, data = self.fixture()
        table = P.parse_table(data, base)
        self.assertEqual(table['activationPercent'], 10)
        self.assertEqual(table['items'][0], dict(item=1, rates=[30] * 10))
        self.assertEqual(table['items'][1], dict(item=2, rates=[70] * 10))
        self.assertEqual(table['bands'][0], dict(min=1, max=10))
        self.assertEqual(table['bands'][-1], dict(min=91, max=100))

    def test_honey_gather_collector(self):
        # the fix honey-gather moves the gate 14 bytes on; the tables stay
        base, data = self.fixture()
        moved = P.GATE_ADDRESSES[1] - base
        data[:6] = bytes(6)
        data[moved:moved + 2] = b'\x0a\x20'
        data[moved + 2:moved + 6] = bl(P.GATE_ADDRESSES[1] + 2, P.CHANCE_FN)
        self.assertEqual(P.parse_table(data, base)['activationPercent'], 10)
        data[moved + 2:moved + 6] = bl(P.GATE_ADDRESSES[1] + 2, P.CHANCE_FN + 4)   # another function
        with self.assertRaisesRegex(ValueError, 'activation gate'):
            P.parse_table(data, base)

    def test_reject_changed_code_or_bad_table(self):
        base, data = self.fixture()
        data[0] = 11
        with self.assertRaisesRegex(ValueError, 'activation gate'):
            P.parse_table(data, base)
        base, data = self.fixture()
        data[-1] = 1
        with self.assertRaisesRegex(ValueError, 'total 100'):
            P.parse_table(data, base)


if __name__ == '__main__':
    unittest.main()
