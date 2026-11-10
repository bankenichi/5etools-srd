import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from item_proof_inputs import require_inputs


class ItemProofInputTest(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.pdf=self.root/'official.pdf';self.pdf.write_bytes(b'official source')
        self.files=['items.json','items-base.json','magicvariants.json','decks.json']
        for name in self.files:(self.root/name).write_text('{}\n',encoding='utf8')
        self.proof={'passed':True,'pdf_sha256':hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
                    'input_sha256':{name:hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in self.files}}

    def check(self,proof):require_inputs(proof,self.pdf,self.root,self.files,'test-item')

    def test_complete_current_proof_passes(self):self.check(self.proof)

    def test_missing_or_extra_input_hash_cannot_hide_stale_data(self):
        for name in self.files:
            with self.subTest(name=name):
                proof=copy.deepcopy(self.proof);del proof['input_sha256'][name]
                (self.root/name).write_text('{"changed":true}\n',encoding='utf8')
                with self.assertRaisesRegex(ValueError,'input inventory'):self.check(proof)
                (self.root/name).write_text('{}\n',encoding='utf8')
        proof=copy.deepcopy(self.proof);proof['input_sha256']['extra.json']='invented'
        with self.assertRaisesRegex(ValueError,'input inventory'):self.check(proof)
        for bad in (None,{},[],self.files):
            with self.subTest(inputs=bad):
                proof=copy.deepcopy(self.proof);proof['input_sha256']=bad
                with self.assertRaisesRegex(ValueError,'input inventory'):self.check(proof)

    def test_every_input_and_pdf_change_rejects_proof(self):
        for name in self.files:
            with self.subTest(name=name):
                (self.root/name).write_text('{"changed":true}\n',encoding='utf8')
                with self.assertRaisesRegex(ValueError,'Stale.*'+name):self.check(self.proof)
                (self.root/name).write_text('{}\n',encoding='utf8')
        self.pdf.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError,'PDF source proof'):self.check(self.proof)

    def test_failed_or_truthy_nonboolean_receipt_is_rejected(self):
        for value in (False,1,'true',None):
            with self.subTest(passed=value):
                proof=copy.deepcopy(self.proof);proof['passed']=value
                with self.assertRaisesRegex(ValueError,'Failed'):self.check(proof)


if __name__=='__main__':unittest.main()
