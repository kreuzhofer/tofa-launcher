"""Run the installed presentation workflow from a captured actual loader result."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from presentation_runtime import from_loader_output, sha256


def private_generated(directory):
    # These two directories were exclusively created by this smoke invocation.
    # Never follow its installed node_modules dependency symlink.
    for parent, directories, files in os.walk(directory, followlinks=False):
        Path(parent).chmod(0o700)
        for name in list(directories):
            path=Path(parent)/name
            if path.is_symlink():
                if directory.name == 'build' and path == directory/'node_modules': directories.remove(name)
                else: raise ValueError('unexpected_generated_symlink')
        for name in files:
            path=Path(parent)/name
            if path.is_symlink() or not path.is_file(): raise ValueError('unexpected_generated_file')
            path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--skill', required=True, type=Path)
    parser.add_argument('--provider', required=True, choices=('codex_app', 'tofa_presentation_runtime'))
    parser.add_argument('--loader-result', required=True, type=Path)
    options = parser.parse_args()
    runtime = from_loader_output(json.loads(options.loader_result.read_text()), options.provider)
    paths = runtime['paths']
    workspace = options.workspace.resolve()
    # Apply only to newly generated owned evidence and inherited child writes.
    # No installed runtime/skill permissions are changed.
    if options.workspace.is_symlink() or not workspace.is_dir() or workspace.stat().st_uid != os.getuid():
        raise ValueError('owned_workspace_required')
    os.umask(0o077)
    build = workspace / 'build'; build.mkdir(mode=0o700)
    output = workspace / 'output'; output.mkdir(mode=0o700)
    (build / 'node_modules').symlink_to(paths['node_modules'], target_is_directory=True)
    source = build / 'presentation.mjs'
    shutil.copyfile(Path(__file__).parent / 'fixtures/presentation-smoke.mjs', source)
    env = dict(os.environ, RUNTIME_NODE=paths['node'], RUNTIME_NODE_MODULES=paths['node_modules'],
               RUNTIME_PYTHON=paths['python'], RUNTIME_BIN_DIR=paths['bin'], PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([paths['node'], 'container_tools/mark_artifact_operation_started.mjs',
                    '--operation-kind', 'create', '--expected-output-count', '1', '--output-format', 'pptx'],
                   cwd=options.skill, env=env, check=True, timeout=10)
    subprocess.run([paths['node'], str(source), str(workspace), str(options.skill.resolve())],
                   cwd=workspace, env=env, check=True, timeout=100)
    # PDF conversion is an explicit supplied-LibreOffice route. Artifact Tool's
    # native PDF export failed its retained bundle check; nothing is installed.
    subprocess.run([str(Path(paths['bin']) / 'soffice'),
                    '-env:UserInstallation=' + (workspace / 'libreoffice-profile').as_uri(),
                    '--headless', '--convert-to', 'pdf', '--outdir', str(workspace / 'output'),
                    str(workspace / 'output/deck.pptx')],
                   cwd=workspace, env=env, check=True, timeout=60)
    subprocess.run([str(Path(paths['bin']) / 'pdfinfo'), str(workspace / 'output/deck.pdf')],
                   cwd=workspace, env=env, check=True, timeout=10)
    private_generated(build); private_generated(output)
    print('TOFA_PRESENTATION_SMOKE_PASS ' + json.dumps({'schema': 'tofa-presentation-smoke-v1',
        'status': 'passed', 'artifacts': {name: sha256(workspace / 'output' / name) for name in
            ('deck.pptx', 'deck.pdf', 'slide.png')}}), flush=True)


if __name__ == '__main__': main()
