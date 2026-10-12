"""Private evidence IO rejects malformed records and failed execution explicitly."""
import json
from pathlib import Path
import tempfile
import unittest

from capability_runtime import read_object, protected, smoke_execution


class EvidenceTests(unittest.TestCase):
    def test_json_records_must_be_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            for value in ([], None, 'text', 4):
                path.write_text(json.dumps(value))
                with self.subTest(value=value), self.assertRaises(ValueError): read_object(path)
            path.write_text('{}'); self.assertEqual(read_object(path), {})

    def test_approval_and_instruction_file_changes_affect_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / 'home'; home.mkdir()
            skill = root / 'skill'; skill.mkdir(); runtime = root / 'runtime'; runtime.mkdir()
            for name in ('managed_config.toml', 'AGENTS.md', 'AGENTS.override.md'):
                path = home / name; path.write_text('initial owned fixture')
                before = protected(home, skill, runtime)
                path.write_text('changed owned fixture')
                self.assertNotEqual(before, protected(home, skill, runtime))

    def test_artifact_existence_cannot_replace_successful_smoke_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); output = workspace / 'output'; output.mkdir()
            for name in ('deck.pptx', 'deck.pdf', 'slide.png'): (output / name).write_bytes(b'owned fake output')
            for result in ('Process exited with code 1\nOutput:\nfailed',
                    {'isError': True}, {'exit_code': 1, 'output': 'failed'}, 'Process exited with code 0\nOutput:\n'):
                with self.subTest(result=result), self.assertRaises(ValueError): smoke_execution(result, workspace)


if __name__ == '__main__': unittest.main()
