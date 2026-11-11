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
import traceback
from datetime import datetime, timezone, timedelta

ROOT = Path('/tmp/tofa-presentation-validation')
CASES = ('clean-exit', 'repeat-launch', 'launcher-crash', 'native-crash',
         'ordinary-launch', 'bridge-update', 'uninstall-reinstall',
         'service-switching', 'history-resume', 'review-routing',
         'launch-naming', 'runtime-preview')
COLLECTION_ERRORS = (OSError, ValueError, KeyError, subprocess.SubprocessError, http.client.HTTPException)


def system_skills_digest(value, identity):
    evidence = (identity or {}).get('system_skills')
    if evidence and value in evidence['accepted_skills_sha256']:
        return hashlib.sha256(json.dumps(evidence['accepted_skills_sha256'],separators=(',',':')).encode()).hexdigest()
    return value


def integration_identity(identity):
    """Compare integration invariants without erasing catalog/plugin provenance."""
    result = dict(identity)
    if result.get('system_skills'):
        result['system_skills'] = {**result['system_skills'], 'path':''}
    if 'hashes' in result:
        result['hashes'] = {key:value for key,value in result['hashes'].items()
                            if key not in ('catalog', 'native_catalog', 'plugins')}
    if 'skills' in result.get('hashes', {}):
        result['hashes']['skills'] = system_skills_digest(result['hashes']['skills'], identity)
    return result


def integration_protected(state, identity=None):
    return {key:system_skills_digest(value, identity) if key == 'skills' else value
            for key,value in state.items() if key != 'plugins'}


def integration_snapshot(snapshot):
    # Compare copies; retain complete original receipts, including cache detail.
    result = {**snapshot, 'identity':integration_identity(snapshot['identity'])}
    if 'protected' in result:
        result['protected'] = integration_protected(result['protected'], snapshot['identity'])
    evidence = snapshot['identity'].get('system_skills')
    if evidence and snapshot['identity'].get('hashes', {}).get('skills') in evidence['accepted_skills_sha256']:
        result['skill_files'] = dict(snapshot['skill_files'])
        result['skill_files']['skills'] = {k:v for k,v in snapshot['skill_files']['skills'].items()
                                          if not k.startswith('.system/')}
    result.pop('plugin_files', None)
    return result


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
    if plan.get('system_skills_contract'): command += ['--system-skills-contract', plan['system_skills_contract']]
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
    if integration_identity(current['identity']) != integration_identity(frozen['identity']): raise ValueError('calibration_identity_drift')
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


def terminal_outcome(plan,process,observer,requested_stop,exited_before_stop):
    # Observer's first terminal outcome is authoritative; a later finish cannot
    # turn scope/budget/disconnection failure into successful collection.
    reason=observer.reason or requested_stop
    return {'schema':'tofa-native-account-finish-v1','stop':reason,
         'finished_utc':utc(stamp()),'exit_code':process.returncode if process else None,
         'observer_stop':observer.reason,'observer_requests':len(observer.records),
         'stop_acknowledged':observer.stop_acknowledged,
         'process_exited_before_stop':exited_before_stop,
         'scope':plan.get('limits_note','Synthetic runtime transport; no model capability or paid inference.'),
         'qualified':False}


def write_finish(run,plan,process,observer,requested_stop,exited_before_stop):
    save(run/'after.json',snapshot(plan))
    save(run/'finish.json',terminal_outcome(plan,process,observer,requested_stop,exited_before_stop))


def collection_record(run, errors, diagnostics, route_registered):
    if diagnostics:
        with open(run/'collection-error.log', 'x', opener=lambda p,f: os.open(p,f,0o600)) as log:
            log.write('\n'.join(diagnostics))
    save(run/'collection.json', {'schema':'tofa-native-account-collection-v1',
         'status':'failed' if errors else 'complete', 'errors':errors,
         'route_registered':route_registered})


