"""Public non-launch kit commands, using only owned synthetic files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("qualification_kit.py")

class KitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRIPT.parent)
        self.addCleanup(self.tmp.cleanup)
        self.kit = Path(self.tmp.name) / "kit"
        self.kit.mkdir()
        (self.kit / "source/scripts").mkdir(parents=True)
        (self.kit / "tofa").write_text("synthetic candidate")
        (self.kit / "model-services.json").write_text("{}")
        (self.kit / "source/scripts/dependency.py").write_text("VALUE = 1")
        (self.kit / "source/scripts/desktop_qualification.py").write_text("import dependency\n")
        self.plan = {"schema":"tofa-qualification-kit-v1", "source_revision":"a"*40,
            "launcher":"tofa", "collector":"source/scripts/desktop_qualification.py",
            "model_services":"model-services.json", "app_bundle":"/Applications/ChatGPT.app",
            "runtime_root":"/unused/supplied-runtime", "durable_root":str(self.kit),
            "run_root":"/tmp/tofa-presentation-validation", "case":"clean-exit",
            "model":"synthetic/main", "guardian":"synthetic/reviewer",
            "seconds":600, "requests":8, "output_tokens":4096,
            "prompt":"Reply exactly: tofa-clean-exit-ok. Do not use tools or create files.",
            "automatic_retries":0, "retain_credentials":True}
        self.pin()

    def pin(self):
        self.plan["files"] = {str(p.relative_to(self.kit)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.kit.rglob("*") if p.is_file() and p.name != "kit.json"}
        (self.kit / "kit.json").write_text(json.dumps(self.plan))

    def run_cli(self, action, *args, ok=True):
        result = subprocess.run([sys.executable,str(SCRIPT),action,"--kit",str(self.kit),*args],
                                text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_tampered_candidate_stops_before_collector_import(self):
        (self.kit/"tofa").write_text("changed")
        result = self.run_cli("check", ok=False)
        self.assertIn("pinned kit hash mismatch", result.stderr)

    def test_missing_dependency_is_reported_before_handoff(self):
        (self.kit/"source/scripts/dependency.py").write_text("import missing_fixture_dependency")
        self.pin()
        self.assertIn("collector_import_failed", self.run_cli("check", ok=False).stderr)

    def test_unbound_dependency_and_symlink_are_rejected(self):
        (self.kit/"source/scripts/surprise.py").write_text("pass")
        self.assertIn("unbound collector dependency", self.run_cli("check", ok=False).stderr)
        (self.kit/"source/scripts/surprise.py").unlink()
        (self.kit/"tofa").unlink()
        (self.kit/"tofa").symlink_to(self.kit/"model-services.json")
        self.assertIn("regular files", self.run_cli("check", ok=False).stderr)

    def test_status_never_resumes_consumed_attempt(self):
        root = Path("/tmp/tofa-presentation-validation/runs")
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            run = Path(tmp)
            (run/"kit-binding.json").write_text(json.dumps({"kit_sha256":hashlib.sha256((self.kit/"kit.json").read_bytes()).hexdigest()}))
            (run/"finish.json").write_text('{"status":"failed"}')
            before = (run/"finish.json").read_bytes()
            result = json.loads(self.run_cli("status", "--run", str(run)).stdout)
            self.assertEqual(result["status"], "consumed")
            self.assertEqual(result["next_action"], "review_retained_evidence")
            self.assertEqual((run/"finish.json").read_bytes(), before)
            self.run_cli("prepare", "--run", str(run), ok=False)

    def test_prepare_retains_declaration_and_passes_pinned_values_without_launch(self):
        app = self.kit / "App/Contents"
        app.mkdir(parents=True)
        (app/"Info.plist").write_text("fixture")
        runtime = self.kit / "runtime"
        runtime.mkdir()
        (runtime/"runtime.json").write_text("{}")
        self.plan.update(app_bundle=str(app.parent), runtime_root=str(runtime))
        collector = self.kit/"source/scripts/desktop_qualification.py"
        collector.write_text("""import dependency
if __name__ == '__main__':
    import json, pathlib, sys, tempfile
    args = sys.argv[1:]
    assert args[:2] == ['prepare', '--defer-snapshot']
    for key, expected in {'--seconds':'600', '--requests':'8', '--output-tokens':'4096',
                          '--source-revision':'a'*40, '--model':'synthetic/main'}.items():
        assert args[args.index(key)+1] == expected
    parent = pathlib.Path('/tmp/tofa-presentation-validation/runs')
    parent.mkdir(parents=True, exist_ok=True)
    run = pathlib.Path(tempfile.mkdtemp(prefix='kit-test.', dir=parent))
    (run/'workspace').mkdir()
    print(json.dumps({'run':str(run),'desktop_launched':False,'status':'workspace_setup_required'}))
""")
        self.pin()
        result = json.loads(self.run_cli("prepare").stdout)
        self.addCleanup(shutil.rmtree, result["run"], True)
        self.assertFalse(result["desktop_launched"])
        self.assertEqual((Path(result["durable_preparation"])/"kit.json").read_bytes(), (self.kit/"kit.json").read_bytes())
        self.assertEqual(json.loads(self.run_cli("status", "--run", result["run"]).stdout)["status"], "prepared")

    def test_restore_after_tmp_deletion_verifies_bytes_and_never_launches(self):
        first = json.loads(self.run_cli("restore").stdout)
        restored = Path(first["kit"])
        self.addCleanup(shutil.rmtree, restored, True)
        self.assertEqual((restored/"tofa").read_bytes(), (self.kit/"tofa").read_bytes())
        self.assertFalse(first["desktop_launched"])
        shutil.rmtree(restored)
        second = json.loads(self.run_cli("restore").stdout)
        self.addCleanup(shutil.rmtree, second["kit"], True)
        self.assertNotEqual(first["kit"], second["kit"])
        self.assertTrue(Path(second["kit"]).is_dir())

if __name__ == "__main__":
    unittest.main()
