"""Verify, restore and prepare a frozen private kit. Never launch Desktop.

kit.json is an explicitly reviewed declaration, not a discovery mechanism. Hashes
bind every executable/import and recipe; model identities are selections, not gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

RUN_ROOT = Path('/tmp/tofa-presentation-validation')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(root, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or '..' in path.parts:
        raise ValueError('invalid kit relative path')
    root = root.resolve()
    target = root / path
    if any((root / part).is_symlink() for part in (path, *path.parents)) or not target.is_file():
        raise ValueError('kit requires regular files without symlinks: ' + relative)
    return target


def declaration(kit):
    plan = json.loads(regular(kit, 'kit.json').read_text())
    if plan.get('schema') != 'tofa-qualification-kit-v1':
        raise ValueError('unsupported kit schema')
    if not re.fullmatch('[0-9a-f]{40}', plan['source_revision']):
        raise ValueError('full candidate revision required')
    if (plan['run_root'] != str(RUN_ROOT) or plan['seconds'] != 600
            or plan['automatic_retries'] != 0 or plan['retain_credentials'] is not True
            or not 1 <= plan['requests'] <= 80 or not 1 <= plan['output_tokens'] <= 8192):
        raise ValueError('invalid run bounds or retention policy')
    durable = Path(plan['durable_root'])
    if not durable.is_absolute() or not durable.is_dir() or durable.resolve().is_relative_to(Path('/tmp').resolve()):
        raise ValueError('durable root must exist outside /tmp')
    if not plan['prompt'].strip() or not re.fullmatch('[a-z-]+', plan['case']):
        raise ValueError('case and exact prompt required')
    for name in ('model', 'guardian'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', plan[name]):
            raise ValueError('explicit model role required')
    for name in ('app_bundle', 'runtime_root'):
        if not Path(plan[name]).is_absolute():
            raise ValueError('absolute environment paths required')
    for name in ('launcher', 'collector', 'model_services'):
        if plan[name] not in plan['files']:
            raise ValueError('unbound required kit file: ' + name)
    return plan


def check(kit):
    plan = declaration(kit)
    for relative, expected in plan['files'].items():
        if not re.fullmatch('[0-9a-f]{64}', expected) or digest(regular(kit, relative)) != expected:
            raise ValueError('pinned kit hash mismatch: ' + relative)
    scripts = (kit / plan['collector']).parent
    for path in scripts.rglob('*'):
        if path.is_file() or path.is_symlink():
            if str(path.relative_to(kit)) not in plan['files']:
                raise ValueError('unbound collector dependency')
    # Fail on import errors before human setup; no environment snapshot or launch.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONPATH='')
    result = subprocess.run([sys.executable, '-B', '-s', '-c',
        'import importlib.util,sys; sys.path.insert(0,sys.argv[1]); '
        's=importlib.util.spec_from_file_location("collector_preflight",sys.argv[2]); '
        'm=importlib.util.module_from_spec(s); s.loader.exec_module(m)',
        str(scripts), str(kit / plan['collector'])], cwd=scripts, env=env,
        capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('collector_import_failed; inspect the frozen collector dependencies')
    return plan


def restore(kit):
    plan = check(kit)
    parent = RUN_ROOT / 'guides'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = Path(tempfile.mkdtemp(prefix='kit.', dir=parent))
    try:
        for relative in (*plan['files'], 'kit.json'):
            source = regular(kit, relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(source, target)
        check(destination)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'kit': str(destination), 'desktop_launched': False, 'next_action': 'check_or_prepare'}


def prepare(kit):
    plan = check(kit)
    if plan['case'] != 'clean-exit':
        raise ValueError('this guide supports clean-exit only; other cases need a reviewed case guide')
    if plan['prompt'] != 'Reply exactly: tofa-clean-exit-ok. Do not use tools or create files.':
        raise ValueError('clean-exit guide requires its fixed smoke prompt')
    if not (Path(plan['app_bundle']) / 'Contents/Info.plist').is_file():
        raise ValueError('Desktop application missing')
    if not (Path(plan['runtime_root']) / 'runtime.json').is_file():
        raise ValueError('supplied runtime missing')
    # This public collector action allocates a fresh workspace only. Snapshot and
    # launch remain separate actions, after explicit human workspace setup.
    args = [sys.executable, '-B', str(kit / plan['collector']), 'prepare', '--defer-snapshot']
    for key in ('launcher', 'model_services'):
        args += ['--' + key.replace('_', '-'), str(kit / plan[key])]
    for key in ('app_bundle','runtime_root','source_revision','case','model','guardian',
                'seconds','requests','output_tokens','prompt'):
        args += ['--' + key.replace('_', '-'), str(plan[key])]
    result = subprocess.run(args, cwd=kit, capture_output=True, text=True, timeout=60)
    archive = Path(plan['durable_root']) / 'preparations'
    archive.mkdir(mode=0o700, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='prepare.', dir=archive))
    (attempt / 'collector.stdout').write_text(result.stdout)
    (attempt / 'collector.stderr').write_text(result.stderr)
    (attempt / 'kit.json').write_bytes((kit / 'kit.json').read_bytes())
    if result.returncode:
        raise ValueError('preparation_failed_before_launch; private diagnostics: ' + str(attempt))
    record = json.loads(result.stdout)
    run = Path(record['run'])
    if not run.resolve().is_relative_to((RUN_ROOT / 'runs').resolve()) or record.get('desktop_launched') is not False:
        raise ValueError('unexpected preparation result')
    if any((run / name).exists() for name in ('start.json', 'finish.json', 'collection.json')):
        raise ValueError('attempt_consumed_no_retry')
    binding = {'schema': 'tofa-kit-binding-v1', 'kit_sha256': digest(kit / 'kit.json')}
    with (run / 'kit-binding.json').open('x') as stream:
        json.dump(binding, stream)
    record['durable_preparation'] = str(attempt)
    (attempt / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def status(kit, run):
    plan = declaration(kit)
    if run is None:
        return {'desktop_launched': False, 'next_action': 'check_then_prepare', 'source_revision': plan['source_revision']}
    if not run.resolve().is_relative_to((RUN_ROOT / 'runs').resolve()):
        raise ValueError('run outside established temporary root')
    if not run.exists():
        return {'desktop_launched': False, 'next_action': 'review_durable_evidence_then_prepare_fresh', 'status':'temporary_run_missing'}
    binding = json.loads(regular(run, 'kit-binding.json').read_text())
    if binding.get('kit_sha256') != digest(kit / 'kit.json'):
        raise ValueError('run belongs to another kit declaration')
    consumed = any((run / name).exists() for name in ('start.json','finish.json','collection.json','declaration.json','launcher-process.json'))
    return {'desktop_launched': False, 'status': 'consumed' if consumed else 'prepared',
            'next_action': 'review_retained_evidence' if consumed else 'workspace_setup_then_explicit_launch',
            'run': str(run)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check','restore','prepare','status'))
    parser.add_argument('--kit', required=True, type=Path)
    parser.add_argument('--run', type=Path, help='status only; never resumes an attempt')
    options = parser.parse_args()
    if options.run and options.action != 'status': parser.error('--run is status-only')
    kit = options.kit.absolute()
    os.umask(0o077)
    try:
        if options.action == 'check':
            plan = check(kit)
            result = {'status':'checked', 'desktop_launched':False, 'source_revision':plan['source_revision']}
        elif options.action == 'restore': result = restore(kit)
        elif options.action == 'prepare': result = prepare(kit)
        else: result = status(kit, options.run)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Kit stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
