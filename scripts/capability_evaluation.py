"""Explicit macOS capability evaluation; preflight never performs inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import shlex
import signal
import subprocess
import sys
import time
import uuid

CORPUS = Path(__file__).resolve().parent / 'fixtures/capabilities/v3/manifest.json'
DIMENSIONS = ('task_content', 'language', 'skill_use', 'file_integrity',
              'reference_syntax', 'visible_preview', 'repetition', 'recovery')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_path(workspace, name):
    return workspace / ('fixtures/' + name if name.endswith(('.pptx', '.pdf')) else name)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    # Run directories have one writer. Individual attempts are never reused.
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def version(path):
    result = subprocess.run([str(path), '--version'], capture_output=True, timeout=10)
    if result.returncode or not result.stdout.strip():
        raise ValueError('version_probe_failed')
    text = result.stdout.decode().strip()
    if not re.fullmatch(r'[A-Za-z0-9 .+_-]{1,160}', text): raise ValueError('invalid_version')
    return {'sha256': digest(path), 'version': text}


def settings(home):
    return {name: digest(home / name) if (home / name).is_file() else None
            for name in ('config.toml', 'AGENTS.md', 'AGENTS.override.md', 'managed_config.toml')}


def inventory(roots):
    result = []
    for root in roots:
        for path in sorted(Path(root).expanduser().rglob('SKILL.md')):
            resources = []
            total = 0
            for resource in sorted(path.parent.rglob('*')):
                if ('__pycache__' in resource.parts or '.git' in resource.parts or
                        resource.name == '.DS_Store' or resource.suffix == '.pyc' or not resource.is_file()):
                    continue
                total += resource.stat().st_size
                if total > 128 * 1024 * 1024 or len(resources) >= 10000:
                    raise ValueError('skill_inventory_limit')
                resources.append((str(resource.relative_to(path.parent)), digest(resource)))
            result.append({'location_sha256': fingerprint(str(path.resolve())), 'sha256': digest(path),
                           'resources_sha256': fingerprint(resources),
                           'presentation': bool(re.search(r'(?im)^name:.*presentation', path.read_text()))})
    return sorted(result, key=lambda item: item['location_sha256'])


def environment(options):
    home = Path(options.codex_home).expanduser().resolve()
    roots = options.skill_root or [str(home / 'skills'), str(home / 'plugins/cache'),
                                  str(Path.home() / '.agents/skills')]
    return dict(settings=settings(home), skills=inventory(roots), python=version(sys.executable),
                node=version(shutil.which('node')) if shutil.which('node') else None,
                shell={'sha256': digest('/bin/zsh')},
                launcher=version(options.launcher), codex=version(options.codex),
                os=platform.platform(), environment_sha256=fingerprint({key: os.environ.get(key)
                    for key in ('PATH', 'SHELL', 'LANG', 'LC_ALL', 'NODE_PATH')}))


def preflight(options):
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value) for value in (options.model, options.guardian)):
        raise ValueError('invalid_model_id')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', options.variant): raise ValueError('invalid_variant')
    root = Path(options.private_root).expanduser().resolve()
    # Private diagnostics and model text must not become repository artifacts.
    if any((parent / '.git').exists() for parent in (root, *root.parents)):
        raise ValueError('private_root_must_be_outside_git')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077:
        raise ValueError('private_root_requires_mode_0700')
    run_id = uuid.uuid4().hex
    run = root / run_id
    run.mkdir(mode=0o700)
    workspace = run / 'workspace'
    workspace.mkdir(mode=0o700)
    corpus = json.loads(CORPUS.read_text())
    case = corpus['cases'][options.case]
    fixtures = {name: corpus['fixtures'][name] for name in case['files']}
    cell = dict(client=options.client, model=options.model, case=options.case,
                variant=options.variant, corpus=corpus['version'], platform='Darwin/arm64')
    report = dict(schema='tofa-capability-v1', run_id=run_id, cell_id=fingerprint(cell), cell=cell,
        status='ready', blockers=[], started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        limits=case['limits'], requests=[], observations=[],
        controls={'parallel_tool_calls': False, 'repetition_stop': 5,
                  'diagnostic_tool_calls': 3 if options.case == '07' else None,
                  'request_body_bytes': 16 * 1024 * 1024, 'event_bytes': 32 * 1024 * 1024,
                  'response_bytes': 64 * 1024 * 1024, 'workspace_observation_bytes': 128 * 1024 * 1024,
                  'provider_request_retries': 0, 'provider_stream_retries': 0,
                  'guardian_retries': 'native_and_budgeted', 'currency_cap': None},
        criteria={key: {'status': 'not_run', 'reason': 'ui_check_pending' if key == 'visible_preview'
                        else 'not_observed'} for key in DIMENSIONS},
        provenance={'corpus_sha256': digest(CORPUS), 'prompt_sha256': fingerprint(case['prompt']),
                    'fixture_hashes': fixtures, 'os': platform.platform(),
                    'guardian': options.guardian, 'instruction_variant': options.variant})
    save(run / 'result.json', report)
    for name, expected in fixtures.items():
        source = CORPUS.parent / name
        if digest(source) != expected:
            report['blockers'].append('fixture_checksum_mismatch')
            continue
        target = fixture_path(workspace, name)
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
    (run / 'prompt.txt').write_text(case['prompt'] + '\n')
    if (options.variant == 'baseline') != (options.instructions is None):
        report['blockers'].append('variant_requires_explicit_instruction_file')
    elif options.instructions:
        try:
            instructions = Path(options.instructions).read_bytes()
            if not instructions.strip() or len(instructions) > 65536: raise ValueError('invalid_instructions')
            instructions.decode('utf-8')
            (workspace / 'AGENTS.md').write_bytes(instructions)
            report['provenance']['instruction_file_sha256'] = hashlib.sha256(instructions).hexdigest()
        except (OSError, ValueError, UnicodeError):
            report['blockers'].append('instruction_file_unavailable')
    report['provenance']['harness_sha256'] = {path.name: digest(path) for path in
        [Path(__file__), Path(__file__).with_name('capability_observer.py'), Path(__file__).with_name('capability_actions.py')]}
    if (platform.system(), platform.machine()) != ('Darwin', 'arm64'):
        report['blockers'].append('macos_arm64_required')
    if not Path(options.codex_home).expanduser().is_dir():
        report['blockers'].append('persistent_codex_home_missing')
    for name in ('launcher', 'codex'):
        try:
            report['provenance'][name] = version(getattr(options, name))
        except (OSError, ValueError, subprocess.SubprocessError):
            report['blockers'].append(name + '_version_unavailable')
    try:
        report['provenance'].update(environment(options))
        if options.case in ('03', '04') and not any(item['presentation'] for item in report['provenance']['skills']):
            report['blockers'].append('presentation_skill_missing')
        if options.case in ('03', '04') and report['provenance']['node'] is None:
            report['blockers'].append('presentation_node_runtime_missing')
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        report['blockers'].append('environment_inventory_unavailable')
    try:
        protocol_args = [options.launcher, 'evaluation-protocol']
        if options.client == 'desktop': protocol_args += ['--app-bundle', options.app_bundle or '']
        protocol = subprocess.run(protocol_args, capture_output=True, timeout=10)
        if protocol.returncode or json.loads(protocol.stdout).get('version') != 1:
            raise ValueError('unsupported_bound')
        catalog = subprocess.run([options.launcher, 'models'], capture_output=True, timeout=30)
        if catalog.returncode: raise ValueError('catalog_unavailable')
        models = [line.split('\t')[0] for line in catalog.stdout.decode().splitlines()]
        if any(model not in models for model in (options.model, options.guardian)):
            report['blockers'].append('model_or_guardian_unavailable')
        if options.client == 'desktop' and 'nvidia/Nemotron-3_5-Lightning' not in models:
            report['blockers'].append('independent_naming_unavailable')
        report['provenance']['catalog_sha256'] = fingerprint(sorted(models))
        report['catalog_checked_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        report['blockers'].append('launcher_bound_or_catalog_unavailable')
    if options.client == 'desktop':
        try:
            bundle = Path(options.app_bundle)
            plist = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
            report['provenance']['desktop'] = {
                'version': plist['CFBundleShortVersionString'], 'build': plist['CFBundleVersion'],
                'executable_sha256': digest(bundle / 'Contents/MacOS/ChatGPT'),
                'application_sha256': digest(bundle / 'Contents/Resources/app.asar'),
                'engine': version(options.codex)}
            packaged = bundle / 'Contents/Resources/codex-cli'
            engine = (packaged / 'CodexCLI.app/Contents/MacOS/codex' if packaged.exists()
                      else bundle / 'Contents/Resources/codex')
            if engine.resolve() != Path(options.codex).resolve():
                report['blockers'].append('bundled_engine_mismatch')
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            report['blockers'].append('desktop_inventory_unavailable')
    if options.compare_with:
        try:
            previous = json.loads((Path(options.compare_with) / 'result.json').read_text())
            if (not isinstance(previous, dict) or previous.get('schema') != report['schema'] or
                    not isinstance(previous.get('provenance'), dict)):
                raise ValueError('invalid_comparison')
            compared = ('launcher', 'codex', 'desktop', 'os', 'settings', 'skills', 'python', 'node', 'shell',
                        'environment_sha256', 'catalog_sha256', 'guardian', 'harness_sha256', 'corpus_sha256')
            report['drift'] = [key for key in compared if previous['provenance'].get(key) != report['provenance'].get(key)]
            if report['drift']: report['blockers'].append('environment_drift')
        except (OSError, ValueError, UnicodeError):
            report['blockers'].append('comparison_unavailable')
    report['status'] = 'infra_blocked' if report['blockers'] else 'ready'
    save(run / 'preflight.json', report)
    save(run / 'result.json', report)
    return run, report


def protected_settings(options):
    home = Path(options.codex_home).expanduser()
    launcher_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'tofa'
    paths = [home / name for name in ('config.toml', 'auth.json')]
    paths += [launcher_home / name for name in ('config.yml', 'credentials.yml')]
    return [digest(path) if path.is_file() else None for path in paths]


def finish_report(run, report, observer, code, preserved):
    report.update(requests=observer.records, actions=observer.actions, exit_code=code,
                  elapsed_ms=observer.elapsed(), stop_reason=observer.reason, settings_preserved=preserved)
    forwarded = [r for r in observer.records if r.get('forwarded')]
    report['usage'] = {key: sum(r['usage'][key] for r in forwarded)
        if forwarded and all(key in r.get('usage', {}) for r in forwarded) else None
        for key in ('input_tokens', 'output_tokens')}
    report['usage']['complete'] = all(value is not None for value in report['usage'].values())
    report['request_counts'] = {role: sum(r.get('role') == role and r.get('forwarded', False)
        for r in observer.records) for role in ('main', 'guardian', 'auxiliary_title')}
    failures = [r['failure'] for r in observer.records if r.get('failure')]
    reason = observer.reason
    infra = any(value.startswith(('unsupported_', 'unmatched_', 'workspace_', 'scope_')) or
                value in ('stream_failure', 'upstream_http_error', 'response_incomplete',
                          'instruction_variant_missing') for value in failures)
    completed = any(r.get('completed') and r.get('final_answer') and r.get('role') == 'main' for r in observer.records)
    if not preserved:
        report['blockers'].append('protected_settings_changed')
    if infra or report['blockers'] or not preserved or not observer.records:
        report['status'] = 'infra_blocked'
    elif reason in ('operator_cancelled', 'client_disconnected'):
        report['status'] = 'cancelled'
    elif reason not in (None, 'operator_finished') or not completed or (code != 0 and reason != 'operator_finished'):
        report['status'] = 'failed'
    else:
        report['status'] = 'completed'
    criteria = report['criteria']
    if report['cell']['case'] in ('05', '07'):
        intact = all(not path.is_symlink() and path.is_file() and digest(path) == expected
            for name, expected in report['provenance']['fixture_hashes'].items()
            for path in [fixture_path(run / 'workspace', name)])
        criteria['file_integrity'] = dict(status='passed' if intact else 'failed',
                                          reason='fixtures_unchanged' if intact else 'fixture_changed')
    if (run / 'final.txt').exists() and report['cell']['case'] == '05':
        text = (run / 'final.txt').read_text()
        names = ('sample-deck.pptx', 'sample-deck.pdf')
        linked = all(re.search(r'\[[^\]]+\]\(' + re.escape(str(run / 'workspace/fixtures' / name)) + r'\)', text)
                     for name in names)
        terminal = all('fixtures/' + name in text for name in names)
        passed = linked if report['cell']['client'] == 'desktop' else terminal
        criteria['reference_syntax'] = dict(status='passed' if passed else 'failed',
            reason='absolute_markdown_links' if linked else 'terminal_paths' if terminal else 'missing_references')
    criteria['repetition'] = dict(status='failed' if observer.actions['max_no_progress_streak'] >= 5 else
                                  'passed' if completed else 'inconclusive', reason='observed_action_equivalence')
    if report['cell']['case'] == '07':
        good = (observer.actions['probe_failure_observed'] and criteria['file_integrity']['status'] == 'passed'
                and observer.actions['diagnostic_calls'] <= 3
                and not observer.actions['repeated_unchanged_action'])
        criteria['recovery'] = dict(status='passed' if good else 'failed', reason='diagnostic_rule',
                                   semantic_explanation='operator_check_pending')
    save(run / 'result.json', report)


def execute(options, run, report):
    from capability_observer import Observer
    if not options.live:
        report['blockers'].append('explicit_live_mode_required')
    if report['blockers']:
        report['status'] = 'infra_blocked'; save(run / 'result.json', report); return
    before = protected_settings(options)
    workspace = run / 'workspace'
    binary = Path(options.launcher).resolve()
    env = dict(os.environ, CODEX_HOME=str(Path(options.codex_home).expanduser().resolve()))
    shim = run / 'bin'; shim.mkdir()
    executable = shim / 'codex'
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(Path(options.codex).resolve())) + ' "$@"\n')
    executable.chmod(0o700)
    env['PATH'] = str(shim) + os.pathsep + env.get('PATH', '')
    code = None
    with Observer(run, model=options.model, guardian=options.guardian, limits=report['limits'], case=options.case) as observer:
        config = run / 'observer.json'
        save(config, dict(version=1, endpoint=observer.url, secret=observer.secret, seconds=report['limits']['seconds']))
        target = 'codex' if options.client == 'cli' else 'codex-desktop'
        command = [str(binary), 'launch', target, '--model', options.model, '--guardian-model', options.guardian,
                   '--allow-unverified', '--evaluation-observer', str(config)]
        if options.client == 'cli':
            command += ['--', '--sandbox', 'workspace-write', 'exec', '--skip-git-repo-check', '--json', '-']
        else:
            command += ['--app-bundle', str(Path(options.app_bundle).resolve())]
            print('Create a NEW conversation in workspace: ' + str(workspace) +
                  '\nUse the exact prompt in: ' + str(run / 'prompt.txt') +
                  '\nAfter the turn and naming finish, use the evaluator finish command for this run.', file=sys.stderr)
        process = None
        log_path = run / 'client.log'
        try:
            with log_path.open('wb') as log:
                process = subprocess.Popen(command, cwd=workspace, env=env, start_new_session=True,
                    stdin=subprocess.PIPE if options.client == 'cli' else subprocess.DEVNULL, stdout=log, stderr=log)
                if process.stdin:
                    process.stdin.write((run / 'prompt.txt').read_bytes()); process.stdin.close()
                while process.poll() is None:
                    if (run / 'cancel.request').exists(): observer.stop('operator_cancelled')
                    elif (run / 'finish.request').exists(): observer.stop('operator_finished')
                    if log_path.stat().st_size > 64 * 1024 * 1024: observer.stop('client_output_limit')
                    if observer.reason:
                        if options.client == 'cli': os.killpg(process.pid, signal.SIGTERM)
                        else: process.terminate()  # Launcher retains native Desktop ownership checks.
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=5)
                        break
                    try: process.wait(timeout=.1)
                    except subprocess.TimeoutExpired: pass
                code = process.returncode
        except KeyboardInterrupt:
            observer.stop('operator_cancelled')
        except (OSError, ValueError, subprocess.SubprocessError):
            report['blockers'].append('client_launch_failure')
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            try: preserved = before == protected_settings(options)
            except OSError: preserved = False
            try:
                after = environment(options)
                report['environment_drift_during_run'] = [key for key, value in after.items()
                    if report['provenance'].get(key) != value]
                if report['environment_drift_during_run']: report['blockers'].append('environment_drift_during_run')
            except (OSError, ValueError, subprocess.SubprocessError):
                report['blockers'].append('final_inventory_unavailable')
    finish_report(run, report, observer, code, preserved)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('preflight')
    prepare.add_argument('--private-root', required=True)
    prepare.add_argument('--case', required=True, choices=('03', '04', '05', '07'))
    prepare.add_argument('--client', required=True, choices=('cli', 'desktop'))
    prepare.add_argument('--model', required=True)
    prepare.add_argument('--guardian', default='zai-org/GLM-5.3-Flash')
    prepare.add_argument('--variant', default='baseline')
    prepare.add_argument('--instructions', help='explicit additive workspace instruction file for a named variant')
    prepare.add_argument('--launcher', required=True)
    prepare.add_argument('--codex', required=True)
    prepare.add_argument('--app-bundle')
    prepare.add_argument('--skill-root', action='append')
    prepare.add_argument('--codex-home', default=os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    prepare.add_argument('--compare-with')
    live = commands.add_parser('run', parents=[prepare], add_help=False)
    live.add_argument('--live', action='store_true', help='explicitly authorize this bounded inference attempt')
    for mode in ('cancel', 'finish'):
        control = commands.add_parser(mode)
        control.add_argument('run', type=Path)
    observe = commands.add_parser('observe')
    observe.add_argument('run', type=Path)
    observe.add_argument('--operator', required=True)
    observe.add_argument('--criterion', choices=DIMENSIONS, required=True)
    observe.add_argument('--status', choices=('passed', 'failed', 'inconclusive', 'unsupported'), required=True)
    observe.add_argument('--reason', required=True, help='short categorical code; no private text')
    export = commands.add_parser('export')
    export.add_argument('run', type=Path)
    export.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.command in ('cancel', 'finish'):
        if not (options.run / 'result.json').is_file(): raise ValueError('unknown_run')
        with (options.run / (options.command + '.request')).open('x') as stream: stream.write(options.command)
        return 0
    if options.command in ('observe', 'export'):
        report = json.loads((options.run / 'result.json').read_text())
        if report.get('schema') != 'tofa-capability-v1': raise ValueError('unknown_report_schema')
        if options.command == 'observe':
            for value in (options.operator, options.reason):
                if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value): raise ValueError('invalid_observation_code')
            observation = dict(id=uuid.uuid4().hex, operator=options.operator, criterion=options.criterion,
                status=options.status, reason=options.reason,
                observed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            path = options.run / ('observation-' + observation['id'] + '.json')
            with path.open('x') as stream: json.dump(observation, stream)
            print(json.dumps(observation))
            return 0
        observations = [json.loads(path.read_text()) for path in options.run.glob('observation-*.json')]
        observations.sort(key=lambda item: (item['observed_utc'], item['id']))
        report['observations'] = observations
        for item in observations:
            report['criteria'][item['criterion']] = {key: item[key] for key in ('status', 'reason', 'operator')}
        with options.output.open('x') as stream: json.dump(report, stream, indent=2)
        return 0
    run, report = preflight(options)
    if options.command == 'run': execute(options, run, report)
    print(json.dumps(report))
    return int(report['status'] not in ('ready', 'completed'))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Capability evaluation failed: invalid input or local IO; no fallback.', file=sys.stderr)
        sys.exit(1)