def finish_collection(run,plan,process,observer,requested_stop,exited_before_stop, failure=None):
    errors = [failure[0]] if failure else []
    diagnostics = [failure[1]] if failure else []
    def collect(phase, reason, action):
        try: action()
        except COLLECTION_ERRORS:
            errors.append({'phase':phase, 'reason':reason})
            # Raw diagnostics stay in a private file; summaries use fixed codes.
            diagnostics.append(traceback.format_exc())

    collect('observer_drain', 'observer_drain_failed', lambda: observer.__exit__(None,None,None))
    outcome = terminal_outcome(plan,process,observer,requested_stop,exited_before_stop)
    if any(e['phase']=='observer_drain' for e in errors): outcome['observer_requests'] = None
    save(run/'launch-outcome.json', outcome)
    # A prerequisite refusal can end the launch before any route exists. No
    # route-stop proof is fabricated for that case; admission still requires it.
    if observer.endpoint or (run/'start.json').exists():
        collect('route_stop', 'route_stop_probe_failed', lambda: probe_stopped_route(run,observer,process.pid))
    collect('after_snapshot', 'snapshot_failed', lambda: save(run/'after.json',snapshot(plan)))
    collection_record(run, errors, diagnostics, bool(observer.endpoint))
    if errors:
        if failure: return  # The original orchestration exception is in flight.
        raise ValueError('collection_incomplete_private_diagnostics_retained')
    save(run/'finish.json', outcome)


def finish_calibration(run,plan,process,observer,exited_before_stop):
    # The calibration's with-block has drained every owned request handler.
    write_finish(run,plan,process,observer,'process_exit',exited_before_stop)


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
    if getattr(options, 'system_skills_contract', None):
        save(run/'system-skills.json', read(options.system_skills_contract))
        plan['system_skills_contract'] = str(run/'system-skills.json')
    save(run / 'plan.json', plan)
    deferred = getattr(options, 'defer_snapshot', False)
    if deferred:
        save(run/'workspace-setup.json', {'schema':'tofa-workspace-setup-v1',
             'workspace':str(run/'workspace'), 'allocated_utc':utc(stamp())})
    else:
        before = snapshot(plan); save(run / 'before.json', before)
    print(json.dumps({'run': str(run), 'status': 'workspace_setup_required' if deferred else 'prepared',
                      'desktop_launched': False}))


def freeze(run):
    """Capture once, after human workspace setup in the ordinary client.

    This never edits settings, refreshes an existing baseline or grants a pass.
    Launch still compares its complete snapshot to this immutable baseline.
    """
    run = private_run(run)
    if any((run/name).exists() for name in ('start.json','declaration.json','collection.json','launcher-process.json')):
        raise ValueError('attempt_consumed_no_retry')
    if (run/'before.json').exists(): raise ValueError('baseline_already_frozen')
    setup = read(run/'workspace-setup.json')
    if setup.get('schema') != 'tofa-workspace-setup-v1' or setup.get('workspace') != str(run/'workspace'):
        raise ValueError('workspace_setup_record_invalid')
    save(run/'before.json', snapshot(read(run/'plan.json')))
    print(json.dumps({'run':str(run),'status':'prepared','desktop_launched':False}))


