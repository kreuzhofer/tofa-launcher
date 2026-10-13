"""Private evidence IO rejects malformed records and failed execution explicitly."""
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

from capability_runtime import desktop_identity, read_object, protected, smoke_execution


class EvidenceTests(unittest.TestCase):
    def test_native_metadata_rejects_missing_or_invalid_identity_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'Owned.app'
            metadata = bundle / 'Contents/Info.plist'
            metadata.parent.mkdir(parents=True)
            engine = bundle / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
            invalid = ({}, [], {'CFBundleShortVersionString': '1'},
                {'CFBundleShortVersionString': '1', 'CFBundleVersion': 4},
                {'CFBundleShortVersionString': '', 'CFBundleVersion': '4'},
                {'CFBundleShortVersionString': False, 'CFBundleVersion': '4'})
            for value in invalid:
                metadata.write_bytes(plistlib.dumps(value))
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'invalid_native_desktop_metadata'):
                    desktop_identity(bundle, engine)
            for contents in (b'not a plist', b'<?xml version="1.0"?><plist><dict>'):
                metadata.write_bytes(contents)
                with self.subTest(contents=contents), self.assertRaisesRegex(ValueError, 'invalid_native_desktop_metadata'):
                    desktop_identity(bundle, engine)

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
