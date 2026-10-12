"""Supplied-runtime loader tests at the STDIO MCP boundary."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import signal
import time
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('presentation_runtime.py')


def supplied_runtime(root):
    manifest = dict(bundleFormatVersion=2, bundleVersion='fixture-1',
                    targetPlatform='darwin', targetArch='arm64', nodeVersion='v24.19.0',
                    pythonVersion='3.12.14', artifactToolVersion='2.8.93')
    root.mkdir()
    (root / 'runtime.json').write_text(json.dumps(manifest))
    for name in ('dependencies/node/bin/node', 'dependencies/python/bin/python3',
                 'dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs',
                 'dependencies/bin/override/soffice', 'dependencies/bin/override/pdfinfo',
                 'dependencies/bin/override/pdftoppm',
                 'dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice',
                 'dependencies/native/poppler/bin/pdfinfo', 'dependencies/native/poppler/bin/pdftoppm'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture: never executed\n')
        path.chmod(0o700)
    (root / 'dependencies/node/node_modules/@oai/artifact-tool/package.json').write_text(
        json.dumps({'name': '@oai/artifact-tool', 'version': '2.8.93'}))


class LoaderTests(unittest.TestCase):
    def exchange(self, root, arguments=None):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-11-25', 'capabilities': {},
                'clientInfo': {'name': 'fixture', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {
                'name': 'load_workspace_dependencies', 'arguments': arguments or {}}},
        ]
        result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), 'mcp',
                                 '--runtime-root', str(root)],
            input=''.join(json.dumps(item) + '\n' for item in requests),
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {item['id']: item for item in map(json.loads, result.stdout.splitlines())}

    def test_actual_mcp_call_returns_only_the_supplied_runtime_and_provider_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'supplied runtime'
            supplied_runtime(root)
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            replies = self.exchange(root)
            self.assertEqual(replies[1]['result']['serverInfo']['name'], 'tofa-presentation-runtime')
            tools = replies[2]['result']['tools']
            self.assertEqual([tool['name'] for tool in tools], ['load_workspace_dependencies'])
            self.assertEqual(tools[0]['inputSchema'], {
                'type': 'object', 'properties': {}, 'additionalProperties': False})
            self.assertTrue(tools[0]['annotations']['readOnlyHint'])
            result = replies[3]['result']
            self.assertFalse(result['isError'])
            runtime = result['structuredContent']
            self.assertEqual(runtime['provider'], 'tofa_presentation_runtime')
            self.assertEqual(runtime['bundle_version'], 'fixture-1')
            self.assertEqual(runtime['artifact_tool_version'], '2.8.93')
            self.assertEqual(runtime['paths']['node'], str(root / 'dependencies/node/bin/node'))
            self.assertEqual(runtime['paths']['bin'], str(root / 'dependencies/bin/override'))
            self.assertIn('Node.js packages:', result['content'][0]['text'])
            self.assertEqual(set(runtime['native_executables']), {'soffice', 'pdfinfo', 'pdftoppm'})
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_unusable_bundle_is_an_explicit_tool_failure_without_returned_paths(self):
        for failure in ('missing', 'malformed', 'format', 'host', 'package', 'outside', 'not_executable'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve() / 'runtime'
                supplied_runtime(root)
                manifest = root / 'runtime.json'
                value = json.loads(manifest.read_text())
                if failure == 'missing': manifest.unlink()
                elif failure == 'malformed': manifest.write_text('{')
                elif failure in ('format', 'host'):
                    value['bundleFormatVersion' if failure == 'format' else 'targetPlatform'] = 1 if failure == 'format' else 'linux'
                    manifest.write_text(json.dumps(value))
                elif failure == 'package':
                    (root / 'dependencies/node/node_modules/@oai/artifact-tool/package.json').write_text('{}')
                else:
                    node = root / 'dependencies/node/bin/node'
                    if failure == 'outside':
                        node.unlink(); node.symlink_to(sys.executable)
                    else: node.chmod(0o600)
                result = self.exchange(root)[3]['result']
                self.assertTrue(result['isError'])
                self.assertNotIn('structuredContent', result)
                self.assertIn('Supplied runtime unavailable:', result['content'][0]['text'])

    def test_loader_refuses_installation_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'runtime'
            supplied_runtime(root)
            reply = self.exchange(root, {'install': True})[3]
            self.assertEqual(reply['error']['code'], -32602)

    def test_native_result_must_resolve_complete_paths_and_package_in_this_host(self):
        from presentation_runtime import inventory, instructions, from_loader_output
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'runtime'; supplied_runtime(root)
            text = instructions(inventory(root))
            result = {'content': [{'type': 'text', 'text': text}]}
            self.assertEqual(from_loader_output(result, 'codex_app')['provider'], 'codex_app')
            for output in ({'isError': True, **result}, {'success': False, **result}, {},
                    {**result, 'structuredContent': {'contract': 'supplied-presentation-runtime-v1',
                        'root': '/wrong-host', 'success': False}},
                    {'content': [{'type': 'text', 'text': text.replace('Override binaries:', 'Unavailable:')}]},
                    {'content': [{'type': 'text', 'text': text.replace('Python packages:', 'Unavailable:')}]},
                    {'content': [{'type': 'text', 'text': text.replace(str(root), '/other-host/runtime')}]},
                    {'content': [{'type': 'text', 'text': text.replace('fixture-1', 'wrong-bundle')}]},
                    {'content': [{'type': 'text', 'text': text.replace('Node.js packages: `' + str(root), 'Node.js packages: `/another-root')}]},
                    {'content': [{'type': 'text', 'text': text + '\n- Node.js executable: `/unrelated/node`'}]}):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    from_loader_output(output, 'codex_app')
            (root / 'dependencies/node/node_modules/@oai/artifact-tool/package.json').write_text('{}')
            with self.assertRaises(ValueError): from_loader_output(result, 'codex_app')


class DesktopCalibrationTests(unittest.TestCase):
    def test_desktop_refuses_standalone_engine_substitution_before_starting_any_provider(self):
        result = subprocess.run([sys.executable, str(SCRIPT.with_name('presentation_calibration.py')),
            '--client', 'desktop', '--codex', sys.executable, '--launcher', sys.executable,
            '--app-bundle', '/nonexistent/Fixture.app', '--runtime-root', '/missing/runtime',
            '--skill', '/missing/skill', '--private-root', '/missing/private', '--check'],
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('native_bundled_engine_required', result.stderr)


@unittest.skipUnless(os.environ.get('TOFA_TEST_CODEX') and sys.platform == 'darwin', 'opt-in installed CLI')
class InstalledLoaderTests(unittest.TestCase):
    def test_cancelled_launch_retains_failed_qualification_and_preservation_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); runtime = root / 'runtime'; supplied_runtime(runtime)
            home = root / 'home'; home.mkdir()
            (home / 'config.toml').write_text('# owned settings\n')
            skill = root / 'skill'; skill.mkdir(); (skill / 'SKILL.md').write_text('owned fixture')
            marker = root / 'started'
            codex = root / 'codex'
            codex.write_text('#!' + sys.executable + '\nimport pathlib,sys,time\n'
                'if "--version" in sys.argv: print("codex-cli 0.162.1")\n'
                'elif "mcp" in sys.argv: print("[]")\n'
                'else:\n pathlib.Path(' + repr(str(marker)) + ').touch()\n time.sleep(180)\n')
            codex.chmod(0o700)
            command = [sys.executable, str(SCRIPT.with_name('presentation_calibration.py')),
                '--client', 'cli', '--codex', str(codex), '--launcher', os.environ['TOFA_PRESENTATION_LAUNCHER'],
                '--runtime-root', str(runtime), '--codex-home', str(home), '--skill', str(skill),
                '--private-root', str(root / 'runs')]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.05)
                self.assertTrue(marker.exists(), 'fixture client never started')
                process.send_signal(signal.SIGINT)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 1, stderr)
                proofs = list((root / 'runs').glob('*/qualification.json'))
                self.assertEqual(len(proofs), 1, stderr)
                proof = json.loads(proofs[0].read_text())
                self.assertEqual(proof['status'], 'infra_blocked')
                self.assertEqual(proof['failure'], 'operator_cancelled')
                self.assertTrue(proof['settings_preserved'])
                self.assertEqual(proof['preservation']['before'], proof['preservation']['after'])
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)

    def test_installed_cli_invokes_loader_and_builds_supplied_runtime_artifacts(self):
        root = Path(os.environ['TOFA_PRESENTATION_CALIBRATION_ROOT'])
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        command = [sys.executable, str(SCRIPT.with_name('presentation_calibration.py')),
                   '--client', 'cli', '--codex', os.environ['TOFA_TEST_CODEX'],
                   '--launcher', os.environ['TOFA_PRESENTATION_LAUNCHER'],
                   '--runtime-root', os.environ['TOFA_PRESENTATION_RUNTIME'],
                   '--skill', os.environ['TOFA_PRESENTATION_SKILL'], '--private-root', str(root)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=200)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence['status'], 'qualified')
        self.assertFalse(evidence['paid_inference'])
        self.assertEqual(evidence['loader_name'], 'mcp__tofa_presentation_runtime__load_workspace_dependencies')
        self.assertTrue(evidence['settings_preserved'])
        self.assertEqual(set(evidence['artifacts']), {'deck.pptx', 'deck.pdf', 'slide.png'})
        from capability_runtime import qualify
        from capability_evaluation import version
        proof = Path(evidence['run']) / 'qualification.json'
        identity = version(Path(os.environ['TOFA_TEST_CODEX']))
        home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).resolve()
        skill = Path(os.environ['TOFA_PRESENTATION_SKILL'])
        binding = qualify(proof, client='cli', client_identity=identity, home=home, skill=skill)
        self.assertEqual(binding['runtime']['root'], os.environ['TOFA_PRESENTATION_RUNTIME'])
        from capability_observer_test import BoundaryTests
        boundary = BoundaryTests()
        request = json.loads((proof.parent / 'model-request-2.json').read_text())
        for failed in (False, True):
            with self.subTest(live_loader_failed=failed), boundary.boundary(case='03', qualification=binding) as (observer, seen):
                body = json.loads(json.dumps(request))
                if failed:
                    next(item for item in body['input'] if item.get('type') == 'function_call_output')['output'] = {'isError': True}
                boundary.post(observer, '/responses', body, 'client-token', 400 if failed else 200)
                self.assertEqual(len(seen), 0 if failed else 1)
                if failed: self.assertEqual(observer.reason, 'presentation_runtime_result_invalid')
        data = json.loads(proof.read_text())
        self.assertIn('observed_versions', data)
        # Tamper only disposable copies. Actual attempt evidence is immutable.
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory).resolve() / 'evidence'
            shutil.copytree(proof.parent, copied, symlinks=True)
            copied_proof = copied / 'qualification.json'
            data['run'] = str(copied)
            for key, replacement in (('client', 'desktop'), ('client_identity', {}),
                                     ('observed_versions', {}), ('harness', {}),
                                     ('thread_identity', None), ('preservation', None), ('artifacts', None)):
                with self.subTest(tampered=key):
                    copied_proof.write_text(json.dumps(dict(data, **{key: replacement})))
                    with self.assertRaises(ValueError):
                        qualify(copied_proof, client='cli', client_identity=identity, home=home, skill=skill)
            copied_proof.write_text(json.dumps(data))
            (copied / 'loader-result.json').write_text('{}')
            with self.assertRaises(ValueError):
                qualify(copied_proof, client='cli', client_identity=identity, home=home, skill=skill)
        # Derivative fixtures exercise drift without changing ordinary settings
        # or claiming another actual-client/native-UI qualification.
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory).resolve()
            copied = temporary / 'evidence'; shutil.copytree(proof.parent, copied, symlinks=True)
            owned_home = temporary / 'home'; owned_home.mkdir()
            managed = owned_home / 'managed_config.toml'; managed.write_text('# owned policy fixture\n')
            from capability_runtime import protected
            fixture = json.loads(proof.read_text()); fixture['run'] = str(copied)
            snapshot = protected(owned_home, skill, Path(fixture['runtime']['root']))
            fixture['preservation'] = {'before': snapshot, 'after': snapshot}
            copied_proof = copied / 'qualification.json'; copied_proof.write_text(json.dumps(fixture))
            final = copied / 'final.txt'; final.write_text(final.read_text().replace(str(proof.parent), str(copied)))
            owned_binding = qualify(copied_proof, client='cli', client_identity=identity, home=owned_home, skill=skill)
            with boundary.boundary(case='03', qualification=owned_binding) as (observer, seen):
                managed.write_text('# changed owned policy fixture\n')
                boundary.post(observer, '/responses', request, 'client-token', 400)
                self.assertEqual(observer.reason, 'presentation_runtime_environment_drift')
                self.assertEqual(seen, [])
            managed.write_text('# owned policy fixture\n')
            for name in ('workspace/build/finalization.json', 'model-request-1.json'):
                original = (copied / name).read_bytes()
                (copied / name).write_text('[]')
                with self.subTest(malformed=name), self.assertRaises(ValueError):
                    qualify(copied_proof, client='cli', client_identity=identity, home=owned_home, skill=skill)
                (copied / name).write_bytes(original)
            (copied / 'smoke-result.json').write_text(json.dumps('Process exited with code 1\nOutput:\nfailed'))
            with self.assertRaisesRegex(ValueError, 'presentation_smoke_failed'):
                qualify(copied_proof, client='cli', client_identity=identity, home=owned_home, skill=skill)


if __name__ == '__main__':
    unittest.main()
