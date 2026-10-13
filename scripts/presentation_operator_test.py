"""Exercise the operator handoff against a failed child without launching an app."""
import os
from pathlib import Path
import pty
import shlex
import subprocess
import sys
import tempfile
import unittest


class OperatorTests(unittest.TestCase):
    def test_failed_launch_reports_client_error_without_asking_for_previews(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wizard = root / 'operator.sh'
            source = Path(__file__).with_name('presentation_operator.sh').read_text()
            wizard.write_text(source.replace('TASK_ROOT=/tmp/tofa-presentation-validation',
                'TASK_ROOT=' + shlex.quote(str(root / 'validation'))))
            fixture = root / 'python'
            fixture.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
if len(sys.argv) > 1 and sys.argv[1].endswith('presentation_calibration.py'):
    if '--check' in sys.argv:
        print('{"status":"assets_ready"}')
        sys.exit(0)
    root = pathlib.Path(sys.argv[sys.argv.index('--private-root') + 1])
    run = root / 'failed-attempt'
    (run / 'workspace').mkdir(parents=True)
    (run / 'prompt.txt').write_text('synthetic prompt')
    (run / 'client.log').write_text('tofa: unsupported evaluation observer contract\\n')
    (run / 'qualification.json').write_text(json.dumps({'status':'infra_blocked','failure':'actual_client_loader_unobserved'}))
    print('Fixture launch failed', file=sys.stderr, flush=True)
    sys.exit(1)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
            fixture.chmod(0o700)
            master, slave = pty.openpty()
            try:
                process = subprocess.Popen(['bash', str(wizard)], stdin=slave,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env=dict(os.environ, TOFA_PRESENTATION_PYTHON=str(fixture)))
                os.write(master, b'y\n')
                output, errors = process.communicate(timeout=15)
            finally:
                if 'process' in locals() and process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                os.close(master); os.close(slave)
            self.assertEqual(process.returncode, 1, output + errors)
            self.assertIn('unsupported evaluation observer contract', output + errors)
            self.assertNotIn('Record native previews', output)
            self.assertNotIn('Preview result [p/f/u]', output)


if __name__ == '__main__':
    unittest.main()
