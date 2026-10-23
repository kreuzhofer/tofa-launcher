"""Local human-guidance helpers; never control an application or grant a pass."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import stat
import sys
import tarfile
import time

from desktop_qualification import private_run, read as private_read, save

CANDIDATE_NAME = '372255f'
HASHES = {'tofa': '7e74232c325b32b5f8c0c6ada314fdb05cc6191c5c1a05f01f0ec61678823b1f', 'source.tar': 'ef0e4738ed5ab65986512892bf460d6a4b3a34cceca1c0e08ec496e019a9f401'}


def read(path):
    return json.loads(path.read_text())


def alive(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    return True


def launcher_refusal(run):
    log = run/'launcher.log'
    if not log.exists(): return None
    # Report a known launcher refusal, never echo arbitrary private diagnostics.
    with log.open() as stream:
        for line in stream:
            if line.startswith('tofa: ordinary desktop profile is already owned or has an unresolved native lock.'):
                return 'ordinary_profile_owned_or_unresolved_lock'
    return None


def ensure_active(run, pid):
    if (run/'finish.json').exists(): raise ValueError('attempt ended')
    if (run/'declaration.json').exists():
        expiry = datetime.fromisoformat(read(run/'declaration.json')['expires_utc'].replace('Z','+00:00'))
        if datetime.now(timezone.utc) >= expiry: raise ValueError('attempt deadline reached')
    if not alive(pid):
        if launcher_refusal(run):
            raise ValueError('Desktop profile is in use or has an unresolved native lock. '
                             'Quit ChatGPT Desktop fully with Cmd-Q before a new attempt. '
                             'Do not delete locks or retry this consumed attempt; retain logs for review.')
        raise ValueError('collector stopped; retain logs for review')


def outcome(value):
    if value not in ('p', 'f', 'u'): raise ValueError('enter p, f, or u')
    return {'p':'passed','f':'failed','u':'not_observed'}[value]


def response(run, pid, prompt, choices):
    print(prompt, end=' ', file=sys.stderr, flush=True)
    while True:
        ensure_active(run, pid)
        if not select.select([sys.stdin], [], [], 0.25)[0]: continue
        line = sys.stdin.readline()
        if not line: raise ValueError('terminal input closed')
        ensure_active(run, pid)
        value = line.strip()
        if choices:
            try: return outcome(value)
            except ValueError:
                print('Enter p (passed), f (failed), or u (not observed):', file=sys.stderr, flush=True)
        elif not value: return ''
        else: print('Press Enter to continue.', file=sys.stderr, flush=True)


def check(kit):
    candidate = kit/'candidates'/CANDIDATE_NAME
    for name, expected in HASHES.items():
        if hashlib.sha256((candidate/name).read_bytes()).hexdigest() != expected:
            raise ValueError('pinned candidate hash mismatch: '+name)
    with tarfile.open(candidate/'source.tar') as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.startswith('scripts/'):
                target = candidate/'source'/member.name
                if target.is_symlink() or target.read_bytes() != archive.extractfile(member).read():
                    raise ValueError('frozen collector source mismatch')
    app = Path('/Applications/ChatGPT.app')
    if not (app/'Contents/Info.plist').is_file(): raise ValueError('host Desktop missing')
    roots = list((Path.home()/'.cache/codex-runtimes').glob('*/runtime.json'))
    if len(roots) != 1: raise ValueError('runtime discovery ambiguous or absent; agent review required')
    read(roots[0])
    print(roots[0].parent)


def summary(run):
    before = read(run/'before.json') if (run/'before.json').exists() else None
    after = read(run/'after.json') if (run/'after.json').exists() else None
    finish = read(run/'finish.json') if (run/'finish.json').exists() else None
    history = read(run/'history-after.json') if (run/'history-after.json').exists() else None
    def changed(left, right):
        return sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
    return {
        'schema':'tofa-manual-guide-summary-v1', 'run':str(run), 'qualified':False,
        'status':'awaiting_agent_review' if finish else 'incomplete_collection',
        'launcher_refusal':launcher_refusal(run),
        'stop':finish.get('stop') if finish else None,
        'exit_code':finish.get('exit_code') if finish else None,
        'process_exited_before_stop':finish.get('process_exited_before_stop') if finish else None,
        'observer_requests':finish.get('observer_requests') if finish else None,
        'identity_equal':before['identity']==after['identity'] if before and after else None,
        'protected_equal':before['protected']==after['protected'] if before and after else None,
        'identity_drift':changed(before['identity'].get('hashes', {}), after['identity'].get('hashes', {})) if before and after else None,
        'protected_drift':changed(before['protected'], after['protected']) if before and after else None,
        'existing_history_bytes_preserved':history['existing_bytes_preserved'] if history else None,
        'history_drift':history['changed'] if history else None,
        'observations':[{k:read(p)[k] for k in ('criterion','outcome','method')}
                        for p in sorted(run.glob('observation-*.json'))],
    }


def history_digest(path, length):
    # Existing bytes must survive; new turns may append after this prefix.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('history_symlink_not_supported')
    value = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise ValueError('history_regular_file_required')
        while length:
            chunk = stream.read(min(length, 1024 * 1024))
            if not chunk: raise ValueError('history_truncated')
            value.update(chunk); length -= len(chunk)
    return value.hexdigest()


def history_before(run):
    home = Path(private_read(run/'before.json')['identity']['home']).resolve()
    entries = {}
    def traversal_error(error):
        raise error
    for name in ('sessions', 'archived_sessions'):
        root = home/name
        if root.is_symlink(): raise ValueError('history_symlink_not_supported')
        if not root.exists(): continue
        if not root.is_dir(): raise ValueError('history_directory_required')
        for current, directories, files in os.walk(root, followlinks=False, onerror=traversal_error):
            for part in directories + files:
                path = Path(current)/part
                if path.is_symlink(): raise ValueError('history_symlink_not_supported')
            for name in files:
                path = Path(current)/name
                length = path.stat().st_size
                entries[str(path.relative_to(home))] = {'bytes':length, 'sha256':history_digest(path,length)}
    save(run/'history-before.json', {'schema':'tofa-history-prefix-v1','home':str(home),'entries':entries})


def history_after(run):
    before = private_read(run/'history-before.json')
    home = Path(before['home'])
    changed, hashes = [], {}
    for relative, entry in before['entries'].items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('sessions','archived_sessions'):
            raise ValueError('invalid_history_path')
        try: digest = history_digest(home/path, entry['bytes'])
        except (OSError, ValueError): digest = None
        hashes[relative] = digest
        if digest != entry['sha256']: changed.append(relative)
    save(run/'history-after.json', {'schema':'tofa-history-prefix-v1','existing_bytes_preserved':not changed,
                                   'changed':sorted(changed),'hashes':hashes})


def main():
    kit = Path(sys.argv.pop(1)).resolve()
    action = sys.argv[1]
    if action == 'check': return check(kit)
    if action == 'receipt':
        sources = [Path(__file__), Path(__file__).with_name('desktop_qualification_operator.sh')]
        save(Path(sys.argv[2])/'guide.json', {'schema':'tofa-manual-guide-v1','candidate':CANDIDATE_NAME,
             'candidate_hashes':HASHES,'guide_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
        return
    run = private_run(Path(sys.argv[2]))
    if action == 'history-before': return history_before(run)
    if action == 'history-after': return history_after(run)
    if action == 'summarize':
        value = summary(run)
        with (run/'guide-summary.json').open('x') as stream: json.dump(value, stream, indent=2)
        # Copy only after the collector has ended. Keep original evidence paths.
        archive = kit/'evidence'/run.name
        archive.parent.mkdir(mode=0o700, exist_ok=True)
        shutil.copytree(run, archive, symlinks=True)
        print(json.dumps(value, indent=2))
        print('Durable private copy: '+str(archive))
        return
    pid = int(sys.argv[3])
    if action in ('input','observe'):
        print(response(run, pid, sys.argv[4], action=='observe'))
    elif action == 'ready':
        # Includes up to 180 seconds for snapshot before the launch deadline starts.
        until = time.monotonic()+240
        while time.monotonic() < until:
            ensure_active(run, pid)
            if (run/'start.json').exists() and (run/'process.json').exists(): return
            time.sleep(0.25)
        raise ValueError('launch handoff unavailable; no prompt should be submitted')
    elif action == 'exited':
        receipt = read(run/'process.json')
        until = time.monotonic()+60
        while time.monotonic() < until:
            if not alive(receipt['native_pid']) and not alive(receipt['launcher_pid']): return
            ensure_active(run, pid)
            time.sleep(0.25)
        raise ValueError('normal exit was not observed within 60 seconds')
    else: raise ValueError('unknown guide action')


if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        print('Guide stopped: '+str(error), file=sys.stderr)
        sys.exit(1)
