"""Read-only, launcher-owned locator for an existing supplied presentation runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PROVIDER = 'tofa_presentation_runtime'
TOOL = 'load_workspace_dependencies'
PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
LIMIT = 1024 * 1024


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def metadata(path):
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError('runtime_metadata_unavailable')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('invalid_runtime_metadata')
    return value


def inventory(root):
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('runtime_root_requires_absolute_directory')
    root = root.resolve()
    manifest = metadata(root / 'runtime.json')
    if manifest.get('bundleFormatVersion') != 2 or isinstance(manifest.get('bundleFormatVersion'), bool):
        raise ValueError('unsupported_runtime_bundle_format')
    if (manifest.get('targetPlatform'), manifest.get('targetArch')) != ('darwin', 'arm64'):
        raise ValueError('unsupported_runtime_host')
    for key in ('bundleVersion', 'nodeVersion', 'pythonVersion', 'artifactToolVersion'):
        value = manifest.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,80}', value):
            raise ValueError('invalid_runtime_version')
    paths = {name: root / relative for name, relative in {
        'node': 'dependencies/node/bin/node', 'node_modules': 'dependencies/node/node_modules',
        'python': 'dependencies/python/bin/python3', 'python_packages': 'dependencies/python',
        'bin': 'dependencies/bin/override'}.items()}
    files = {'manifest': root / 'runtime.json', 'node': paths['node'], 'python': paths['python'],
             'artifact_package': paths['node_modules'] / '@oai/artifact-tool/package.json',
             'artifact_module': paths['node_modules'] / '@oai/artifact-tool/dist/artifact_tool.mjs'}
    files.update({name: paths['bin'] / name for name in ('soffice', 'pdfinfo', 'pdftoppm')})
    native = {'soffice': root / 'dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice',
              'pdfinfo': root / 'dependencies/native/poppler/bin/pdfinfo',
              'pdftoppm': root / 'dependencies/native/poppler/bin/pdftoppm'}
    files.update({'native_' + name: path for name, path in native.items()})
    for path in [*paths.values(), *files.values()]:
        if not path.exists() or root not in path.resolve().parents:
            raise ValueError('runtime_path_missing_or_outside_bundle')
    for name in ('node_modules', 'python_packages', 'bin'):
        if not paths[name].is_dir():
            raise ValueError('runtime_directory_missing')
    for name, path in files.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('runtime_file_missing')
        if (name in ('node', 'python', 'soffice', 'pdfinfo', 'pdftoppm') or name.startswith('native_')) and not path.stat().st_mode & 0o111:
            raise ValueError('runtime_executable_unavailable')
    package = metadata(files['artifact_package'])
    if package.get('name') != '@oai/artifact-tool' or package.get('version') != manifest['artifactToolVersion']:
        raise ValueError('runtime_package_identity_mismatch')
    return {'contract': 'supplied-presentation-runtime-v1', 'provider': PROVIDER,
            'root': str(root), 'bundle_version': manifest['bundleVersion'],
            'artifact_tool_version': package['version'],
            'declared_versions': {'node': manifest['nodeVersion'], 'python': manifest['pythonVersion']},
            'paths': {name: str(path) for name, path in paths.items()},
            'native_executables': {name: str(path) for name, path in native.items()},
            'hashes': {name: sha256(path) for name, path in files.items()}}


def instructions(runtime):
    paths = runtime['paths']
    return '\n'.join(['### Workspace Dependencies',
        'Provider: launcher-owned tofa_presentation_runtime (existing supplied bundle).',
        '- Bundle version: `' + runtime['bundle_version'] + '`',
        '- Node.js executable: `' + paths['node'] + '`',
        '- Node.js packages: `' + paths['node_modules'] + '`',
        '- Python executable: `' + paths['python'] + '`',
        '- Python packages: `' + paths['python_packages'] + '`',
        '- Override binaries: `' + paths['bin'] + '`'])


def from_loader_output(output, provider):
    """Validate the returned text against the actual bundle, for either owning provider."""
    if provider not in (PROVIDER, 'codex_app'):
        raise ValueError('unqualified_loader_provider')
    text = []
    def collect(value):
        if isinstance(value, str):
            text.append(value)
            if value.startswith('Wall time:') and '\nOutput:\n' in value:
                value = value.split('\nOutput:\n', 1)[1]
            try: decoded = json.loads(value)
            except (ValueError, TypeError): return
            if not isinstance(decoded, str): collect(decoded)
        elif isinstance(value, list):
            for item in value: collect(item)
        elif isinstance(value, dict):
            if value.get('isError') is True or value.get('success') is False:
                raise ValueError('loader_call_failed')
            if value.get('contract') == 'supplied-presentation-runtime-v1':
                if provider != PROVIDER or value != inventory(value.get('root', '')):
                    raise ValueError('returned_runtime_identity_mismatch')
                text.append(instructions(value))
            for key in ('content', 'contentItems', 'text', 'output'):
                if key in value: collect(value[key])
    collect(output)
    combined = '\n'.join(text)
    labels = {'node': 'Node.js executable', 'node_modules': 'Node.js packages',
              'python': 'Python executable', 'python_packages': 'Python packages', 'bin': 'Override binaries'}
    paths = {}
    for name, label in labels.items():
        matches = set(re.findall(r'(?m)^- ' + re.escape(label) + r': `([^`\n]+)`', combined))
        if len(matches) != 1: raise ValueError('incomplete_or_ambiguous_loader_result')
        paths[name] = matches.pop()
    node = Path(paths['node'])
    if not node.is_absolute() or tuple(node.parts[-4:]) != ('dependencies', 'node', 'bin', 'node'):
        raise ValueError('unsupported_loader_runtime_layout')
    runtime = inventory(node.parents[3])
    if any(runtime['paths'][name] != value for name, value in paths.items()):
        raise ValueError('loader_paths_do_not_match_bundle')
    versions = set(re.findall(r'(?m)^- Bundle version: `([^`\n]+)`', combined))
    if versions != {runtime['bundle_version']}: raise ValueError('loader_bundle_version_mismatch')
    runtime['provider'] = provider
    return runtime


def serve(root):
    initialized = False
    while True:
        line = sys.stdin.buffer.readline(LIMIT + 1)
        if not line: return
        request = None
        try:
            if len(line) > LIMIT: raise ValueError('request_limit')
            request = json.loads(line)
            if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
                raise ValueError('invalid_request')
            if 'id' not in request: continue
            method, params = request.get('method'), request.get('params', {})
            if not isinstance(params, dict): raise ValueError('invalid_params')
            if method == 'initialize':
                if params.get('protocolVersion') not in PROTOCOLS:
                    raise ValueError('unsupported_protocol_version')
                initialized = True
                result = {'protocolVersion': params['protocolVersion'], 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'tofa-presentation-runtime', 'version': '1'}}
            elif not initialized:
                raise ValueError('initialize_required')
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': [{'name': TOOL, 'description':
                    'Locate the existing supplied presentation runtime. Read-only; no installation; no arguments.',
                    'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}}]}
            elif method == 'tools/call':
                if params.get('name') != TOOL or params.get('arguments', {}) != {}:
                    raise ValueError('loader_requires_no_arguments')
                try:
                    runtime = inventory(root)
                    result = {'content': [{'type': 'text', 'text': instructions(runtime)}],
                              'structuredContent': runtime, 'isError': False}
                except (OSError, ValueError, UnicodeError) as error:
                    result = {'content': [{'type': 'text', 'text': 'Supplied runtime unavailable: ' +
                              (str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'invalid_local_runtime')}],
                              'isError': True}
            else:
                raise ValueError('unsupported_method')
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except (ValueError, TypeError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                        'error': {'code': -32602, 'message': 'Invalid or unsupported loader request.'}}
        print(json.dumps(response, separators=(',', ':')), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('mcp', 'describe'))
    parser.add_argument('--runtime-root', required=True, type=Path)
    options = parser.parse_args()
    if options.command == 'mcp': serve(options.runtime_root)
    else: print(json.dumps(inventory(options.runtime_root)))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, UnicodeError):
        print('Supplied presentation runtime validation failed; no fallback.', file=sys.stderr)
        sys.exit(1)
