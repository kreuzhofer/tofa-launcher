"""Preservation boundary for an explicitly verified retained Desktop bridge."""
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from capability_runtime import protected


class RetainedMCPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'home'; self.home.mkdir()
        self.skill = self.root / 'skill'; self.skill.mkdir()
        self.runtime = self.root / 'runtime'; self.runtime.mkdir()
        self.bundle = self.root / 'Owned.app'
        self.engine = self.bundle / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
        self.engine.parent.mkdir(parents=True)
        self.engine.write_text('owned engine')
        metadata = self.bundle / 'Contents/Info.plist'
        metadata.write_bytes(plistlib.dumps({'CFBundleShortVersionString': 'fixture', 'CFBundleVersion': '1'}))
        for name in ('Contents/Resources/app.asar', 'Contents/MacOS/ChatGPT',
                'Contents/Resources/plugins/openai-bundled/plugins/codex-app-tools/server.mjs'):
            path = self.bundle / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('owned fixture')
        self.engine.chmod(0o700)
        key = hashlib.sha256(str(self.engine).encode()).hexdigest()
        self.bridge = self.root / 'desktop-bridge-v2' / key / 'tofa-desktop-engine'
        self.bridge.parent.mkdir(mode=0o700, parents=True)
        self.bridge.write_text('owned verified bridge'); self.bridge.chmod(0o700)
        self.owner = self.bridge.with_name('owner.json')
        self.owner.write_text(json.dumps(dict(Version=2, LifecycleVersion=1,
            Engine=str(self.engine), SHA256=hashlib.sha256(self.bridge.read_bytes()).hexdigest())))
        self.owner.chmod(0o600)
        self.plugin = self.home / 'plugins/cache/openai-bundled/unified-computer-use/fixture/.mcp.json'
        self.plugin.parent.mkdir(parents=True)
        self.evidence = self.root / 'lifecycle.json'
        source = Path(__file__).parents[1] / 'docs/evaluation/evidence/presentation-runtime-126-127/retained-mcp-lifecycle.json'
        record = json.loads(source.read_text())
        record['app_version'] = 'fixture'; record['app_build'] = '1'
        record['source_sha256']['launcher-retained'] = hashlib.sha256(self.bridge.read_bytes()).hexdigest()
        self.evidence.write_text(json.dumps(record))
        self.write_references(self.engine)

    def write_references(self, executable):
        (self.home / 'config.toml').write_text('model = "original"\n[mcp_servers.node_repl.env]\nCODEX_CLI_PATH = ' + json.dumps(str(executable)) + '\n')
        self.plugin.write_text(json.dumps({'mcpServers': {'cua_repl': {'env': {'CODEX_CLI_PATH': str(executable), 'KEEP': 'original'}}}}))

    def policy(self):
        from retained_mcp import retained_policy
        return retained_policy(self.home, self.engine, self.bridge,
            {'version': 'fixture', 'build': '1'}, self.evidence)

    def snapshot(self, policy):
        return protected(self.home, self.skill, self.runtime, retained_mcp=policy)

    def test_only_explicit_retained_policy_accepts_the_two_executable_changes(self):
        policy = self.policy()
        before = self.snapshot(policy)
        raw = protected(self.home, self.skill, self.runtime)
        self.write_references(self.bridge)
        self.assertEqual(before, self.snapshot(policy))
        self.assertNotEqual(raw, protected(self.home, self.skill, self.runtime))
        self.write_references(self.engine)
        self.assertEqual(before, self.snapshot(policy))

    def test_unrelated_settings_skills_credentials_and_runtime_stay_protected(self):
        policy = self.policy()
        for path, original, changed in (
            (self.home / 'config.toml', (self.home / 'config.toml').read_text(),
                (self.home / 'config.toml').read_text().replace('original', 'changed')),
            (self.plugin, self.plugin.read_text(), self.plugin.read_text().replace('original', 'changed')),
            (self.home / 'auth.json', '{"token":"owned"}', '{"token":"changed"}'),
            (self.home / 'managed_config.toml', 'approval_policy="on-request"', 'approval_policy="never"'),
            (self.skill / 'SKILL.md', 'original', 'changed'),
            (self.runtime / 'runtime.json', '{}', '{"changed":true}'),
        ):
            with self.subTest(path=path.name):
                path.write_text(original); before = self.snapshot(policy)
                path.write_text(changed)
                self.assertNotEqual(before, self.snapshot(policy))
                path.write_text(original)

    def test_policy_fails_closed_after_bridge_owner_engine_or_evidence_drift(self):
        policy = self.policy()
        for path in (self.bridge, self.owner, self.engine, self.evidence):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                with self.assertRaises(ValueError): self.snapshot(policy)
                path.write_bytes(original)
        self.bridge.unlink()
        with self.assertRaises(ValueError): self.snapshot(policy)

    def test_reference_removal_or_another_executable_is_not_an_exception(self):
        policy = self.policy()
        for executable in ('/missing/engine', str(self.bridge) + '-other'):
            self.write_references(executable)
            with self.assertRaises(ValueError): self.snapshot(policy)
        self.write_references(self.engine)
        self.plugin.unlink()
        with self.assertRaises(ValueError): self.snapshot(policy)

    def test_duplicate_json_keys_cannot_hide_an_unapproved_reference(self):
        policy = self.policy()
        self.plugin.write_text('{"mcpServers":{"cua_repl":{"env":{"CODEX_CLI_PATH":"/unapproved",'
            + '"CODEX_CLI_PATH":' + json.dumps(str(self.engine)) + '}}}}')
        with self.assertRaises(ValueError): self.snapshot(policy)

    def test_desktop_calibration_records_raw_and_scoped_preservation_on_failed_attempt(self):
        from presentation_runtime_test import supplied_runtime
        self.runtime.rmdir(); supplied_runtime(self.runtime)
        self.engine.write_text('#!' + sys.executable + '\nprint("codex-cli fixture")\n')
        launcher = self.root / 'launcher'
        launcher.write_text('#!' + sys.executable + '\n' +
            'import json,pathlib,sys\nif "--version" in sys.argv: print("fixture 1")\nelse:\n' +
            ' p=pathlib.Path(' + repr(str(self.home / 'config.toml')) + ')\n' +
            ' p.write_text(p.read_text().replace(' + repr(str(self.engine)) + ', ' + repr(str(self.bridge)) + '))\n' +
            ' p=pathlib.Path(' + repr(str(self.plugin)) + ')\n' +
            ' p.write_text(p.read_text().replace(' + repr(str(self.engine)) + ', ' + repr(str(self.bridge)) + '))\n')
        launcher.chmod(0o700)
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('presentation_calibration.py')),
            '--client', 'desktop', '--codex', str(self.engine), '--launcher', str(launcher),
            '--app-bundle', str(self.bundle), '--runtime-root', str(self.runtime), '--skill', str(self.skill),
            '--codex-home', str(self.home), '--private-root', str(self.root / 'runs'),
            '--retained-mcp-bridge', str(self.bridge), '--retained-mcp-evidence', str(self.evidence)],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(result.stdout, result.stderr)
        result = json.loads(result.stdout)
        proof = json.loads((Path(result['run']) / 'qualification.json').read_text())
        self.assertEqual(proof['failure'], 'actual_client_loader_unobserved')
        self.assertTrue(proof['settings_preserved'])
        self.assertEqual(proof['preservation']['before'], proof['preservation']['after'])
        self.assertNotEqual(proof['preservation']['raw_before'], proof['preservation']['raw_after'])
        self.assertEqual(proof['retained_mcp']['bridge'], str(self.bridge))

    def test_live_evaluator_preservation_is_opt_in_and_keeps_credential_drift(self):
        from capability_evaluation import protected_settings
        from types import SimpleNamespace
        options = SimpleNamespace(codex_home=str(self.home))
        policy = self.policy()
        before = protected_settings(options, retained_mcp=policy)
        raw = protected_settings(options)
        self.write_references(self.bridge)
        self.assertEqual(before, protected_settings(options, retained_mcp=policy))
        self.assertNotEqual(raw, protected_settings(options))
        (self.home / 'auth.json').write_text('{"owned":"changed"}')
        self.assertNotEqual(before, protected_settings(options, retained_mcp=policy))

    def test_unowned_or_symlinked_bridge_and_incomplete_lifecycle_are_rejected(self):
        self.bridge.chmod(0o755)
        with self.assertRaises(ValueError): self.policy()
        self.bridge.chmod(0o700)
        original = self.owner.read_bytes()
        target = self.root / 'owner-target.json'; target.write_bytes(original); target.chmod(0o600)
        self.owner.unlink(); self.owner.symlink_to(target)
        with self.assertRaises(ValueError): self.policy()
        self.owner.unlink(); self.owner.write_bytes(original); self.owner.chmod(0o600)
        record = json.loads(self.evidence.read_text())
        record['phases']['crash']['protected_raw_equal'] = False
        self.evidence.write_text(json.dumps(record))
        with self.assertRaises(ValueError): self.policy()


if __name__ == '__main__': unittest.main()
