"""#102 prototype exercised at the existing public disposable-runner boundary."""
import unittest
import json
from pathlib import Path
import struct
import subprocess
import sys

from windows_run_test import WindowsRunFixture


class AtomicOwnershipTests(WindowsRunFixture):
    def test_preservation_failure_is_not_a_completed_negative_experiment(self):
        self.change(mode='atomic_preservation_failed')
        result, report, _ = self.invoke('--suite', 'desktop-atomic-ownership', '--test-auth', 'native-session', '--timeout', '1800')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'atomic_ownership_observation_failed')
        self.assertFalse(report['atomic_ownership']['checks']['cli_defaults_unchanged'])

    def test_incomplete_native_trial_is_reported_separately_from_a_completed_negative(self):
        self.change(mode='atomic_incomplete')
        result, report, _ = self.invoke('--suite', 'desktop-atomic-ownership', '--test-auth', 'native-session', '--timeout', '1800')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'atomic_ownership_observation_failed')
        self.assertEqual(report['atomic_ownership']['stage'], 'pipe')
        self.assertTrue(report['retained'])

    def test_source_probe_binds_native_contract_signals_to_exact_archive_bytes(self):
        body = b'app.requestSingleInstanceLock(); const endpoint="codex-ipc"; if(e.code==="EADDRINUSE"){}'
        header = json.dumps({'files': {'main.js': {'size': len(body), 'offset': '0'}}}).encode()
        payload = struct.pack('<I', len(header)) + header
        payload += b'\0' * (-len(payload) % 4)
        packed = struct.pack('<I', len(payload)) + payload
        archive = self.root / 'app.asar'
        archive.write_bytes(struct.pack('<II', 4, len(packed)) + packed + body)
        process = subprocess.run([sys.executable, str(Path(__file__).with_name('windows_atomic_ownership_prototype.py')),
                                  '--inspect-asar', str(archive)], capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['sources'][0]['singleton_calls'], 1)
        self.assertEqual(result['sources'][0]['fixed_pipe_names'], 1)
        self.assertEqual(result['sources'][0]['collision_handlers'], 1)
        self.assertNotIn('const endpoint', process.stdout)

    def test_negative_atomic_observation_is_retained_and_never_promotes_support(self):
        self.change(mode='atomic_negative')
        result, report, state = self.invoke('--suite', 'desktop-atomic-ownership', '--test-auth', 'native-session', '--timeout', '1800')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'atomic_ownership_blocked')
        self.assertEqual(state['task_execution_seconds'], 600)
        self.assertEqual(report['capabilities']['desktop_ownership'], 'blocked')
        self.assertEqual(report['atomic_ownership']['trials'][0]['bytes_available'], 84)
        self.assertTrue(report['retained'])

    def test_atomic_trial_requires_its_own_evidence(self):
        result, report, _ = self.invoke('--suite', 'desktop-atomic-ownership', '--test-auth', 'native-session', '--timeout', '1800')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.get('reason'), 'atomic_ownership_evidence_missing')
        self.assertTrue(report['retained'])
        self.assertNotEqual(report['capabilities'].get('desktop_ownership'), 'verified')


if __name__ == '__main__':
    unittest.main()
