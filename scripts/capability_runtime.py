"""Evidence validation for a particular actual-client presentation runtime lane."""
import hashlib
import json
from pathlib import Path
import zipfile
import subprocess
import plistlib

from presentation_runtime import from_loader_output, inventory, sha256

PROVIDERS = {'cli': 'tofa_presentation_runtime', 'desktop': 'codex_app'}


def harness_identity():
    directory = Path(__file__).parent
    names = ('presentation_calibration.py', 'presentation_runtime.py', 'presentation_smoke.py',
        'capability_runtime.py', 'presentation_preview.py', 'capability_observer.py',
        'capability_actions.py', 'capability_evaluation.py', 'evaluation_proxy.py')
    return {path.name: sha256(path) for path in [*(directory / name for name in names),
        directory / 'fixtures/presentation-smoke.mjs']}


def desktop_identity(bundle, engine):
    if bundle is None: raise ValueError('native_desktop_app_bundle_required')
    bundle = Path(bundle).resolve()
    packaged = bundle / 'Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
    if Path(engine).resolve() != packaged.resolve(): raise ValueError('native_bundled_engine_required')
    plist = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    return {'version': plist['CFBundleShortVersionString'], 'build': plist['CFBundleVersion'],
        'application_sha256': sha256(bundle / 'Contents/Resources/app.asar'),
        'executable_sha256': sha256(bundle / 'Contents/MacOS/ChatGPT'),
        'native_transport_sha256': sha256(bundle / 'Contents/Resources/plugins/openai-bundled/plugins/codex-app-tools/server.mjs')}


def executable_versions(runtime, workspace):
    """Probe only fixed supplied executables, with an owned LibreOffice profile."""
    paths = runtime['paths']
    commands = {
        'node': [paths['node'], '--version'],
        'python': [paths['python'], '-I', '-B', '--version'],
        'soffice': [str(Path(paths['bin']) / 'soffice'),
            '-env:UserInstallation=' + (workspace / 'version-profile').as_uri(), '--version'],
        'pdfinfo': [str(Path(paths['bin']) / 'pdfinfo'), '-v'],
        'pdftoppm': [str(Path(paths['bin']) / 'pdftoppm'), '-v'],
    }
    versions = {}
    for name, command in commands.items():
        result = subprocess.run(command, capture_output=True, timeout=10, cwd=workspace)
        output = (result.stdout + result.stderr).decode().strip()
        if result.returncode or not output or len(output) > 4096:
            raise ValueError('supplied_executable_version_failed')
        versions[name] = {'sha256': sha256(command[0]), 'version': output}
    if versions['node']['version'] != runtime['declared_versions']['node'] or (
            versions['python']['version'] != 'Python ' + runtime['declared_versions']['python']):
        raise ValueError('supplied_executable_version_mismatch')
    return versions


