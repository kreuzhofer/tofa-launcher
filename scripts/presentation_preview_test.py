"""Human preview evidence is separate, immutable and tied to exact owned files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('presentation_preview.py')


class PreviewTests(unittest.TestCase):
    def observe(self, run, status, method=None):
        return subprocess.run([sys.executable, str(SCRIPT), str(run), '--operator', 'fixture-human',
            '--status', status, '--pptx', str(run / 'workspace/output/deck.pptx'),
            '--pdf', str(run / 'workspace/output/deck.pdf'),
            *(['--observation-method', method] if method else [])], capture_output=True, text=True, timeout=5)

    def test_computer_use_observation_is_attributed_without_claiming_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'run'; output = run / 'workspace/output'; output.mkdir(parents=True)
            (output / 'deck.pptx').write_bytes(b'owned synthetic artifact')
            (output / 'deck.pdf').write_bytes(b'owned synthetic PDF')
            result = self.observe(run, 'passed', 'computer_use')
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads((run / 'operator.json').read_text())
            self.assertEqual(evidence['observation_method'], 'computer_use')
            self.assertIn('computer-use', evidence['scope'])
            self.assertNotIn('human', evidence['scope'])

    def test_operator_record_binds_both_files_and_cannot_overwrite_an_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'run'; output = run / 'workspace/output'; output.mkdir(parents=True)
            (output / 'deck.pptx').write_bytes(b'owned synthetic artifact')
            (output / 'deck.pdf').write_bytes(b'owned synthetic PDF')
            result = self.observe(run, 'passed')
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads((run / 'operator.json').read_text())
            self.assertEqual(evidence['operator'], 'fixture-human')
            self.assertEqual(set(evidence['files']), {'deck.pptx', 'deck.pdf'})
            self.assertEqual(evidence['files']['deck.pdf'], str((output / 'deck.pdf').resolve()))
            self.assertTrue((run / 'finish.request').is_file())
            before = (run / 'operator.json').read_bytes()
            self.assertNotEqual(self.observe(run, 'failed').returncode, 0)
            self.assertEqual((run / 'operator.json').read_bytes(), before)

    def test_missing_or_symlinked_artifacts_cannot_receive_a_preview_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'run'; output = run / 'workspace/output'; output.mkdir(parents=True)
            self.assertNotEqual(self.observe(run, 'passed').returncode, 0)
            self.assertFalse((run / 'operator.json').exists())
            (output / 'deck.pptx').symlink_to(SCRIPT)
            (output / 'deck.pdf').write_bytes(b'owned synthetic PDF')
            self.assertNotEqual(self.observe(run, 'passed').returncode, 0)
            self.assertFalse((run / 'operator.json').exists())

    def test_unobserved_preview_remains_unobserved(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / 'run'; output = run / 'workspace/output'; output.mkdir(parents=True)
            (output / 'deck.pptx').write_bytes(b'owned synthetic artifact')
            (output / 'deck.pdf').write_bytes(b'owned synthetic PDF')
            self.assertEqual(self.observe(run, 'not_observed').returncode, 0)
            self.assertEqual(json.loads((run / 'operator.json').read_text())['status'], 'not_observed')


if __name__ == '__main__': unittest.main()