def launch(run):
    from capability_observer import Observer
    run = private_run(run)
    if any((run/name).exists() for name in ('start.json', 'declaration.json', 'collection.json')):
        raise ValueError('attempt_consumed_no_retry')
    phase = 'prelaunch_snapshot'
    try:
        plan = read(run/'plan.json'); before = read(run/'before.json')
        current = snapshot(plan)
        if current != before:
            save(run/'prelaunch.json', current)
        if integration_snapshot(current) != integration_snapshot(before):
            raise ValueError('environment_drift_before_launch')
        phase = 'observer_setup'
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
    except COLLECTION_ERRORS as error:
        reason = 'environment_drift_before_launch' if str(error)=='environment_drift_before_launch' else 'prelaunch_collection_failed'
        collection_record(run, [{'phase':phase, 'reason':reason}], [traceback.format_exc()], None)
        raise
    process = None
    observer_drained = False
    failure = None
    reason = 'collector_failed'
    exited_before_stop = None
    phase = 'observer_start'
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
        phase = 'launcher_start'
        with open(run / 'launcher.log', 'x', opener=lambda p,f: os.open(p,f,0o600)) as log:
            process = subprocess.Popen(command, cwd=run / 'workspace', stdout=log, stderr=log, start_new_session=True)
            save(run / 'launcher-process.json', {'schema': 'tofa-native-account-process-v1', 'launcher_pid': process.pid,
                 'launcher_sha256': digest(plan['launcher']), 'started_utc': utc(now)})
            print(json.dumps({'run': str(run), 'launcher_pid': process.pid, 'deadline_utc': utc(now + timedelta(seconds=plan['seconds']))}), flush=True)
            phase = 'launch_monitor'
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
                if observer.reason: reason=observer.reason; break
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
            exited_before_stop=process.poll() is not None
            observer.stop(reason)
            try: process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        observer_drained=True
        finish_collection(run,plan,process,observer,reason,exited_before_stop)
        print(json.dumps({'run':str(run),'stop':observer.reason or reason,'qualified':False}))
    except COLLECTION_ERRORS:
        failure = ({'phase':phase, 'reason':'collector_failed'}, traceback.format_exc())
        raise
    finally:
        if not observer_drained:
            exited_before_stop = process.poll() is not None if process else None
            if process and exited_before_stop and not (run/'start.json').exists():
                reason = 'launch_failed'
            else:
                reason = observer.reason or 'collector_failed'
            observer.stop(reason)

        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        if not observer_drained:
            finish_collection(run,plan,process,observer,reason,exited_before_stop,failure)


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
    if integration_identity(before['identity']) != integration_identity(after['identity']): raise ValueError('identity_drift')
    observations = [read(path) for path in sorted(run.glob('observation-*.json'))]
    value = {'schema':'tofa-native-account-case-v1','case':declaration['case'],
        'declaration':reference(run,run/'declaration.json'),'start':reference(run,run/'start.json'),
        'before_snapshot':reference(run,run/'before.json'),'after_snapshot':reference(run,run/'after.json'),
        'process_receipt':reference(run,run/'process.json'),'finish_receipt':reference(run,run/'finish.json'),
        'requests':reference(run,run/'requests.json'),
        **({'system_skills_contract':reference(run,run/'system-skills.json')} if before['identity'].get('system_skills') else {}),
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
        'integration_protected_equal':integration_protected(before['protected'],before['identity'])==integration_protected(after['protected'],after['identity']),
        'observations':[{'criterion':o['criterion'],'method':o['method'],'outcome':o['outcome']} for o in observations],
        'next':'Validate immutable full evidence with the frozen launcher; fixture and native observations remain separate.'})
    print(json.dumps({'case_record':str(run/'case.json'),'qualified':False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    for name in ('launcher', 'app-bundle', 'runtime-root', 'model-services'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--system-skills-contract', type=Path)
    p.add_argument('--scope', type=Path); p.add_argument('--prompt'); p.add_argument('--source-revision', required=True)
    p.add_argument('--case', choices=CASES, required=True); p.add_argument('--model', required=True)
    p.add_argument('--guardian', default='zai-org/GLM-5.3-Flash')
    p.add_argument('--seconds', type=int, choices=(600,900), default=600)
    p.add_argument('--requests', type=int, choices=range(1,81), default=12)
    p.add_argument('--output-tokens', type=int, choices=range(1,8193), default=4096)
    p.add_argument('--defer-snapshot', action='store_true',
                   help='Allocate the workspace only; freeze after human ordinary-client setup, before run.')
    p = sub.add_parser('freeze'); p.add_argument('run', type=Path)
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
    elif options.action == 'freeze': freeze(options.run)
    elif options.action == 'run': launch(options.run)
    elif options.action == 'observe': observe(options)
    elif options.action == 'record': record(options)
    elif options.action == 'external-action': external_action(options)
    else: control(options)


if __name__ == '__main__':
    try: main()
    except COLLECTION_ERRORS:
        raise SystemExit('qualification collection failed; retain private attempt for diagnosis; no retry or pass inferred')
