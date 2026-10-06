"""Bounded UTM transport; transport completion is not guest readiness."""
import base64
import gzip
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET


class Failure(Exception):
    pass


class Transport:
    def __init__(self, executable, template, timeout):
        self.executable = executable
        self.template = template
        self.deadline = time.monotonic() + timeout
        self.progress_observed = False
        self.prepared_roots = set()
        self.last_task = None
        self.operation = 'not_started'

    def call(self, *args, data=None):
        self.operation = '_'.join(args[:2] if args[:1] == ('file',) else args[:1])
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Failure('transport_timeout')
        try:
            result = subprocess.run([self.executable, *args], input=data, capture_output=True,
                                    timeout=min(remaining, 150))
        except subprocess.TimeoutExpired as error:
            raise Failure('transport_timeout') from error
        stderr = result.stderr.strip()
        if stderr.startswith(b'#< CLIXML'):
            try:
                entries = list(ET.fromstring(stderr.split(b'\n', 1)[1]))
                if entries and all(entry.attrib.get('S') == 'progress' for entry in entries):
                    self.progress_observed = True
                    stderr = b''
            except (ET.ParseError, IndexError):
                pass
        if result.returncode or stderr or b'Error from event:' in result.stdout:
            diagnostic = result.stdout + stderr
            if args[:1] == ('ip-address',) and b'guest agent is not running' in diagnostic.lower():
                raise Failure('guest_agent_pending')
            if (args[:2] == ('file', 'pull') and b'OSStatus error -2700' in diagnostic
                    and b'failed to open file' in diagnostic
                    and any(message in diagnostic for message in (b'The system cannot find the file specified.',
                                                                   b'The system cannot find the path specified.'))):
                raise Failure('guest_result_pending')
            # Never echo external stderr: it can contain credentials or user content.
            raise Failure('vm_transport_failed')
        return result.stdout

    def powershell(self, source):
        encoded = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        if len(encoded) > 30000:
            raise Failure('guest_command_too_large')
        return self.call('exec', self.template, '--cmd', 'powershell.exe', '-NoProfile',
                         '-NonInteractive', '-EncodedCommand', encoded)

    def preflight(self, request):
        here = Path(__file__).parent
        root = 'C:\\Users\\Public\\' + request['run']
        if root not in self.prepared_roots:
            self.powershell((here / 'windows_template_root.ps1').read_text().replace('__RUN__', request['run']))
            staging = envelope(self.wait_file(root + '\\staging.json'), request['run'], 'staging')
            if not staging['ok']: raise Failure('guest_staging_failed')
            self.prepared_roots.add(root)
        source = (here / 'windows_template_preflight.ps1').read_text()
        payload = base64.b64encode(json.dumps(request).encode()).decode('ascii')
        self.powershell(source.replace('__REQUEST__', payload))
        raw = self.wait_file(root + '\\preflight.json')
        return envelope(raw, request['run'], 'preflight')

    def wait_file(self, path):
        while True:
            try:
                return self.call('file', 'pull', self.template, path)
            except Failure as error:
                if str(error) != 'guest_result_pending':
                    raise
                if self.deadline <= time.monotonic():
                    raise Failure('guest_completion_timeout') from error
                time.sleep(min(.5, max(0, self.deadline - time.monotonic())))

    def measure(self, request, candidate=None):
        root = 'C:\\Users\\Public\\' + request['run']
        here = Path(__file__).parent
        files = {'\\request.json': json.dumps(request).encode(),
                 '\\probe.py': (here / 'windows_template_probe.py').read_bytes()}
        if candidate is not None:
            files.update({'\\candidate.exe.gz': gzip.compress(candidate, mtime=0),
                          '\\windows_candidate.py': (here / 'windows_candidate.py').read_bytes()})
        for suffix, content in files.items():
            self.call('file', 'push', self.template, root + suffix, data=content)
        source = (here / 'windows_template_stage.ps1').read_text().replace('__ROOT__', root)
        source = source.replace('__WINDOW_STYLE__', 'Normal' if request['initialize_sandbox'] else 'Hidden')
        guest = (here / 'windows_template_user.ps1').read_text().replace('__ROOT__', root)
        source = source.replace('__USER_COMMAND__', base64.b64encode(guest.encode('utf-16-le')).decode())
        self.powershell(source)
        task = envelope(self.wait_file(root + '\\task.json'), request['run'], 'completion')
        self.last_task = task
        if task.get('completed') is not True:
            raise Failure('guest_task_incomplete')
        result = envelope(self.call('file', 'pull', self.template, root + '\\result.json'), request['run'], 'native')
        return task, result


def envelope(raw, run, phase):
    try:
        value = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as error:
        raise Failure('malformed_guest_result') from error
    if not isinstance(value, dict) or value.get('run') != run or value.get('phase') != phase:
        raise Failure('uncorrelated_guest_result')
    if type(value.get('ok')) is not bool:
        raise Failure('malformed_guest_result')
    return value
