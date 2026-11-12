"""Controlled executable/JSON-RPC boundary; never contacts an inference service."""
import json
import os
from pathlib import Path
import platform
import sys

role = sys.argv[1]
mode = os.environ.get('FIXTURE_ADMISSION_MODE', 'success')
if role == 'launcher':
    with Path(os.environ['FIXTURE_ADMISSION_LOG']).open('a') as stream:
        stream.write(json.dumps(sys.argv[2:]) + '\n')
    assert sys.argv[-2:] == ['--', '--version'], 'paid invocation is forbidden'
    if mode == 'unavailable':
        print('PRIVATE_PROJECT not available', file=sys.stderr)
        sys.exit(1)
    print('codex-cli 0.160.1')
    sys.exit()

for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    result = {}
    if request['method'] == 'command/exec':
        params = request['params']; command = params['command'][-1]; cwd = Path(params['cwd'])
        result = {'exitCode': 0, 'stdout': '', 'stderr': ''}
        if 'Get-Location' in command:
            result['stdout'] = 'C:\\' if mode == 'wrong_cwd' else str(cwd)
        elif 'python --version' in command:
            result['stdout'] = 'Python ' + platform.python_version()
            if mode == 'python_missing': result['exitCode'] = 1
        elif 'outside.txt' in command:
            if mode == 'outside_writable':
                (cwd.parent / 'outside.txt').write_text('must not exist')
            else:
                result.update(exitCode=1, stderr='Unauthori\nzedAccessException\nFullyQualifiedErrorId : GetContentWriterUnauthorizedAccessError,Microsoft.PowerShell.Commands.SetContentCommand')
        elif 'Set-Content' in command:
            (cwd / 'write.txt').write_text('qualification-ok')
            result['stdout'] = 'qualification-ok'
        else:
            result['stdout'] = (cwd / 'input.json').read_text()
    if request['method'] == 'command/exec' and mode in ('null_stdout', 'null_stderr', 'bool_exit'):
        result[{'null_stdout': 'stdout', 'null_stderr': 'stderr', 'bool_exit': 'exitCode'}[mode]] = True if mode == 'bool_exit' else None
    if mode == 'malformed_result' and request['method'] == 'command/exec': result = None
    print(json.dumps({'id': request['id'], 'result': result}), flush=True)
