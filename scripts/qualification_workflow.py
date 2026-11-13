"""Read-only campaign preflight and bounded CI observation. Never launch or retry."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from qualification_reconcile import reference

OFFLINE_ACTIONS = {'prepare-guide', 'reconcile-evidence', 'offline-tests', 'review', 'commit', 'ci-watch'}


def preflight(path):
    plan = json.loads(path.read_text())
    if plan['schema'] != 'tofa-qualification-campaign-v1':
        raise ValueError('unsupported campaign schema')
    repo = Path(plan['repository'])
    if not repo.is_absolute() or not repo.is_dir(): raise ValueError('explicit repository directory required')
    repo = repo.resolve()
    prefix = ['git', '-C', str(repo)]
    if plan.get('author'):
        for key in ('name','email'):
            value = plan['author'][key]
            if not value.strip() or any(char in value for char in '\r\n\0'):
                raise ValueError('invalid process-only author identity')
            prefix += ['-c', 'user.' + key + '=' + value]
    def git(*args):
        result = subprocess.run([*prefix, *args], capture_output=True, text=True, timeout=10)
        if result.returncode: raise ValueError('repository preflight failed: ' + args[0])
        return result.stdout.strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != repo:
        raise ValueError('repository is not the declared checkout root')
    if git('branch', '--show-current') != plan['branch']:
        raise ValueError('integration branch mismatch')
    if not re.fullmatch('[0-9a-f]{40}', plan['head']) or git('rev-parse', 'HEAD') != plan['head']:
        raise ValueError('candidate head mismatch; review changes before a new campaign revision')
    if git('status', '--porcelain=v1', '--untracked-files=no'):
        raise ValueError('tracked changes present; review before changing the candidate')
    git('var', 'GIT_AUTHOR_IDENT')
    git('var', 'GIT_COMMITTER_IDENT')
    for tool in plan['tools']:
        if not Path(tool).is_absolute() or not Path(tool).is_file() or not os.access(tool, os.X_OK):
            raise ValueError('required executable unavailable')
    for entry in plan['accepted_evidence']: reference(path.parent, entry)
    if (plan['retain_credentials'] is not True or plan['automatic_retries'] != 0
            or plan['human_step_seconds'] != 600):
        raise ValueError('campaign contradicts retention or bounded-run policy')
    action = plan['next_action']
    return {'schema':'tofa-qualification-preflight-v1', 'candidate':plan['candidate'],
        'head':plan['head'], 'branch':plan['branch'], 'git_prefix':prefix,
        'untracked_count':sum(line.startswith('?? ') for line in git('status','--porcelain=v1','--untracked-files=all').splitlines()),
        'accepted_receipts_verified':len(plan['accepted_evidence']), 'next_action':action,
        'may_continue':action in OFFLINE_ACTIONS and action in plan['authorized_actions'],
        'desktop_launched':False, 'settings_changed':False,
        'authorization_note':'Recorded authority is scoped; this command executes no next action.'}


def watch(options):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', options.repository):
        raise ValueError('explicit owner/repository required')
    if not re.fullmatch('[0-9a-f]{40}', options.head) or options.run_id <= 0:
        raise ValueError('pinned run and full head required')
    if not 1 <= options.poll_seconds <= 60 or not 1 <= options.seconds <= 3600:
        raise ValueError('invalid observation bounds')
    options.output.mkdir(mode=0o700)  # exclusive attempt directory
    start, previous, number = time.monotonic(), None, 0
    while time.monotonic() - start < options.seconds:
        def get(suffix):
            response = subprocess.run([options.gh, 'api',
                f'repos/{options.repository}/actions/runs/{options.run_id}' + suffix],
                capture_output=True, text=True, timeout=min(30, max(0.1, options.seconds - (time.monotonic()-start))))
            if response.returncode: raise ValueError('CI observation failed; no retry requested')
            return json.loads(response.stdout)
        run = get('')
        if run['head_sha'] != options.head or run['id'] != options.run_id:
            raise ValueError('CI run identity mismatch')
        jobs = get('/jobs?filter=latest&per_page=100')
        if jobs.get('total_count', len(jobs['jobs'])) > len(jobs['jobs']):
            raise ValueError('CI jobs response incomplete')
        snapshot = {'run_id':run['id'], 'head':run['head_sha'], 'attempt':run['run_attempt'],
            'status':run['status'], 'conclusion':run['conclusion'],
            'jobs':[{'id':j['id'], 'name':j['name'], 'status':j['status'], 'conclusion':j['conclusion'],
                'steps':[{'name':s['name'],'status':s['status'],'conclusion':s['conclusion']} for s in j.get('steps',[])]}
                for j in jobs['jobs']], 'retry_performed':False}
        snapshot['eligible_failed_job_ids'] = [j['id'] for j in snapshot['jobs']
            if run['status'] == 'completed' and j['status'] == 'completed' and j['conclusion'] == 'failure']
        with (options.output / f'{number:04d}.json').open('x') as stream:
            json.dump(snapshot, stream, indent=2)
        number += 1
        if snapshot != previous:
            print(json.dumps(snapshot), flush=True)
            previous = snapshot
        if run['status'] == 'completed': return 0
        left = options.seconds - (time.monotonic() - start)
        if left > 0: time.sleep(min(options.poll_seconds, left))
    raise ValueError('CI observation deadline; retained snapshots are incomplete, no retry requested')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    check = commands.add_parser('preflight')
    check.add_argument('--campaign', required=True, type=Path)
    observer = commands.add_parser('watch-ci')
    observer.add_argument('--repository', required=True)
    observer.add_argument('--run-id', required=True, type=int)
    observer.add_argument('--head', required=True)
    observer.add_argument('--output', required=True, type=Path)
    observer.add_argument('--gh', default='gh')
    observer.add_argument('--seconds', type=int, default=600)
    observer.add_argument('--poll-seconds', type=int, default=10)
    options = parser.parse_args()
    os.umask(0o077)
    try:
        if options.action == 'preflight': print(json.dumps(preflight(options.campaign.resolve()), indent=2))
        else: return watch(options)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('Workflow stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__': sys.exit(main())
