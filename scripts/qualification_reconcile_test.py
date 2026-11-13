"""Reconciliation at its public CLI; controlled assessor process, no clients."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('qualification_reconcile.py')

class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = {'source_revision':'a'*40,'hashes':{'launcher':'b'*64}}
        self.result = {'schema':'tofa-desktop-assessment-v1','target':self.target,
            'coverage_complete':False,'release_qualified':False,
            'behaviours':{'account-capabilities':{'status':'reused','reason':'unchanged behaviour','original_status':'passed'},
                          'history-continuation':{'status':'missing','reason':'not observed'}}}
        self.write('result.json', self.result)
        assessor = self.root/'assessor'
        assessor.write_text('#!'+sys.executable+'\nimport pathlib,sys\n'
            'assert sys.argv[1:4] == ["desktop-qualification","assess","--assessment"]\n'
            'print((pathlib.Path(__file__).parent/"result.json").read_text())\n')
        assessor.chmod(0o700)
        self.write('assessment.json', {'schema':'tofa-desktop-assessment-plan-v1','target':self.target})
        self.plan = {'schema':'tofa-release-reconciliation-v1', 'candidate':'synthetic-candidate',
            'target':self.target, 'assessor':self.ref('assessor'), 'assessment':self.ref('assessment.json'),
            'provenance':{'catalog':'changed', 'model':'another/main', 'plugin_cache':'changed'},
            'retained_reviews':[]}
        self.write('declaration.json', self.plan)

    def write(self, name, value):
        (self.root/name).write_text(json.dumps(value))

    def ref(self, name):
        return {'path':name,'sha256':hashlib.sha256((self.root/name).read_bytes()).hexdigest()}

    def run_cli(self, ok=True):
        result = subprocess.run([sys.executable,str(SCRIPT),'--declaration',str(self.root/'declaration.json'),
            '--output',str(self.root/'reconciliation.json')],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return json.loads((self.root/'reconciliation.json').read_text()) if ok else result

    def test_reuse_and_missing_behaviour_are_reported_without_new_gates(self):
        before = (self.root/'assessment.json').read_bytes()
        report = self.run_cli()
        self.assertEqual(report['matrix']['account-capabilities']['disposition'], 'reused')
        self.assertEqual(report['matrix']['history-continuation']['disposition'], 'targeted_evidence_needed')
        self.assertEqual(report['provenance'], self.plan['provenance'])
        self.assertFalse(report['release_qualified'])
        self.assertEqual(report['desktop_launches'], 0)
        self.assertEqual((self.root/'assessment.json').read_bytes(), before)

    def test_failed_security_contract_cannot_be_hidden_by_old_success(self):
        self.result['behaviours']['account-capabilities'] = {'status':'failed',
            'reason':'credential preservation failed','original_status':'passed'}
        self.write('result.json', self.result)
        report = self.run_cli()
        self.assertEqual(report['matrix']['account-capabilities']['disposition'], 'investigate_failed_contract')
        self.assertEqual(report['matrix']['account-capabilities']['original_status'], 'passed')
        self.assertFalse(report['release_qualified'])

    def test_tampered_plan_is_rejected_without_rewriting_it(self):
        self.write('assessment.json', {'target':'changed'})
        before = (self.root/'assessment.json').read_bytes()
        self.assertIn('integrity mismatch', self.run_cli(ok=False).stderr)
        self.assertEqual((self.root/'assessment.json').read_bytes(), before)

    def test_mismatched_candidate_is_rejected(self):
        self.plan['target'] = {'source_revision':'c'*40}
        self.write('declaration.json', self.plan)
        self.assertIn('target differs', self.run_cli(ok=False).stderr)

    def test_original_legacy_receipts_are_verified_but_do_not_fill_missing_rows(self):
        self.write('original.json', {'status':'failed'})
        self.write('review.json', {'status':'accepted_functional_result',
            'original_receipts_sha256':{'original.json':self.ref('original.json')['sha256']}})
        self.plan['retained_reviews'] = [{'review':self.ref('review.json'), 'evidence_root':'.',
            'reviewer':'maintainer','reason':'scoped functional acceptance; historical failure retained'}]
        self.write('declaration.json', self.plan)
        report = self.run_cli()
        self.assertEqual(report['retained_reviews'][0]['receipts_verified'], 1)
        self.assertFalse(report['retained_reviews'][0]['supplies_assessor_coverage'])
        self.assertEqual(report['matrix']['history-continuation']['disposition'], 'targeted_evidence_needed')
        self.assertEqual(json.loads((self.root/'original.json').read_text())['status'], 'failed')
        # A subsequent reconciliation is new evidence, never an overwritten receipt.
        self.assertIn('File exists', self.run_cli(ok=False).stderr)

    def test_corrupt_original_receipt_is_rejected(self):
        self.write('original.json', {'status':'passed'})
        self.write('review.json', {'original_receipts_sha256':{'original.json':'0'*64}})
        self.plan['retained_reviews'] = [{'review':self.ref('review.json'), 'evidence_root':'.',
            'reviewer':'maintainer','reason':'explicit review'}]
        self.write('declaration.json', self.plan)
        self.assertIn('integrity mismatch', self.run_cli(ok=False).stderr)

if __name__ == '__main__': unittest.main()
