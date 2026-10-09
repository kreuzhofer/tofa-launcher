"""Offline checks at the release command and GitHub CLI boundaries."""
import os
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/release.py"


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tofa release ")
        self.addCleanup(self.temp.cleanup)
        self.work = pathlib.Path(self.temp.name)
        self.dist = self.work / "dist"
        self.dist.mkdir()
        self.version = "v0.1.0-rc.1"
        self.names = [f"tofa_{self.version}_{system}_{arch}" + (".exe" if system == "windows" else "")
                      for system in ("darwin", "linux", "windows") for arch in ("amd64", "arm64")]
        self.names += ["install.sh", "install.ps1", "uninstall.sh", "uninstall.ps1", "LICENSE",
                       "README.md", "THIRD_PARTY_NOTICES.txt", "LICENSE-GO.txt", "PATENTS-GO.txt",
                       "LICENSE-CODEX.txt", "NOTICE-CODEX.txt"]
        for name in self.names:
            (self.dist / name).write_text("fixture: " + name)
        (self.dist / "SHA256SUMS").write_text("".join(
            hashlib.sha256((self.dist / name).read_bytes()).hexdigest() + "  " + name + "\n"
            for name in self.names))
        self.log = self.work / "calls.jsonl"
        self.tools = self.work / "tools"
        self.tools.mkdir()
        gh = self.tools / "gh"
        gh.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
mode = os.environ.get("API_MODE", "")
if args[:1] == ["api"]:
    if args[1].endswith("/releases"):
        if mode == "api-error":
            sys.exit("API unavailable")
        print(json.dumps([[{"tag_name": "v0.1.0-rc.1", "draft": mode == "draft"}] if mode in ("existing", "draft") else []]))
    elif "/commits/" in args[1]:
        print(json.dumps({"sha": "changed" if mode == "moved-tag" else "abc123"}))
    else:
        sys.exit("Unexpected API request")
elif args[:2] == ["release", "create"]:
    pathlib.Path(os.environ["FIXTURE_DIST"]).parent.joinpath('notes.md').write_text(pathlib.Path(args[args.index('--notes-file')+1]).read_text())
    if mode == "upload-error":
        sys.exit("Upload failed; draft remains private")
elif args[:2] == ["release", "download"]:
    dest = pathlib.Path(args[args.index("--dir") + 1])
    for source in pathlib.Path(os.environ["FIXTURE_DIST"]).iterdir():
        shutil.copyfile(source, dest / source.name)
    if mode == "corrupt-download":
        (dest / "install.sh").write_text("corrupt")
    if mode == "missing-download":
        (dest / "LICENSE").unlink()
elif args[:2] != ["release", "edit"]:
    sys.exit("Unexpected gh command")
