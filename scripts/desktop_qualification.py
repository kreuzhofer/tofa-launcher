"""Private, explicit Desktop qualification collection for #134.

No action grants a qualification pass. Machine observations and attributed UI
observations remain separate; the launcher's full evidence validator decides
admission. Existing native histories bypass Observer request/token accounting.
"""
import argparse
import hashlib
import http.client
from urllib.parse import urlsplit
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from datetime import datetime, timezone, timedelta

ROOT = Path('/tmp/tofa-presentation-validation')
CASES = ('clean-exit', 'repeat-launch', 'launcher-crash', 'native-crash',
         'ordinary-launch', 'bridge-update', 'uninstall-reinstall',
         'service-switching', 'history-resume', 'review-routing',
         'launch-naming', 'runtime-preview')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('invalid_private_record')
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('private_owned_record_required')
    return json.loads(path.read_text(), object_pairs_hook=unique)


def private_run(path):
    path = Path(path).absolute()
    root = ROOT.resolve()
    if path.is_symlink() or not path.is_dir(): raise ValueError('owned_run_required')
    if ROOT.absolute() in path.parents:
        path = root / path.relative_to(ROOT.absolute())
    resolved = path
    if root not in resolved.parents: raise ValueError('fixed_validation_root_required')
    current = resolved
    while current != root:
        info = current.lstat()
        if current.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private_owned_run_or_symlink_invalid')
        current = current.parent
    return resolved


def save(path, value):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def stamp(): return datetime.now(timezone.utc).replace(microsecond=0)
def utc(value): return value.isoformat().replace('+00:00', 'Z')


def snapshot(plan):
    command = [plan['launcher'], 'desktop-qualification', 'snapshot', '--app-bundle', plan['app_bundle'],
               '--runtime-root', plan['runtime_root'], '--harness-root', str(Path(__file__).resolve().parent),
               '--source-revision', plan['source_revision']]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if result.returncode: raise ValueError('snapshot_failed_private_stderr_not_published')
    return json.loads(result.stdout, object_pairs_hook=unique)


