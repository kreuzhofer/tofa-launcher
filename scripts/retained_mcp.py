"""Opt-in preservation exception for two lifecycle-verified MCP engine references.

Only these two files use semantic comparison; every other protected file keeps
its byte hash. This module never writes settings or repairs a missing bridge.
"""
import hashlib
import json
import os
from pathlib import Path

from presentation_runtime import sha256

LIFECYCLE = Path(__file__).parents[1] / 'docs/evaluation/evidence/presentation-runtime-126-127/retained-mcp-lifecycle.json'


def retained_policy(home, engine, bridge, native, evidence=LIFECYCLE):
    home, engine, bridge, evidence = map(Path, (home, engine, bridge, evidence))
    if not all(path.is_absolute() for path in (home, engine, bridge, evidence)):
        raise ValueError('retained_mcp_absolute_paths_required')
    owner_path = bridge.with_name('owner.json')
    for path in (bridge, owner_path):
        if (path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid() or
                path.stat().st_mode & 0o077):
            raise ValueError('retained_mcp_private_owned_bridge_required')
    if (bridge.parent.is_symlink() or bridge.parent.stat().st_uid != os.getuid() or
            bridge.parent.stat().st_mode & 0o077 or not os.access(bridge, os.X_OK)):
        raise ValueError('retained_mcp_private_owned_bridge_required')
    owner = json.loads(owner_path.read_text())
    bridge_hash = sha256(bridge)
    if (not isinstance(owner, dict) or owner.get('Version') != 2 or owner.get('LifecycleVersion') != 1 or
            owner.get('Engine') != str(engine) or owner.get('SHA256') != bridge_hash or
            owner.get('PendingSHA256') or bridge.name != 'tofa-desktop-engine' or
            bridge.parent.name != hashlib.sha256(str(engine).encode()).hexdigest() or
            bridge.parent.parent.name != 'desktop-bridge-v2'):
        raise ValueError('retained_mcp_owner_mismatch')
    if evidence.is_symlink() or not evidence.is_file():
        raise ValueError('retained_mcp_lifecycle_evidence_required')
    record = json.loads(evidence.read_text())
    try:
        phases, verification = record['phases'], record['verification']
        valid = (record['schema'] == 'tofa-retained-mcp-lifecycle-v1' and
            record['app_version'] == native['version'] and record['app_build'] == native['build'] and
            record['source_sha256']['launcher-retained'] == bridge_hash and
            record['tested_identity'] == {'engine_sha256': sha256(engine), 'native': native} and
            phases['crash']['crash'] is True and phases['crash']['protected_raw_equal'] is True and
            phases['clean_repeat']['protected_raw_equal'] is True and
            phases['ordinary_restart']['protected_normalized_equal'] is True and
            all(phases['uninstall'][key] is True for key in ('installation_removed', 'bridge_retained',
                'bridge_detached', 'synthetic_credentials_removed', 'shared_state_preserved')) and
            phases['uninstall']['exit_code'] == 0 and phases['uninstall']['ordinary_engine_exit'] == 0 and
            all(phases[phase][server]['initialize_and_arithmetic'] == 'passed'
                for phase in ('clean_exit', 'crash', 'uninstall') for server in ('node-repl', 'cua-repl')) and
            verification['real_cli_node_call']['exit_code'] == 0 and
            verification['real_cli_node_call']['marker_returned'] is True and
            verification['ordinary_engine_config']['ordinary_effective_config_equal'] is True and
            verification['ordinary_native_readiness']['ready'] > 0 and
            verification['ordinary_native_readiness']['failed'] == 0 and
            verification['ordinary_native_readiness']['peer_rejections'] == 0)
    except (KeyError, TypeError): valid = False
    if not valid: raise ValueError('retained_mcp_lifecycle_evidence_mismatch')
    if not engine.is_file() or not os.access(engine, os.X_OK):
        raise ValueError('retained_mcp_engine_unavailable')
    return {'schema': 'tofa-retained-mcp-policy-v1', 'home': str(home), 'engine': str(engine),
        'engine_sha256': sha256(engine), 'bridge': str(bridge), 'bridge_sha256': bridge_hash,
        'native': native, 'evidence': str(evidence), 'evidence_sha256': sha256(evidence),
        'plugin': str(home / 'plugins/cache/openai-bundled/unified-computer-use' / native['version'] / '.mcp.json')}


def validate_policy(policy, home):
    try:
        current = retained_policy(home, policy['engine'], policy['bridge'], policy['native'], policy['evidence'])
    except (KeyError, TypeError, OSError, ValueError) as error:
        raise ValueError('retained_mcp_policy_unavailable') from error
    if current != policy: raise ValueError('retained_mcp_policy_drift')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('retained_mcp_duplicate_json_key')
        result[key] = value
    return result


def typed_value(value):
    if isinstance(value, dict):
        return ['object', [[key, typed_value(item)] for key, item in sorted(value.items())]]
    if isinstance(value, list): return ['array', [typed_value(item) for item in value]]
    if hasattr(value, 'isoformat'): return [type(value).__name__, value.isoformat()]
    return [type(value).__name__, value]


def normalized_digest(path, policy):
    path = Path(path)
    if str(path) == str(Path(policy['home']) / 'config.toml'):
        route = ('mcp_servers', 'node_repl', 'env', 'CODEX_CLI_PATH')
        import tomllib
        parser = tomllib.loads
    elif str(path) == policy['plugin']:
        route = ('mcpServers', 'cua_repl', 'env', 'CODEX_CLI_PATH')
        parser = lambda text: json.loads(text, object_pairs_hook=unique_object)
    else: return sha256(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('retained_mcp_config_unavailable')
    try:
        document = parser(path.read_text())
        parent = document
        for key in route[:-1]: parent = parent[key]
        if parent[route[-1]] not in (policy['engine'], policy['bridge']):
            raise ValueError('retained_mcp_unverified_reference')
        parent[route[-1]] = policy['engine']
        # TOML date/time values retain their type, not just their printed value.
        encoded = json.dumps(typed_value(document))
    except (KeyError, TypeError) as error:
        raise ValueError('retained_mcp_reference_missing') from error
    return hashlib.sha256(encoded.encode()).hexdigest()