''')
        gh.chmod(0o755)
        self.env = dict(PATH=str(self.tools) + os.pathsep + os.environ["PATH"], CALL_LOG=str(self.log),
                        FIXTURE_DIST=str(self.dist), GITHUB_REF="refs/tags/" + self.version,
                        GITHUB_EVENT_NAME="push", GITHUB_REPOSITORY="owner/repo", GITHUB_SHA="abc123",
                        REQUIRED_RESULTS='{"artifacts":"success","native":"success"}')

    def command(self, *args, **env):
        return subprocess.run([sys.executable, str(SCRIPT), *args],
                              env=dict(os.environ, **env), capture_output=True,
                              text=True, timeout=30)

    def publish(self, **env):
        return self.command("publish", str(self.dist), **dict(self.env, **env))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_publishes_verified_downloads_as_a_prerelease_without_rebuilding(self):
        before = {p.name: p.read_bytes() for p in self.dist.iterdir()}
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls()
        create = next(c for c in calls if c[:2] == ["release", "create"])
        for flag in ("--draft", "--verify-tag", "--prerelease", "--latest=false"):
            self.assertIn(flag, create)
        for name in before:
            self.assertIn(str(self.dist / name), create)
        self.assertEqual(calls[-1][:3], ["release", "edit", self.version])
        self.assertIn("--draft=false", calls[-1])
        self.assertIn("--prerelease", calls[-1])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.dist.iterdir()})

    def test_only_tag_push_with_every_required_job_success_can_publish(self):
        invalid = [{"GITHUB_REF": "refs/heads/main"}, {"GITHUB_EVENT_NAME": "workflow_dispatch"},
                   {"GITHUB_EVENT_NAME": "pull_request"}, {"REQUIRED_RESULTS": "{}"}]
        for job in ("native", "artifacts"):
            for status in ("failure", "cancelled", "skipped", "in_progress", ""):
                results = {"native": "success", "artifacts": "success", job: status}
                invalid.append({"REQUIRED_RESULTS": json.dumps(results)})
        for env in invalid:
            with self.subTest(env=env):
                result = self.publish(**env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_existing_release_draft_or_api_failure_is_never_mutated(self):
        for mode in ("existing", "draft", "api-error", "moved-tag"):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.publish(API_MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.calls())
                self.assertTrue(all(call[0] == "api" for call in self.calls()))

    def test_incomplete_or_corrupt_bundle_cannot_create_a_release(self):
        originals = {p: p.read_bytes() for p in self.dist.iterdir()}
        for damage in ("missing", "corrupt", "extra", "duplicate", "missing-sum", "wrong-version"):
            with self.subTest(damage=damage):
                for p in self.dist.iterdir():
                    p.unlink()
                for p, data in originals.items():
                    p.write_bytes(data)
                self.log.unlink(missing_ok=True)
                if damage == "missing":
                    (self.dist / "LICENSE").unlink()
                elif damage == "corrupt":
                    (self.dist / "install.ps1").write_text("corrupted")
                elif damage == "extra":
                    (self.dist / "unexpected").write_text("unexpected")
                elif damage == "wrong-version":
                    old = self.dist / self.names[0]
                    old.rename(self.dist / self.names[0].replace(self.version, "v0.0.1-rc.1"))
                else:
                    sums = self.dist / "SHA256SUMS"
                    lines = sums.read_text().splitlines(keepends=True)
                    sums.write_text("".join(lines + lines[:1] if damage == "duplicate" else lines[1:]))
                result = self.publish()
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(all(c[0] == "api" for c in self.calls()))

    def test_failed_upload_or_download_never_makes_a_public_release(self):
        for mode in ("upload-error", "corrupt-download", "missing-download"):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.publish(API_MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[:2] == ["release", "edit"] for c in self.calls()))

    def test_version_accepts_stable_and_prerelease_tags_and_rejects_invalid_tags(self):
        for tag in ("v0.1.0", "v1.20.3", "v0.1.0-rc.1", "v1.20.3-beta.2", "v2.0.0-preview"):
            result = self.command("version", GITHUB_REF=f"refs/tags/{tag}")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), tag)
        for tag in ("latest", "v01.0.0", "v01.0.0-rc.1", "v1.0.0-01", "v1.0.0-", "v1.0.0-rc/1"):
            result = self.command("version", GITHUB_REF=f"refs/tags/{tag}")
            self.assertNotEqual(result.returncode, 0, tag)
            self.assertIn("Invalid prerelease version", result.stderr)
        result = self.command("version", GITHUB_REF="refs/heads/main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "v0.0.0-ci")

    def stable_bundle(self):
        old = self.version
        self.version = 'v1.2.3'
        for path in self.dist.glob('tofa_*'):
            path.rename(self.dist/path.name.replace(old, self.version))
        (self.dist/'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
            for p in sorted(self.dist.iterdir()) if p.name != 'SHA256SUMS'))
        self.env['GITHUB_REF'] = 'refs/tags/'+self.version

    def test_stable_becomes_latest_only_after_verifying_uploaded_bytes(self):
        self.stable_bundle()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        create = next(c for c in calls if c[:2] == ['release', 'create'])
        self.assertIn('--draft', create)
        self.assertIn('--latest=false', create)
        self.assertIn('--prerelease=false', create)
        self.assertEqual(calls[-1][:3], ['release', 'edit', self.version])
        self.assertIn('--latest=true', calls[-1])
        self.assertIn('--prerelease=false', calls[-1])
        notes = (self.work/'notes.md').read_text()
        self.assertIn('/releases/latest/download/install.sh', notes)
        self.assertIn('/releases/latest/download/install.ps1', notes)
        self.assertIn('sh install.sh\n', notes)

    def test_stable_failure_never_changes_latest(self):
        self.stable_bundle()
        for mode in ('upload-error', 'corrupt-download', 'missing-download', 'moved-tag'):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                result = self.publish(API_MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.calls(), 'Failure must exercise the publication boundary')
                self.assertFalse(any(c[:2] == ['release', 'edit'] for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