def protected(home, skill, runtime):
    files = [home / 'config.toml', home / 'auth.json']
    for root in (home / 'skills', home / 'plugins/cache', home.parent / '.agents/skills', skill, runtime):
        files += [path for path in root.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc']
    snapshot = {str(path): sha256(path) for path in set(files) if path.is_file()}
    return {'files': len(snapshot), 'sha256': hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()}


def loader_tools(body, provider):
    """Recognize the actual flat or namespaced MCP catalog, never a matching suffix."""
    namespace = 'mcp__' + provider
    full = namespace + '__load_workspace_dependencies'
    pending = [(None, tool) for tool in body.get('tools', [])]
    for item in body.get('input', []): pending += [(None, tool) for tool in item.get('tools', [])]
    result = []
    while pending:
        parent, tool = pending.pop()
        if tool.get('type') == 'namespace':
            pending += [(tool.get('name'), child) for child in tool.get('tools', [])]
        elif ((parent is None and tool.get('name') == full) or
              (parent == namespace and tool.get('name') == 'load_workspace_dependencies')):
            schema = tool.get('parameters', {})
            if (tool.get('type') == 'function' and schema.get('type') == 'object' and
                    schema.get('properties') == {} and schema.get('additionalProperties') is False and
                    not schema.get('required')):
                result.append(tool)
    return result


def loader_call(item, provider):
    return item.get('type') == 'function_call' and (
        (item.get('namespace') == 'mcp__' + provider and item.get('name') == 'load_workspace_dependencies') or
        (item.get('namespace') is None and item.get('name') == 'mcp__' + provider + '__load_workspace_dependencies'))


def read_json(path, limit=16 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('qualification_evidence_unavailable')
    return json.loads(path.read_text())


def qualify(path, *, client, client_identity, home, skill, application_identity=None):
    path = Path(path)
    if path.is_symlink(): raise ValueError('qualification_evidence_unavailable')
    path = path.resolve()
    proof = read_json(path)
    run = path.parent
    provider = PROVIDERS[client]
    if (not isinstance(proof, dict) or proof.get('schema') != 'tofa-presentation-qualification-v1' or proof.get('status') != 'qualified' or
            proof.get('client') != client or proof.get('client_identity') != client_identity or
            proof.get('run') != str(run) or proof.get('paid_inference') is not False or
            (proof.get('exit_code') != 0 and not (client == 'desktop' and proof.get('termination') == 'operator_finished')) or proof.get('failure') is not None or
            proof.get('loader_name') != 'mcp__' + provider + '__load_workspace_dependencies'):
        raise ValueError('qualification_identity_mismatch')
    if any(not isinstance(proof.get(name), dict) for name in
            ('runtime', 'observed_versions', 'preservation', 'artifacts', 'thread_identity')):
        raise ValueError('malformed_qualification_evidence')
    if client == 'desktop' and (proof.get('native') != application_identity or
                               proof.get('native_preview') != 'passed'):
        raise ValueError('native_desktop_qualification_incomplete')
    if not isinstance(proof.get('thread_identity', {}).get('id'), str):
        raise ValueError('actual_client_thread_unobserved')
    if client == 'desktop':
        observation = read_json(run / 'operator.json')
        if (sha256(run / 'operator.json') != proof.get('operator_sha256') or
                observation.get('schema') != 'tofa-native-presentation-preview-v1' or
                observation.get('status') != 'passed' or not observation.get('operator') or
                observation.get('artifacts') != {name: proof.get('artifacts', {}).get(name) for name in ('deck.pptx', 'deck.pdf')} or
                observation.get('files') != {name: str(run / 'workspace/output' / name) for name in ('deck.pptx', 'deck.pdf')}):
            raise ValueError('native_preview_evidence_mismatch')
    if proof.get('harness') != harness_identity():
        raise ValueError('qualification_harness_drift')
    output = read_json(run / 'loader-result.json')
    if sha256(run / 'loader-result.json') != proof.get('loader_result_sha256'):
        raise ValueError('qualification_loader_result_changed')
    runtime = from_loader_output(output, provider)
    if runtime != proof.get('runtime'): raise ValueError('qualification_runtime_drift')
    versions = proof.get('observed_versions', {})
    if set(versions) != {'node', 'python', 'soffice', 'pdfinfo', 'pdftoppm'}:
        raise ValueError('qualification_executable_versions_missing')
    for name, identity in versions.items():
        if not isinstance(identity, dict) or identity.get('sha256') != runtime['hashes'][name] or not identity.get('version'):
            raise ValueError('qualification_executable_identity_mismatch')
    if versions['node']['version'] != runtime['declared_versions']['node'] or (
            versions['python']['version'] != 'Python ' + runtime['declared_versions']['python']):
        raise ValueError('qualification_executable_version_mismatch')
    requests = sorted(run.glob('model-request-*.json'))
    observed_call = False
    for request in requests:
        body = read_json(request)
        if not loader_tools(body, provider): continue
        for call in body.get('input', []):
            if not loader_call(call, provider) or json.loads(call.get('arguments', 'null')) != {}: continue
            if any(item.get('type') == 'function_call_output' and item.get('call_id') == call.get('call_id') and
                   item.get('output') == output for item in body['input']): observed_call = True
    if not observed_call: raise ValueError('actual_client_loader_call_unobserved')
    preservation = proof.get('preservation', {})
    if not proof.get('settings_preserved') or preservation.get('before') != preservation.get('after') or (
            preservation.get('after') != protected(home, skill, Path(runtime['root']))):
        raise ValueError('qualification_protected_files_drift')
    artifacts = proof.get('artifacts', {})
    if set(artifacts) != {'deck.pptx', 'deck.pdf', 'slide.png'}: raise ValueError('qualification_artifacts_incomplete')
    for name, expected in artifacts.items():
        artifact = run / 'workspace/output' / name
        if artifact.is_symlink() or sha256(artifact) != expected:
            raise ValueError('qualification_artifact_changed')
    with zipfile.ZipFile(run / 'workspace/output/deck.pptx') as deck:
        if deck.testzip() or 'ppt/slides/slide1.xml' not in deck.namelist():
            raise ValueError('qualification_pptx_invalid')
    if not (run / 'workspace/output/deck.pdf').read_bytes().startswith(b'%PDF-'):
        raise ValueError('qualification_pdf_invalid')
    if not (run / 'workspace/output/slide.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('qualification_render_invalid')
    receipt = read_json(run / 'workspace/build/finalization.json')
    if (receipt.get('finalSha256') != artifacts['deck.pptx'] or
            receipt.get('packageIntegrity', {}).get('status') != 'pass' or
            receipt.get('firstPartyImport', {}).get('passed') is not True):
        raise ValueError('qualification_finalization_failed')
    return {'contract': 'qualified-presentation-runtime-v1', 'client': client, 'provider': provider,
            'runtime': runtime, 'proof_sha256': sha256(path), 'loader_result_sha256': proof['loader_result_sha256'],
            'proof_path': str(path), 'client_identity': client_identity, 'home': str(home), 'skill': str(skill),
            'application_identity': application_identity}