def probe_stopped_route(run, observer, launcher_pid):
    """Probe only the endpoint this attempt registered, with its expired tokens."""
    if not observer.endpoint: raise ValueError('owned_route_not_registered')
    target=urlsplit(observer.endpoint)
    if target.scheme!='http' or target.hostname!='127.0.0.1' or not target.port: raise ValueError('owned_route_invalid')
    outcomes={}
    for name,path,token in (('inference','/responses',observer.inference_token),('control','/evaluation-stop',observer.token)):
        connection=http.client.HTTPConnection('127.0.0.1',target.port,timeout=2)
        try:
            connection.request('POST',path,body=b'{}',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            response=connection.getresponse();outcomes[name]={'http_status':response.status,'socket_closed':False}
            response.read(4096)
        except ConnectionRefusedError: outcomes[name]={'http_status':0,'socket_closed':True}
        finally: connection.close()
    save(run/'route-stop.json',{'schema':'tofa-native-account-route-stop-v1','attempt':run.name,
         'launcher_pid':launcher_pid,'endpoint':observer.endpoint,'observed_utc':utc(stamp()),**outcomes})


def prepare_calibration(run, options, limits):
    """Bind the existing synthetic runtime observer to this frozen candidate."""
    run=private_run(run); frozen=read(options.native_account_snapshot)
    if frozen.get('schema') != 'tofa-native-account-snapshot-v1': raise ValueError('snapshot_schema_invalid')
    plan={'launcher':str(options.launcher.resolve()),'app_bundle':str(options.app_bundle.resolve()),
          'runtime_root':str(options.runtime_root.resolve()),'source_revision':frozen['identity']['source_revision']}
    current=snapshot(plan)
    if current['identity'] != frozen['identity']: raise ValueError('calibration_identity_drift')
    save(run/'before.json',current)
    now=stamp()
    save(run/'declaration.json',{'schema':'tofa-native-account-declaration-v1','attempt':run.name,
         'case':'runtime-preview','root':str(run),'identity':current['identity'],
         'issued_utc':utc(now),'expires_utc':utc(now+timedelta(seconds=limits['seconds'])),
         'seconds':limits['seconds'],'requests':limits['requests']})
    return plan


def calibration_process(run, launcher, process, profile):
    if (run/'process.json').exists(): return
    pid=owned_native_pid(profile,process.pid)
    if pid:
        save(run/'process.json',{'schema':'tofa-native-account-process-v1','launcher_pid':process.pid,
             'native_pid':pid,'launcher_sha256':digest(launcher),
             'started_utc':read(run/'declaration.json')['issued_utc']})


def finish_calibration(run, plan, process, observer):
    save(run/'after.json',snapshot(plan))
    save(run/'finish.json',{'schema':'tofa-native-account-finish-v1','stop':observer.reason or 'process_exit',
         'finished_utc':utc(stamp()),'exit_code':process.returncode if process else None,
         'observer_stop':observer.reason,'observer_requests':len(observer.records),
         'scope':'Synthetic runtime transport; no model capability or paid inference.','qualified':False})


def prepare(options):
    # No Desktop launch or inference. Snapshot reads configured catalog and files.
    parent = ROOT / 'runs' / 'native-account-134'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    run = parent / (options.case + '.' + secrets.token_hex(8)); run.mkdir(mode=0o700)
    run = private_run(run); (run / 'workspace').mkdir(mode=0o700)
    if not options.scope and not options.prompt: raise ValueError('exact_prompt_or_scope_required')
    if options.prompt: (run/'prompt.txt').write_text(options.prompt+'\n'); (run/'prompt.txt').chmod(0o600)
    plan = {'schema': 'tofa-native-account-plan-v1', 'case': options.case,
            'launcher': str(options.launcher.resolve()), 'app_bundle': str(options.app_bundle.resolve()),
            'runtime_root': str(options.runtime_root.resolve()), 'source_revision': options.source_revision,
            'model': options.model, 'guardian': options.guardian, 'seconds': options.seconds,
            'requests': options.requests, 'output_tokens': options.output_tokens,
            'model_services': read(options.model_services),
            'scope': read(options.scope) if options.scope else None,
            'limits_note': 'Observer-visible routes only; native output tokens use observed usage when absent from request. Direct native histories are bounded by launch time only.'}
    save(run / 'plan.json', plan)
    before = snapshot(plan); save(run / 'before.json', before)
    print(json.dumps({'run': str(run), 'status': 'prepared', 'desktop_launched': False}))


def launch(run):
    from capability_observer import Observer
    run = private_run(run); plan = read(run / 'plan.json'); before = read(run / 'before.json')
    if (run / 'start.json').exists() or (run / 'declaration.json').exists(): raise ValueError('attempt_consumed_no_retry')
    current = snapshot(plan)
    if current != before: raise ValueError('environment_drift_before_launch')
    limits = {key: plan[key] for key in ('seconds', 'requests', 'output_tokens')}
    kwargs = {}
    if plan['scope'] is not None:
        scope = plan['scope']; scope['root'] = str(run); scope['attempt'] = run.name
        # Workspace placeholders are explicit, never infer or rewrite history.
        for thread in scope.get('threads', []):
            if thread.get('workspace') == '$WORKSPACE': thread['workspace'] = str(run / 'workspace')
        save(run / 'scope.json', scope)
        kwargs.update(scope_declaration=run / 'scope.json', scope_sha256=digest(run / 'scope.json'), scope_attempt=run.name)
    observer = Observer(run, model=plan['model'], guardian=plan['guardian'], limits=limits,
                        case='05', model_services=plan['model_services'], **kwargs)
    process = None
    try:
        observer.__enter__()
        save(run / 'observer.json', {'version': 2, 'endpoint': 'http://127.0.0.1:' + str(observer.port),
             'secret': observer.secret, 'seconds': plan['seconds'],
             'qualification_declaration': str(run / 'declaration.json')})
        now = stamp()
        save(run / 'declaration.json', {'schema': 'tofa-native-account-declaration-v1',
             'attempt': run.name, 'case': plan['case'], 'root': str(run), 'identity': before['identity'],
             'issued_utc': utc(now), 'expires_utc': utc(now + timedelta(seconds=plan['seconds'])),
             'seconds': plan['seconds'], 'requests': plan['requests'],
             **({'scope_sha256': digest(run / 'scope.json')} if plan['scope'] is not None else {})})
        command = [plan['launcher'], 'launch', 'codex-desktop', '--app-bundle', plan['app_bundle'],
                   '--model', plan['model'], '--guardian-model', plan['guardian'],
                   '--native-account-candidate', '--evaluation-observer', str(run / 'observer.json')]
        with (run / 'launcher.log').open('x', opener=lambda p,f: os.open(p,f,0o600)) as log:
            process = subprocess.Popen(command, cwd=run / 'workspace', stdout=log, stderr=log, start_new_session=True)
            save(run / 'launcher-process.json', {'schema': 'tofa-native-account-process-v1', 'launcher_pid': process.pid,
                 'launcher_sha256': digest(plan['launcher']), 'started_utc': utc(now)})
            print(json.dumps({'run': str(run), 'launcher_pid': process.pid, 'deadline_utc': utc(now + timedelta(seconds=plan['seconds']))}), flush=True)
            reason = 'process_exit'
            native_recorded = False
            crashed = False
            while True:
                if not native_recorded and process.poll() is None:
                    native_pid = owned_native_pid(before['identity']['profile'], process.pid)
                    if native_pid:
                        save(run / 'process.json', {'schema':'tofa-native-account-process-v1',
                             'launcher_pid':process.pid,'native_pid':native_pid,
                             'launcher_sha256':digest(plan['launcher']),'started_utc':utc(now)})
                        native_recorded = True
                if process.poll() is not None and not (run / 'start.json').exists(): reason = 'launch_failed'; break
                if (run / 'cancel.request').exists(): reason = 'operator_cancelled'; break
                if (run / 'finish.request').exists():
                    reason = read(run/'external-action.json')['action'] if (run/'external-action.json').exists() else ('launcher_crash' if crashed else 'operator_finished')
                    break
                if time.time() >= (now + timedelta(seconds=plan['seconds'])).timestamp(): reason = 'deadline'; break
                if (run / 'launcher-crash.request').exists() and not crashed:
                    if plan['case'] != 'launcher-crash': raise ValueError('crash_not_declared')
                    if not native_recorded: raise ValueError('owned_native_process_not_observed')
                    process.kill(); crashed = True
                time.sleep(0.2)
            observer.stop(reason)
            try: process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        probe_stopped_route(run,observer,process.pid)
        save(run / 'after.json', snapshot(plan))
        save(run / 'finish.json', {'schema': 'tofa-native-account-finish-v1', 'stop': reason,
             'finished_utc': utc(stamp()), 'exit_code': process.returncode,
             'observer_stop': observer.reason, 'observer_requests': len(observer.records),
             'scope': plan['limits_note'], 'qualified': False})
        print(json.dumps({'run': str(run), 'stop': reason, 'qualified': False}))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        observer.__exit__(None, None, None)


def owned_native_pid(profile, launcher_pid):
    # Observe only the candidate's direct native child. Never infer ownership from
    # an app name or send a signal to an unrelated/global process.
    lock = Path(profile)/'SingletonLock'
    try:
        native_pid = int(os.readlink(lock).rsplit('-',1)[1])
        parent = subprocess.run(['/bin/ps','-p',str(native_pid),'-o','ppid='], capture_output=True, timeout=2)
        if parent.returncode or int(parent.stdout.strip()) != launcher_pid: return None
        return native_pid
    except (OSError,ValueError,IndexError,subprocess.SubprocessError): return None


def external_action(options):
    # Receipt for an already observed, explicitly declared action. This command
    # neither kills the client nor invokes an installer/uninstaller.
    run=private_run(options.run); declaration=read(run/'declaration.json'); process=read(run/'process.json')
    expected={'native-crash':'native_crash','bridge-update':'bridge_update_interrupted','uninstall-reinstall':'uninstall_reinstall'}
    if expected.get(declaration['case']) != options.observed_action: raise ValueError('external_action_not_declared')
    now=stamp()
    if now > datetime.fromisoformat(declaration['expires_utc'].replace('Z','+00:00')): raise ValueError('attempt_expired')
    save(run/'external-action.json',{'schema':'tofa-native-account-inspection-v1',
        'attempt':declaration['attempt'],'operator':options.operator,'method':options.method,
        'observed_utc':utc(now),'sources':[reference(run,p) for p in options.source],
        'action':options.observed_action,'native_pid':process['native_pid'],'outcome':'observed'})


def observe(options):
    run = private_run(options.run)
    if (run / 'finish.json').exists(): raise ValueError('observation_after_finish_rejected')
    declaration = read(run / 'declaration.json')
    if stamp() > datetime.fromisoformat(declaration['expires_utc'].replace('Z', '+00:00')):
        raise ValueError('attempt_expired')
    if not re.fullmatch(r'[a-z0-9-]{1,80}', options.criterion): raise ValueError('invalid_criterion')
    artifacts = {}
    if options.criterion in ('native-pptx-preview', 'native-pdf-preview'):
        for name in ('deck.pptx', 'deck.pdf'):
            path = run / 'workspace/output' / name
            if path.is_symlink() or not path.is_file(): raise ValueError('exact_preview_artifacts_required')
            artifacts[name] = digest(path)
    save(run / ('observation-' + options.criterion + '.json'), {
         'criterion': options.criterion, 'operator': options.operator, 'method': options.method,
         'observed_utc': utc(stamp()), 'outcome': options.outcome, 'artifacts': artifacts})


def control(options):
    run = private_run(options.run)
    if (run / 'finish.json').exists(): raise ValueError('attempt_finished')
    if options.action == 'launcher-crash' and read(run / 'plan.json')['case'] != 'launcher-crash':
        raise ValueError('crash_not_declared')
    save(run / (options.action + '.request'), {'requested_utc': utc(stamp())})


def reference(base, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('regular_evidence_required')
    resolved = path.resolve()
    if base not in resolved.parents: raise ValueError('evidence_outside_run')
    return {'path': str(resolved.relative_to(base)), 'sha256': digest(resolved)}


def record(options):
    run = private_run(options.run); facts = read(options.facts)
    if set(facts) - {'history_before','history_after','lifecycle','transport','runtime','raw'}:
        raise ValueError('unknown_machine_fact_fields')
    before, after = read(run/'before.json'), read(run/'after.json')
    declaration, start, finish = read(run/'declaration.json'), read(run/'start.json'), read(run/'finish.json')
    if before['identity'] != after['identity']: raise ValueError('identity_drift')
    observations = [read(path) for path in sorted(run.glob('observation-*.json'))]
    value = {'schema':'tofa-native-account-case-v1','case':declaration['case'],
        'declaration':reference(run,run/'declaration.json'),'start':reference(run,run/'start.json'),
        'before_snapshot':reference(run,run/'before.json'),'after_snapshot':reference(run,run/'after.json'),
        'process_receipt':reference(run,run/'process.json'),'finish_receipt':reference(run,run/'finish.json'),
        'requests':reference(run,run/'requests.json'),
        **({'route_stop':reference(run,run/'route-stop.json')} if (run/'route-stop.json').exists() else {}),
        **({'external_action':reference(run,run/'external-action.json')} if (run/'external-action.json').exists() else {}),
        'identity':before['identity'],'started_utc':start['started_utc'],
        'finished_utc':finish['finished_utc'],'stop':finish['stop'],
        'protected_before':before['protected'],'protected_after':after['protected'],
        'observations':observations,**facts}
    save(run/'case.json',value)
    # This sanitized summary deliberately does not turn submitted facts into a pass.
    save(run/'export.json',{'schema':'tofa-native-account-export-v1','case':declaration['case'],
        'attempt':declaration['attempt'],'stop':finish['stop'],'qualified':False,
        'protected_equal':before['protected']==after['protected'],
        'observations':[{'criterion':o['criterion'],'method':o['method'],'outcome':o['outcome']} for o in observations],
        'next':'Validate immutable full evidence with the frozen launcher; fixture and native observations remain separate.'})
    print(json.dumps({'case_record':str(run/'case.json'),'qualified':False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    for name in ('launcher', 'app-bundle', 'runtime-root', 'model-services'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--scope', type=Path); p.add_argument('--prompt'); p.add_argument('--source-revision', required=True)
    p.add_argument('--case', choices=CASES, required=True); p.add_argument('--model', required=True)
    p.add_argument('--guardian', default='zai-org/GLM-5.3-Flash')
    p.add_argument('--seconds', type=int, choices=(600,900), default=600)
    p.add_argument('--requests', type=int, choices=range(1,81), default=12)
    p.add_argument('--output-tokens', type=int, choices=range(1,8193), default=4096)
    p = sub.add_parser('run'); p.add_argument('run', type=Path)
    p = sub.add_parser('observe'); p.add_argument('run', type=Path)
    p.add_argument('--criterion', required=True); p.add_argument('--operator', required=True)
    p.add_argument('--method', choices=('human','computer_use'), required=True)
    p.add_argument('--outcome', choices=('passed','failed','not_observed'), required=True)
    p = sub.add_parser('external-action'); p.add_argument('run', type=Path)
    p.add_argument('--observed-action', choices=('native_crash','bridge_update_interrupted','uninstall_reinstall'), required=True)
    p.add_argument('--operator', required=True); p.add_argument('--method', choices=('human','computer_use','retained_trace_review'), required=True)
    p.add_argument('--source', type=Path, action='append', required=True)
    p = sub.add_parser('record'); p.add_argument('run', type=Path); p.add_argument('--facts', type=Path, required=True)
    for action in ('finish','cancel','launcher-crash'):
        p = sub.add_parser(action); p.add_argument('run', type=Path)
    options = parser.parse_args()
    if options.action == 'prepare': prepare(options)
    elif options.action == 'run': launch(options.run)
    elif options.action == 'observe': observe(options)
    elif options.action == 'record': record(options)
    elif options.action == 'external-action': external_action(options)
    else: control(options)


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('qualification collection failed; retain private attempt for diagnosis; no retry or pass inferred')
