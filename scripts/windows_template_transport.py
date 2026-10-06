"""Bounded UTM transport; transport completion is not guest readiness."""
import base64
from contextlib import contextmanager
import gzip
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

TASK_EXECUTION_SECONDS = 120
TASK_WAIT_SECONDS = TASK_EXECUTION_SECONDS + 5
TRANSPORT_CALL_SECONDS = TASK_WAIT_SECONDS + 25
MIN_NATIVE_BUDGET = TRANSPORT_CALL_SECONDS + 30


class Failure(Exception):
    pass


class Transport:
    def __init__(self, executable, template, timeout, lease_descriptor=None):
        self.executable = executable
        self.template = template
        self.deadline = time.monotonic() + timeout
        self.progress_observed = False
        self.prepared_roots = set()
        self.last_task = None
        self.operation = 'not_started'
        self.started = time.monotonic()
        self.steps = []
        self.last_progress = None
        self.lease_descriptor = lease_descriptor

    @contextmanager
    def step(self, name):
        start = time.monotonic()
        record = {'step': name, 'started_after_seconds': round(start - self.started, 3), 'outcome': 'failed'}
        self.steps.append(record)
        try:
            yield
            record['outcome'] = 'passed'
        finally:
            record['elapsed_seconds'] = round(time.monotonic() - start, 3)

    def call(self, *args, data=None):
        self.operation = '_'.join(args[:2] if args[:1] == ('file',) else args[:1])
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Failure('transport_timeout')
        try:
            result = subprocess.run([self.executable, *args], input=data, capture_output=True,
                                    pass_fds=(() if self.lease_descriptor is None else (self.lease_descriptor,)),
                                    timeout=min(remaining, TRANSPORT_CALL_SECONDS))
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
            with self.step('protected_staging'):
                self.powershell((here / 'windows_template_root.ps1').read_text().replace('__RUN__', request['run']))
                staging = envelope(self.wait_file(root + '\\staging.json'), request['run'], 'staging')
                if not staging['ok']: raise Failure('guest_staging_failed')
            self.prepared_roots.add(root)
        source = (here / 'windows_template_preflight.ps1').read_text()
        payload = base64.b64encode(json.dumps(request).encode()).decode('ascii')
        with self.step('guest_preflight'):
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

    def measure(self, request, candidate=None, desktop=False):
        completed = False
        try:
            result = self.measure_task(request, candidate, desktop)
            completed = True
            return result
        finally:
            # A timed-out work budget must not hide the last guest checkpoint.
            # This read-only collection has its own bounded 15-second budget.
            diagnostics = Transport(self.executable, self.template, 15, self.lease_descriptor)
            try:
                raw = diagnostics.call('file', 'pull', self.template,
                                       'C:\\Users\\Public\\' + request['run'] + '\\output\\progress.json')
                self.last_progress = progress_envelope(raw, request['run'])
            except (Failure, OSError):
                self.last_progress = {'outcome': 'unavailable', 'reason': 'guest_progress_unavailable_or_invalid'}
                if completed:
                    raise Failure('guest_progress_invalid') from None

    def measure_task(self, request, candidate=None, desktop=False):
        root = 'C:\\Users\\Public\\' + request['run']
        here = Path(__file__).parent
        files = {'\\request.json': json.dumps(request).encode(),
                 '\\probe.py': (here / 'windows_template_probe.py').read_bytes(),
                 '\\user.ps1': (here / 'windows_template_user.ps1').read_text().replace('__ROOT__', root).encode('utf-8')}
        if desktop:
            files['\\probe.py'] = (here / 'windows_desktop_probe.py').read_bytes()
            files['\\windows_template_probe.py'] = (here / 'windows_template_probe.py').read_bytes()
            files['\\user.ps1'] = files['\\user.ps1'].replace(b"phase='native'", b"phase='desktop'")
            for name in ('windows_desktop_runtime.py', 'windows_desktop_bridge.py', 'windows_desktop_ui.ps1',
                         'windows_process.py', 'windows_process.cs'):
                files['\\' + name] = (here / name).read_bytes()
        if candidate is not None:
            files.update({'\\candidate.exe.gz': gzip.compress(candidate, mtime=0),
                          '\\windows_candidate.py': (here / 'windows_candidate.py').read_bytes()})
        for suffix, content in files.items():
            with self.step('stage_' + suffix[1:].split('.')[0]):
                self.call('file', 'push', self.template, root + suffix, data=content)
        source = (here / 'windows_template_stage.ps1').read_text().replace('__ROOT__', root)
        source = source.replace('__TASK_SECONDS__', str(TASK_EXECUTION_SECONDS))
        source = source.replace('__WINDOW_STYLE__', 'Normal' if request['initialize_sandbox'] else 'Hidden')
        # Read the protected harness as a scriptblock, retaining the encoded-command
        # execution contract without nesting its full base64 payload in UTM argv.
        guest = "& ([scriptblock]::Create([IO.File]::ReadAllText('" + root + "\\user.ps1')))"
        source = source.replace('__USER_COMMAND__', base64.b64encode(guest.encode('utf-16-le')).decode())
        with self.step('prepare_task'):
            self.powershell(source)
            staged = envelope(self.wait_file(root + '\\task-staging.json'), request['run'], 'task_staging')
            if not staged['ok']: raise Failure('guest_staging_failed')
        # Provisioning cannot consume the task's 120-second execution budget,
        # 125-second controller wait, 150-second transport cap, or collection margin.
        if self.deadline - time.monotonic() < MIN_NATIVE_BUDGET:
            raise Failure('insufficient_native_task_budget')
        with self.step('desktop_task' if desktop else 'native_task'):
            controller = (here / 'windows_template_wait.ps1').read_text().replace('__ROOT__', root)
            self.powershell(controller.replace('__WAIT_SECONDS__', str(TASK_WAIT_SECONDS)))
        with self.step('collect_task'):
            task = envelope(self.wait_file(root + '\\task.json'), request['run'], 'completion')
        self.last_task = task
        if task.get('completed') is not True:
            raise Failure('guest_task_incomplete')
        with self.step('collect_desktop' if desktop else 'collect_native'):
            result = envelope(self.call('file', 'pull', self.template, root + '\\result.json'), request['run'],
                              'desktop' if desktop else 'native')
        return task, result


def progress_envelope(raw, run):
    value = envelope(raw, run, 'progress')
    allowed = {'user_started', 'package_discovered', 'engine_hashed', 'engine_discovered',
               'native_probe_started', 'candidate_verification', 'workspace_preparation',
               'engine_initialization', 'sandbox_configuration', 'workspace_execution',
               'outside_execution', 'desktop_authentication', 'desktop_preparation', 'desktop_startup',
               'desktop_permissions', 'desktop_command', 'desktop_quit', 'desktop_cleanup'}
    points = value.get('checkpoints')
    if value['ok'] is not True or not isinstance(points, list) or not 1 <= len(points) <= len(allowed):
        raise Failure('malformed_guest_progress')
    clean = []
    previous = 0
    seen = set()
    for point in points:
        if (not isinstance(point, dict) or not isinstance(point.get('stage'), str)
                or point['stage'] not in allowed or point['stage'] in seen
                or type(point.get('elapsed_ms')) is not int or not previous <= point['elapsed_ms'] <= 1800000):
            raise Failure('malformed_guest_progress')
        previous = point['elapsed_ms']
        seen.add(point['stage'])
        clean.append({'stage': point['stage'], 'elapsed_ms': point['elapsed_ms']})
    return {'outcome': 'collected', 'checkpoints': clean}


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
