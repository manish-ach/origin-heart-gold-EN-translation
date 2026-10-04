import unittest
import native_load_check as n

class NativeLoadOracleTests(unittest.TestCase):
    def test_control_argument_ffff_is_not_terminator(self):
        self.assertEqual(n.unpack_units([3,0xfffe,0x100,1,0xffff,4,0xffff]),[3,0xfffe,0x100,1,0xffff,4])

    def test_opaque_control_grammar_retains_embedded_terminator(self):
        payload=[0xfffe,0x129,2,0,0xffff,0xffff]
        self.assertEqual(len(n.unpack_units(payload)),5)
        self.assertEqual(payload.index(0xffff),4)

    def test_compression_crosses_word_boundary(self):
        values=[5,300,0,510,511]
        packed=sum(v<<(9*i) for i,v in enumerate(values))
        words=[(packed>>(15*i))&32767 for i in range(3)]
        self.assertEqual(n.unpack_units([0xf100]+words),values[:-1])

    def test_unterminated_and_truncated_fail_closed(self):
        for words in ([],[1,2],[0xf100,0],[0xfffe,3],[0xfffe,3,2,1]):
            with self.assertRaises(ValueError):n.unpack_units(words)

    def test_wrong_output_is_detected_even_same_length(self):
        expected={'expected_units':2,'expected_sha256':n.unit_hash([7,8])}
        self.assertTrue(n.verify_result(expected,[7,8]))
        self.assertFalse(n.verify_result(expected,[7,9]))
        self.assertFalse(n.verify_result(expected,[7]))

    def test_missing_duplicate_failed_or_extra_entry_is_not_coverage(self):
        expected=['a#0','a#1'];good=[{'ref':r,'status':'pass'} for r in expected]
        self.assertTrue(n.coverage(expected,good))
        for actual in (good[:1],good+[good[0]],good+[{'ref':'b#0','status':'pass'}],[good[0],{'ref':'a#1','status':'fail'}]):
            self.assertFalse(n.coverage(expected,actual))

if __name__=='__main__':unittest.main()
