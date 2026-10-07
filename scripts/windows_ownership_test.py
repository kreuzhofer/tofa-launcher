"""Executable discovery/refusal contract; inventory is the OS boundary snapshot."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class OwnershipContractTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {
            'packages': [{'name': 'OpenAI.Codex_26.930.6422.0_arm64__2p2nqsd0c76g0',
                          'status': 'Ok', 'architecture': 'Arm64',
                          'root': r'C:\Program Files\WindowsApps\OpenAI.Codex_26.930.6422.0_arm64__2p2nqsd0c76g0',
                          'app': r'C:\Program Files\WindowsApps\OpenAI.Codex_26.930.6422.0_arm64__2p2nqsd0c76g0\app\ChatGPT.exe',
                          'engine_sha256': 'a' * 64}],
            'engines': [{'path': r'C:\Users\tofa-test\AppData\Local\OpenAI\Codex\bin\123\codex.exe',
                         'sha256': 'a' * 64, 'architecture': 'ARM64'}],
            'paths_safe': True, 'process_inventory_complete': True, 'incumbents': [],
        }

    def invoke(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'inventory.json'
            path.write_text(json.dumps(self.inventory))
            process = subprocess.run([sys.executable, str(Path(__file__).with_name('windows_ownership_contract.py')),
                                      '--inventory', str(path)], capture_output=True, text=True, timeout=5)
            return process.returncode, json.loads(process.stdout)

    def test_matching_engine_does_not_grant_ownership_from_a_snapshot(self):
        code, result = self.invoke()
        self.assertEqual((code, result['reason']), (42, 'ownership_unproven'))
        self.assertFalse(result['may_launch'])

    def test_ordinary_instance_is_refused_even_with_different_path_casing(self):
        self.inventory['incumbents'] = [{'pid': 123, 'path': self.inventory['packages'][0]['app'].upper()}]
        self.assertEqual(self.invoke(), (41, {'may_launch': False, 'reason': 'native_client_busy'}))

    def test_multiple_registrations_are_not_resolved_by_highest_version(self):
        second = copy.deepcopy(self.inventory['packages'][0])
        second['name'] = second['name'].replace('26.930', '99.999')
        self.inventory['packages'].append(second)
        self.assertEqual(self.invoke()[1]['reason'], 'package_ambiguous')

    def test_incomplete_update_is_refused(self):
        self.inventory['packages'][0]['status'] = 'Modified'
        self.assertEqual(self.invoke()[1]['reason'], 'package_unhealthy')

    def test_standalone_cli_is_not_a_matching_relocated_engine(self):
        self.inventory['engines'][0]['path'] = r'C:\Users\tofa-test\bin\codex.exe'
        self.assertEqual(self.invoke()[1]['reason'], 'engine_mismatch')

    def test_engine_integrity_architecture_and_ambiguity_fail_closed(self):
        original = copy.deepcopy(self.inventory)
        for field, value in [('sha256', 'b' * 64), ('architecture', 'AMD64')]:
            self.inventory = copy.deepcopy(original)
            self.inventory['engines'][0][field] = value
            self.assertEqual(self.invoke()[1]['reason'], 'engine_mismatch')
        self.inventory = original
        self.inventory['engines'] *= 2
        self.assertEqual(self.invoke()[1]['reason'], 'engine_mismatch')

    def test_reparse_or_incomplete_process_inventory_never_grants_ownership(self):
        for key in ('paths_safe', 'process_inventory_complete'):
            with self.subTest(key=key):
                self.inventory[key] = False
                self.assertEqual(self.invoke()[1]['reason'], 'unsafe_or_incomplete_inventory')
                self.inventory[key] = True


if __name__ == '__main__':
    unittest.main()
