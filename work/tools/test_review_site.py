"""Persistence and stale-review protection using synthetic text only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('text_review_server',Path(__file__).parent/'review_site/server.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class ReviewSiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.banks=self.root/'banks';(self.banks/'test').mkdir(parents=True)
        self.path=self.banks/'test/0000.json';self.path.write_text(json.dumps({'strings':[{'id':0,'zh':'source','en':'translation'}]}))
        self.state=self.root/'feedback.json'
        self.item={'ref':'test/0000#0','bank':'test/0000','id':0,'zh':'source','en':'translation','fingerprint':R.fingerprint('source','translation'),'proposal':'proposal'}
        def load(store):store.items={'test/0000#0':dict(self.item)}
        self.patch=patch.object(R.ReviewStore,'load',load);self.patch.start();self.addCleanup(self.patch.stop)
        self.store=R.ReviewStore(self.banks,self.root/'report.json',self.state)
        self.payload={'ref':'test/0000#0','fingerprint':self.item['fingerprint'],'verdict':'accept-proposal','comment':'keep meaning','suggestion':'alternative','revision':0,'proposal':'proposal'}
    def test_save_survives_restart_and_never_changes_bank(self):
        before=self.path.read_bytes();saved=self.store.save(self.payload)
        other=R.ReviewStore(self.banks,self.root/'report.json',self.state)
        self.assertEqual(other.feedback_for('test/0000#0')['comment'],'keep meaning')
        self.assertEqual(other.feedback['history'],[saved]);self.assertEqual(before,self.path.read_bytes())
    def test_changed_proposal_marks_feedback_stale(self):
        self.store.save(self.payload)
        self.store.items[self.payload['ref']]['proposal']='updated proposal'
        self.assertTrue(self.store.feedback_for(self.payload['ref'])['stale'])
        self.assertEqual(self.store.feedback['history'][0]['proposal'],'proposal')
    def test_unseen_proposal_cannot_be_accepted(self):
        self.store.items[self.payload['ref']]['proposal']='updated proposal'
        with self.assertRaises(RuntimeError): self.store.save(self.payload)
        self.assertFalse(self.state.exists())
    def test_word_diff_is_lossless_and_keeps_controls_whole(self):
        old='Remain {VAR:0103:0}{NEWLINE}<text>!'
        new='Stay {VAR:0103:0}{NEWLINE}<text>!'
        diff=R.word_diff(old,new)
        self.assertEqual(''.join(x['text'] for x in diff['before']),old)
        self.assertEqual(''.join(x['text'] for x in diff['after']),new)
        self.assertEqual([x['text'] for x in diff['before'] if x['changed']],['Remain'])
        self.assertEqual([x['text'] for x in diff['after'] if x['changed']],['Stay'])
    def test_open_filter_includes_unresolved_and_changed_reviews(self):
        ref=self.payload['ref']
        self.store.ordered=[ref]
        self.store.items[ref].update(priority=True,kind='overflow',confidence='high',audit_stale=False,search='',warnings=[],findings=[{'title':'test'}])
        query={'verdict':['open']}
        self.assertEqual(self.store.query(query)['total'],1)
        self.store.save(self.payload)
        self.assertEqual(self.store.query(query)['total'],0)
        self.store.items[ref]['proposal']='new proposal'
        self.assertEqual(self.store.query(query)['total'],1)
    def test_stale_fingerprint_rejected(self):
        with self.assertRaises(RuntimeError):self.store.save(dict(self.payload,fingerprint='old'))
        self.assertFalse(self.state.exists())
    def test_bank_changed_on_disk_rejected(self):
        self.path.write_text(json.dumps({'strings':[{'id':0,'zh':'source','en':'updated'}]}))
        with self.assertRaises(RuntimeError):self.store.save(self.payload)
    def test_concurrent_revision_rejected_without_overwrite(self):
        self.store.save(self.payload)
        with self.assertRaises(RuntimeError):self.store.save(dict(self.payload,comment='lost update'))
        self.assertEqual(self.store.feedback_for('test/0000#0')['comment'],'keep meaning')
    def test_edit_retains_history(self):
        self.store.save(self.payload);self.store.save(dict(self.payload,revision=1,comment='second'))
        self.assertEqual(len(self.store.feedback['history']),2)
    def test_validation_and_unknown_reference(self):
        for updates in ({'ref':'../../oops'},{'verdict':'apply-to-ROM'},{'comment':[]},{'suggestion':'x'*20001}):
            with self.assertRaises(ValueError):self.store.save(dict(self.payload,**updates))
    def test_cannot_accept_absent_proposal(self):
        self.store.items[self.payload['ref']]['proposal']=None
        with self.assertRaises(ValueError):self.store.save(self.payload)
    def test_failed_disk_write_does_not_claim_save(self):
        with patch.object(Path,'replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):self.store.save(self.payload)
        self.assertEqual(self.store.feedback['items'],{})

if __name__=='__main__':unittest.main()
