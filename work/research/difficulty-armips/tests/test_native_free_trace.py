"""Allocator address reuse must never count as a second root-free invocation."""
import json
from pathlib import Path
import types
import unittest
from support import RECEIPT
from native_battle import BattleTrace
from native_battle_helpers import native_free_callsite


class NativeFreeTraceTests(unittest.TestCase):
    @staticmethod
    def session():
        receipt=json.loads(RECEIPT.read_text())
        return types.SimpleNamespace(labels=receipt['build']['elf_labels'],
            payload=(Path(receipt['artifacts'])/'resident.bin').read_bytes())

    def fake_trace(self):
        session=self.session();site=native_free_callsite(session)
        r=[0]*16;r[0]=0x022c0000;r[13]=0x027e0000;r[14]=0x023dc101
        generation=[1];pending=[]
        h=types.SimpleNamespace(reg=r,frame=100,u32=lambda a:generation[0],
            read=lambda a,n:session.payload[a-0x023dc000:a-0x023dc000+n])
        session.h=h;session.returned=pending.append
        trace=BattleTrace.__new__(BattleTrace)
        trace.s=session;trace.h=h;trace.run=dict(events=[]);trace.free_scope=None;trace.free_site=site
        trace.snapshot=lambda:dict(epoch=0)
        return trace,r,generation,pending

    def test_bound_callsite_requires_unique_native_target(self):
        session=self.session();site=native_free_callsite(session)
        self.assertEqual(site['lr'],site['address']+5)
        changed=bytearray(session.payload)
        # Reject changed BLX register; no broad "some resident caller" fallback.
        offset=site['address']-0x023dc000+2;changed[offset:offset+2]=b'\x00\x00'
        session.payload=bytes(changed)
        with self.assertRaises(AssertionError):native_free_callsite(session)

    def test_later_nonresident_free_same_address_is_retained_as_allocator_reuse(self):
        t,r,g,pending=self.fake_trace()
        t.original_free()  # unrelated allocator before root wrapper
        self.assertEqual(t.run['events'],[])
        t.dg_battle_root_free();g[0]=2;r[14]=t.free_site['lr'];t.original_free()
        pending.pop()()
        t.h.frame+=1175;r[14]=0x02026505;t.original_free()
        self.assertEqual([e['name'] for e in t.run['events']],
                         ['free','original_free','free_return','allocator_reuse'])
        self.assertTrue(t.run['events'][1]['wrapper_active'])
        self.assertFalse(t.run['events'][-1]['wrapper_active'])
        # A second genuine wrapper invocation remains observable, not ignored.
        t.dg_battle_root_free();r[14]=t.free_site['lr'];t.original_free();pending.pop()()
        self.assertEqual(sum(e['name']=='original_free' for e in t.run['events']),2)

    def test_missing_duplicate_wrong_root_wrong_caller_and_outside_scope_fail(self):
        for mutation in ('missing','duplicate','root','caller','outside','code'):
            t,r,g,pending=self.fake_trace()
            if mutation!='outside':t.dg_battle_root_free()
            r[14]=t.free_site['lr']
            if mutation=='root':r[0]+=4
            if mutation=='caller':r[14]=0x02026505
            if mutation=='code':t.h.read=lambda a,n:b'\x00'*n
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):
                if mutation=='missing':pending.pop()()
                else:
                    t.original_free()
                    if mutation=='duplicate':t.original_free()
