"""Record the human's native Desktop preview observation, then end that owned run."""
import argparse
import json
import os
from pathlib import Path
import re
import time

from presentation_runtime import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--operator', required=True)
    parser.add_argument('--status', choices=('passed', 'failed', 'not_observed'), required=True)
    parser.add_argument('--pptx', type=Path, required=True)
    parser.add_argument('--pdf', type=Path, required=True)
    options = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', options.operator): raise ValueError('invalid_operator')
    run = options.run.resolve()
    files = {'deck.pptx': options.pptx, 'deck.pdf': options.pdf}
    for name, path in files.items():
        expected = run / 'workspace/output' / name
        if path.is_symlink() or path.resolve() != expected or not path.is_file():
            raise ValueError('preview_requires_exact_owned_artifacts')
        files[name] = expected
    observation = {'schema': 'tofa-native-presentation-preview-v1', 'operator': options.operator,
        'status': options.status, 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'files': {name: str(path) for name, path in files.items()},
        'artifacts': {name: sha256(path) for name, path in files.items()},
        'scope': 'human native PPTX and PDF preview observation; no other criterion is scored'}
    descriptor = os.open(run / 'operator.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream: json.dump(observation, stream, indent=2)
    descriptor = os.open(run / 'finish.request', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    print(json.dumps({'status': options.status, 'run': str(run), 'operator': options.operator}))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError) as error: raise SystemExit(str(error))
