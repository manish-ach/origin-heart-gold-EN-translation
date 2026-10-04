"""Synthetic mutations for the independent binary-message validator."""
import struct
import unittest

from text_binary_check import inspect_bank, inspect_narc


def bank(records, seed=123):
    table = bytearray()
    payload = bytearray()
    for index, units in enumerate(records, 1):
        key = seed * 0x2FD * index & 65535
        mask = key | key << 16
        table.extend(struct.pack('<II', (4+len(records)*8+len(payload)) ^ mask, len(units) ^ mask))
        wordkey = 0x91BD3 * index & 65535
        for word in units:
            payload.extend(struct.pack('<H', word ^ wordkey))
            wordkey = wordkey + 0x493D & 65535
    return struct.pack('<HH', len(records), seed) + table + payload


def narc(members):
    offsets = bytearray()
    payload = bytearray()
    for member in members:
        offsets.extend(struct.pack('<II', len(payload), len(payload)+len(member)))
        payload.extend(member)
    sections = b'BTAF'+struct.pack('<IHH',12+len(offsets),len(members),0)+offsets
    sections += b'BTNF'+struct.pack('<I',16)+b'\x04\0\0\0\0\0\x01\0'
    sections += b'GMIF'+struct.pack('<I',8+len(payload))+payload
    return struct.pack('<4sHHIHH',b'NARC',0xFFFE,0x100,16+len(sections),16,3)+sections


def packed(symbols):
    # Independent synthetic encoder uses an explicit string of little-endian bits.
    bits = ''.join(''.join(str((v>>bit)&1) for bit in range(9)) for v in symbols)
    bits += '1' * ((-len(bits)) % 15)
    return [0xF100] + [sum(int(bit)<<j for j,bit in enumerate(bits[i:i+15])) for i in range(0,len(bits),15)] + [0xFFFF]


class BinaryBankTests(unittest.TestCase):
    def assertBad(self, units, code):
        result = inspect_bank(bank([units]))
        self.assertEqual(result['status'],'failed')
        self.assertIn(code,[e['code'] for e in result['errors']])

    def test_empty_inventory_and_empty_string(self):
        self.assertEqual(inspect_bank(bank([]))['status'],'passed')
        self.assertEqual(inspect_bank(bank([[0xFFFF]]))['status'],'passed')

    def test_commands_keep_argument_terminators_as_data(self):
        result=inspect_bank(bank([[5,0xFFFE,0x100,2,0xFFFF,0,0xFFFF,0xFFFF]]))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['records'][0]['commands'][0]['args'],[65535,0])
        self.assertEqual(result['records'][0]['padding'],1)

    def test_missing_terminator(self):
        self.assertBad([1,2], 'missing_terminator')

    def test_zero_length_record(self):
        self.assertBad([], 'empty_record')

    def test_command_header_truncation(self):
        for units in ([0xFFFE],[0xFFFE,1]):
            self.assertBad(units,'truncated_command_header')

    def test_command_argument_overrun(self):
        self.assertBad([0xFFFE,0x100,65535,0xFFFF],'command_arguments_overrun')

    def test_command_consumes_only_terminator(self):
        self.assertBad([0xFFFE,0x100,1,0xFFFF],'missing_terminator')

    def test_trailing_payload(self):
        self.assertBad([0xFFFF,1],'trailing_message_payload')

    def test_interior_compression(self):
        self.assertBad([1,0xF100,0xFFFF],'misplaced_compression_header')

    def test_compression_every_bit_alignment_and_boundaries(self):
        for length in range(36):
            result=inspect_bank(bank([packed([0,510]*length)]))
            self.assertEqual(result['status'],'passed',length)
            self.assertEqual(result['records'][0]['decoded_units'],length*2)

    def test_unterminated_compression(self):
        self.assertBad([0xF100,0,0],'unterminated_compression')

    def test_compressed_high_bit(self):
        self.assertBad([0xF100,0x8001,0xFFFF],'compressed_high_bit')

    def test_compressed_hidden_payload(self):
        self.assertBad([0xF100,0x1FF,0xFFFF],'compressed_trailing_payload')
        self.assertBad([0xF100,0x7FFF,1,0xFFFF],'compressed_trailing_payload')

    def test_compressed_storage_terminator(self):
        self.assertBad([0xF100,0x7FFF],'missing_storage_terminator')

    def test_truncated_inventory_and_payload(self):
        for data in (b'',b'\0',b'\xff\xff\0\0',bank([[1,0xFFFF]])[:-1]):
            self.assertEqual(inspect_bank(data)['status'],'failed')

    def test_overlapping_offset_or_oversize_record(self):
        for offset,length in ((4,1),(13,1),(12,0xFFFFFFFF),(0xFFFFFFFF,1)):
            data=struct.pack('<HHII',1,0,offset,length)+b'\0'*4
            self.assertEqual(inspect_bank(data)['status'],'failed')

    def test_uninterpreted_trailer_not_pass(self):
        self.assertEqual(inspect_bank(bank([[0xFFFF]])+b'x')['status'],'incomplete')

    def test_full_u16_record_inventory(self):
        result=inspect_bank(bank([[0xFFFF]]*65535))
        self.assertEqual(result['status'],'passed')
        self.assertEqual(len(result['records']),65535)


class BinaryNarcTests(unittest.TestCase):
    def test_bounded_member_copies(self):
        result=inspect_narc(narc([b'abc',b'',b'defg']))
        self.assertEqual(result['status'],'passed')
        self.assertEqual([m['data'] for m in result['members']],[b'abc',b'',b'defg'])

    def test_truncations(self):
        data=narc([b'abc'])
        for length in range(len(data)):
            self.assertEqual(inspect_narc(data[:length])['status'],'failed',length)

    def test_header_and_section_mutations(self):
        for offset,value in ((4,0),(7,0),(12,0),(14,2),(16,0),(20,0)):
            data=bytearray(narc([b'abc']))
            data[offset]=value
            self.assertEqual(inspect_narc(bytes(data))['status'],'failed',offset)

    def test_fat_inventory_mutation(self):
        data=bytearray(narc([b'abc']))
        struct.pack_into('<H',data,24,65535)
        self.assertEqual(inspect_narc(bytes(data))['status'],'failed')

    def test_member_overlap_and_overrun(self):
        for start,stop in ((1,5),(2,1),(3,99999)):
            data=bytearray(narc([b'abc',b'def']))
            struct.pack_into('<II',data,36,start,stop)
            self.assertEqual(inspect_narc(bytes(data))['status'],'failed')


if __name__ == '__main__':
    unittest.main()
