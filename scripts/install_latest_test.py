"""Public shell installer checks with a controlled HTTPS transport boundary."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class LatestInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tofa latest ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        self.log = self.root / 'requests.jsonl'
        self.install = self.root / 'install'
        self.install.mkdir()
        (self.install / '.tofa-install').write_text('tofa-install-v1\n')
        (self.install / 'bin').mkdir()
        (self.install / 'bin/tofa').write_text('original executable')
        (self.install / 'unrelated').write_text('preserve me')
        self.config = self.root / 'config/tofa'
        self.config.mkdir(parents=True)
        (self.config / 'config.yml').write_bytes(b'version: 1\nproject_id: synthetic-project\nmodel: synthetic-model\n')
        self.before = self.snapshot()
        shim = self.tools / 'curl'
        shim.write_text('#!' + sys.executable + '\n' + '''
import hashlib, json, os, pathlib, sys
args = sys.argv[1:]
url = next(a for a in args if a.startswith('https://'))
with open(os.environ['REQUEST_LOG'], 'a') as f: f.write(json.dumps(url)+'\\n')
mode = os.environ.get('FIXTURE_MODE', '')
repo = 'https://github.com/kreuzhofer/tofa-launcher'
if url.endswith('/latest'):
    if mode == 'unavailable': sys.exit(22)
    tag = os.environ.get('RESOLVED_TAG', 'v1.2.3')
    if 'api.github.com' in url:
        print(json.dumps({'tag_name': tag, 'prerelease': '-' in tag, 'draft': False}))
    else:
        print(os.environ.get('RESOLVED_URL', repo+'/releases/tag/'+tag), end='')
else:
    tag = os.environ.get('EXPECTED_TAG', 'v1.2.3')
    expected = repo+'/releases/download/'+tag+'/'
    if not url.startswith(expected): sys.exit('wrong pinned download URL')
    data = b'#!/bin/sh\\necho fixture-installed\\n'
    name = 'tofa_'+tag+'_'+os.environ['FIXTURE_PLATFORM']+'_'+os.environ['FIXTURE_ARCH']
    asset = url[len(expected):]
    if mode == 'download-failure': sys.exit(22)
    if asset == 'SHA256SUMS':
        digest = '0'*64 if mode == 'checksum-mismatch' else hashlib.sha256(data).hexdigest()
        data = (digest+'  '+name+'\\n').encode()
    elif asset != name: sys.exit('unexpected asset')
    pathlib.Path(args[args.index('-o')+1]).write_bytes(data)
''')
        shim.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.tools)+os.pathsep+os.environ['PATH'],
                        HOME=str(self.root), XDG_CONFIG_HOME=str(self.root/'config'),
                        TOFA_INSTALL_DIR=str(self.install), REQUEST_LOG=str(self.log),
                        FIXTURE_PLATFORM=platform.system().lower(),
                        FIXTURE_ARCH={'arm64':'arm64','aarch64':'arm64','x86_64':'amd64'}[platform.machine()])
        self.env.pop('TOFA_RELEASE_BASE_URL', None)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for directory in (self.install, self.config)
                for p in directory.rglob('*') if p.is_file()}

    def run_installer(self, *args, **env):
        return subprocess.run(['sh', str(ROOT/'scripts/install.sh'), '--no-modify-path', *args],
                              env=dict(self.env, **env), text=True, capture_output=True, timeout=15)

    def requests(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_latest_rejects_prerelease_metadata_without_changing_installation(self):
        result = self.run_installer(RESOLVED_TAG='v1.2.3-rc.1', EXPECTED_TAG='v1.2.3-rc.1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(len(self.requests()), 1)

    def test_omitted_version_resolves_once_and_pins_both_downloads(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Installed tofa v1.2.3', result.stdout)
        self.assertEqual((self.install/'bin/tofa').read_bytes(), b'#!/bin/sh\necho fixture-installed\n')
        requests = self.requests()
        self.assertEqual(sum(url.endswith('/latest') for url in requests), 1)
        self.assertEqual(len(requests), 3)
        self.assertTrue(all('/releases/download/v1.2.3/' in url for url in requests[1:]))
        self.assertEqual((self.install/'unrelated').read_text(), 'preserve me')

    def test_explicit_prerelease_bypasses_latest_resolution(self):
        result = self.run_installer('--version', 'v1.2.3-rc.1', EXPECTED_TAG='v1.2.3-rc.1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all('/download/v1.2.3-rc.1/' in url for url in self.requests()))

    def test_invalid_resolution_preserves_existing_installation(self):
        for url in ('', 'https://other.invalid/releases/tag/v1.2.3',
                    'http://github.com/kreuzhofer/tofa-launcher/releases/tag/v1.2.3',
                    'https://github.com/kreuzhofer/tofa-launcher/releases/tag/nested/v1.2.3'):
            with self.subTest(url=url):
                self.log.unlink(missing_ok=True)
                result = self.run_installer(RESOLVED_URL=url)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('invalid latest stable release', result.stderr)
                self.assertEqual(len(self.requests()), 1)
                self.assertEqual(self.snapshot(), self.before)
        for tag in ('v01.2.3', 'v1.2', '..', 'v1.2.3?download=1', 'v1.2.3\nv4.5.6'):
            with self.subTest(tag=tag):
                self.log.unlink(missing_ok=True)
                result = self.run_installer(RESOLVED_TAG=tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.requests()), 1)
                self.assertEqual(self.snapshot(), self.before)

    def test_resolution_download_and_checksum_failures_preserve_installation(self):
        for mode in ('unavailable', 'download-failure', 'checksum-mismatch'):
            with self.subTest(mode=mode):
                result = self.run_installer(FIXTURE_MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.snapshot(), self.before)
                if mode == 'unavailable':
                    self.assertIn('could not resolve latest stable release', result.stderr)


if __name__ == '__main__':
    unittest.main()
