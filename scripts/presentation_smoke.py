"""Run the installed presentation workflow from a captured actual loader result."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from presentation_runtime import from_loader_output


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
    build = workspace / 'build'; build.mkdir()
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


if __name__ == '__main__': main()
