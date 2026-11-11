"""Capture exact system-skill inventories from explicitly selected installed engines.

Only initialize each engine in an owned temporary HOME with file-only, absent
credentials. Never start Desktop, run a turn, or touch the ordinary profile.
The output is private maintainer evidence, not a security attestation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time

ROOT = Path('/tmp/tofa-presentation-validation/checks/system-skills')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def capture(engine):
    engine = engine.resolve(strict=True)
    if not engine.is_file() or not os.access(engine, os.X_OK):
        raise ValueError('executable_engine_required')
    original = digest(engine)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=ROOT, prefix='inventory-') as temporary:
        root = Path(temporary); home = root/'codex'; home.mkdir(mode=0o700)
        (home/'config.toml').write_text('cli_auth_credentials_store="file"\n')
        env = {'HOME':str(root), 'CODEX_HOME':str(home), 'PATH':os.defpath,
               'TMPDIR':str(root), 'XDG_CONFIG_HOME':str(root/'config')}
        version = subprocess.check_output([str(engine),'--version'], env=env, cwd=root, timeout=10).decode().strip()
        request = {'id':1,'method':'initialize','params':{
            'clientInfo':{'name':'tofa_system_skills_inventory','version':'1'},
            'capabilities':{'experimentalApi':True}}}
        with (root/'stderr').open('wb') as log:
            process = subprocess.Popen([str(engine),'app-server','-c','features.shell_snapshot=false'],
                env=env,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
            try:
                process.stdin.write((json.dumps(request)+'\n').encode()); process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    data = b''; deadline = time.monotonic()+15
                    while b'\n' not in data:
                        remaining = deadline-time.monotonic()
                        if remaining <= 0 or not selector.select(remaining): raise ValueError('engine_initialize_timeout')
                        chunk = os.read(process.stdout.fileno(),65536)
                        if not chunk: raise ValueError('engine_initialize_closed')
                        data += chunk
                        if len(data)>1024*1024: raise ValueError('engine_initialize_too_large')
                    response = json.loads(data.split(b'\n',1)[0])
                    if response.get('id')!=1 or not isinstance(response.get('result'),dict):
                        raise ValueError('engine_initialize_failed')
            finally:
                try:
                    process.stdin.close()
                finally:
                    try:
                        if process.poll() is None:
                            try: os.killpg(process.pid,signal.SIGTERM)
                            except ProcessLookupError: pass
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid,signal.SIGKILL); process.wait()
                    finally:
                        process.stdout.close()
        files = {}
        system = home/'skills/.system'
        if system.is_symlink() or not system.is_dir(): raise ValueError('system_skills_not_generated')
        for path in sorted(system.rglob('*')):
            if path.is_symlink(): raise ValueError('generated_skill_symlink')
            if '__pycache__' in path.parts or path.suffix=='.pyc': continue
            if path.is_dir(): continue
            if not path.is_file(): raise ValueError('generated_skill_not_regular')
            files[str(path.relative_to(home/'skills'))] = digest(path)
        if '.system/.codex-system-skills.marker' not in files or not 2 <= len(files) <= 4096:
            raise ValueError('generated_inventory_incomplete')
        if digest(engine)!=original: raise ValueError('engine_changed_during_inventory')
        return {'engine':str(engine),'engine_sha256':original,'version':version,'files':files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if not 1 <= len(args.engine) <= 4: parser.error('select one to four installed engines')
    if args.output.exists(): raise ValueError('refuse_existing_contract')
    sources = [capture(engine) for engine in args.engine]
    descriptor = os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as output:
        json.dump({'schema':'tofa-generated-system-skills-v1','sources':sources},output,indent=2)
        output.write('\n');output.flush();os.fsync(output.fileno())
    print(json.dumps({'engines':len(sources),'files':[len(s['files']) for s in sources],
                      'desktop_launched':False,'inference':False}))


if __name__=='__main__': main()
