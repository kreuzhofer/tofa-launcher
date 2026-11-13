"""Bound a CI lifecycle child and retain allowlisted failure diagnostics.

Raw stdout/stderr stay in the caller's owned scratch directory. Receipts never
contain command arguments, paths, environment variables or arbitrary output.
The caller owns cleanup of asynchronous uninstall helpers, as before.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

PHASES = ('fresh_probe_removed', 'fresh_probe_installed', 'uninstall_preserve', 'uninstall_purge')
MARKERS = {b'Checksum mismatch':'checksum_mismatch',
           b'Authentication operation active':'authentication_operation_active',
           b'Uninstaller started;':'uninstaller_started',
           b'Existing terminals may retain the old PATH entry.':'helper_completed'}


def stream_summary(path):
    if not path.is_file(): return {'bytes':0, 'sampled_bytes':0, 'markers':[]}
    with path.open('rb') as stream: sample = stream.read(8192)
    return {'bytes':path.stat().st_size, 'sampled_bytes':len(sample),
            'markers':[name for marker, name in MARKERS.items() if marker in sample]}


def run(job, phase, diagnostics):
    executable = Path(job['executable'])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('absolute executable required')
    # Uninstall may remove its own binary before returning a failure.
    executable_digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    args = job['arguments']
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        raise ValueError('argument array required')
    deadline = job['timeout_ms']
    if type(deadline) is not int or not 1 <= deadline <= 10000:
        raise ValueError('deadline must be between 1 and 10000 milliseconds')
    out, err = Path(job['stdout']), Path(job['stderr'])
    if out == err: raise ValueError('separate output paths required')
    process, failure = None, None
    started = time.monotonic()
    with out.open('xb') as stdout, err.open('xb') as stderr:
        try:
            process = subprocess.Popen([str(executable), *args], stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr)
            if process.wait(timeout=deadline / 1000) != 0: failure = 'nonzero_exit'
        except subprocess.TimeoutExpired:
            failure = 'timeout'
        except KeyboardInterrupt:
            failure = 'cancelled'
        except OSError:
            failure = 'start_failed'
        finally:
            if process and process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    failure = 'cleanup_failed'
    if failure:
        report = {'schema':'tofa-ci-process-failure-v1', 'phase':phase, 'outcome':failure,
            'executable_sha256':executable_digest,
            'pid':process.pid if process else None, 'deadline_ms':deadline,
            'elapsed_ms':round((time.monotonic() - started)*1000),
            'exit_code':process.returncode if process else None,
            'direct_process_exited':process is None or process.poll() is not None,
            'stdout':stream_summary(out), 'stderr':stream_summary(err)}
        diagnostics.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (diagnostics / (phase + '.' + uuid.uuid4().hex + '.json')).open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        print('Lifecycle process failed: ' + phase + ' / ' + failure, file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--phase', choices=PHASES, required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    options = parser.parse_args()
    os.umask(0o077)
    try:
        return run(json.loads(options.job.read_text(encoding='utf-8-sig')), options.phase, options.diagnostics)
    except (OSError, ValueError, KeyError, TypeError):
        print('Lifecycle process setup or receipt write failed; no success claimed.', file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
