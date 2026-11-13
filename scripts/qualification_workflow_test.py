"""Repository and campaign preflight through the public command, in owned repos."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('qualification_workflow.py')

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root/'repo'
        self.repo.mkdir()
        self.git('init', '-b', 'integration')
        (self.repo/'tracked').write_text('baseline')
        self.git('add', 'tracked')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
        self.head = self.git('rev-parse', 'HEAD').strip()
        (self.root/'receipt.json').write_text('{"status":"accepted"}')
        self.plan = {'schema':'tofa-qualification-campaign-v1', 'repository':str(self.repo),
            'branch':'integration','head':self.head,
            'author':{'name':'Fixture','email':'fixture@example.invalid'},
            'tools':[sys.executable], 'candidate':'existing-candidate',
            'accepted_evidence':[{'path':'receipt.json','sha256':hashlib.sha256((self.root/'receipt.json').read_bytes()).hexdigest()}],
            'next_action':'offline-tests','authorized_actions':['offline-tests','review','commit','ci-watch'],
            'retain_credentials':True, 'automatic_retries':0, 'human_step_seconds':600,
            'desktop_launch_authorized':False, 'release_publication_authorized':False}
        self.save()

    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.repo),*args], text=True, stderr=subprocess.PIPE)

    def save(self):
        (self.root/'campaign.json').write_text(json.dumps(self.plan))

    def call(self, ok=True):
        result = subprocess.run([sys.executable,str(SCRIPT),'preflight','--campaign',str(self.root/'campaign.json')],
            cwd=self.root,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result

    def test_explicit_checkout_author_and_receipts_allow_authorized_offline_work(self):
        config = (self.repo/'.git/config').read_bytes()
        (self.repo/'unrelated-untracked').write_text('leave me')
        result = self.call()
        self.assertTrue(result['may_continue'])
        self.assertEqual(result['next_action'], 'offline-tests')
        self.assertEqual(result['untracked_count'], 1)
        self.assertEqual((self.repo/'.git/config').read_bytes(), config)
        self.assertEqual(result['git_prefix'][:3], ['git','-C',str(self.repo.resolve())])

    def test_wrong_branch_head_dirty_tree_and_missing_tool_stop(self):
        for field, value, reason in [('branch','wrong','branch mismatch'),
                ('head','b'*40,'head mismatch'), ('tools',['/missing/tool'],'executable unavailable')]:
            old = self.plan[field]
            self.plan[field] = value
            self.save()
            self.assertIn(reason, self.call(ok=False).stderr)
            self.plan[field] = old
        self.save()
        (self.repo/'tracked').write_text('user edit')
        self.assertIn('tracked changes', self.call(ok=False).stderr)
        self.assertEqual((self.repo/'tracked').read_text(), 'user edit')

    def test_corrupt_receipt_stops_and_new_consent_is_not_inferred(self):
        self.plan['next_action'] = 'launch-desktop'
        self.plan['authorized_actions'].append('launch-desktop')
        self.save()
        self.assertFalse(self.call()['may_continue'])
        (self.root/'receipt.json').write_text('changed')
        self.assertIn('integrity mismatch', self.call(ok=False).stderr)

    @unittest.skipIf(os.name == 'nt', 'POSIX executable fixture; native workflow uses installed gh')
    def test_ci_watcher_waits_for_completion_and_never_requests_a_retry(self):
        gh = self.root/'gh'
        gh.write_text('#!'+sys.executable+"\n"+r'''import json,pathlib,sys
root=pathlib.Path(__file__).parent
assert sys.argv[1]=='api', 'read-only API required'
with (root/'api-calls').open('a') as f: f.write(sys.argv[2]+'\n')
counter=root/'counter'
n=int(counter.read_text()) if counter.exists() else 0
if '/jobs?' in sys.argv[2]:
    print(json.dumps({'total_count':1,'jobs':[{'id':42,'name':'Windows','status':'completed','conclusion':'failure','steps':[]}]}))
else:
    counter.write_text(str(n+1))
    print(json.dumps({'id':123,'head_sha':'a'*40,'run_attempt':1,'status':'in_progress' if n==0 else 'completed','conclusion':None if n==0 else 'failure'}))
''')
        gh.chmod(0o700)
        result = subprocess.run([sys.executable,str(SCRIPT),'watch-ci','--repository','fixture/repo',
            '--run-id','123','--head','a'*40,'--output',str(self.root/'ci'), '--gh',str(gh),
            '--poll-seconds','1','--seconds','5'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        first = json.loads((self.root/'ci/0000.json').read_text())
        last = json.loads((self.root/'ci/0001.json').read_text())
        self.assertEqual(first['eligible_failed_job_ids'], [])
        self.assertEqual(last['eligible_failed_job_ids'], [42])
        self.assertFalse(last['retry_performed'])
        self.assertNotIn('rerun', (self.root/'api-calls').read_text())

if __name__ == '__main__': unittest.main()
