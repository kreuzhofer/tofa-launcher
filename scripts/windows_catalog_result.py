"""Fail-closed publication boundary for synthetic catalog evidence."""
import re
from typing import Any
from windows_template_transport import Failure

CHECKS = ('provider_closed', 'diagnostics_written', 'provider_scope_preserved', 'cli_before', 'cli_during', 'cli_after_selection', 'selected_request', 'native_turn_completed',
          'mixed_refused', 'mixed_atomic', 'unrelated_native', 'cli_after_writes', 'replay_exited',
          'normal_quit', 'cli_after_shutdown', 'cli_exited', 'ordinary_config_preserved', 'vendor_service_preserved', 'owned_apps_exited')
STAGES = ('preparation', 'desktop', 'picker', 'request', 'settings', 'cleanup', 'complete')


def finalize_completion(value):
    """Measure completion from the final, quiescent native/provider evidence."""
    value['checks']['selected_request'] = value.get('requests') == [
        {'model': 'tofa-catalog-b', 'effort': 'high', 'path': '/responses'}]
    value['checks']['native_turn_completed'] = any(
        event.get('event') == 'turn_completed' and event.get('success') is True
        for event in value.get('events', []))


def sanitize(value):
    if not isinstance(value, dict) or value.get('production_gate') != 'blocked' or value.get('stage') not in STAGES:
        raise Failure('malformed_catalog_result')
    result = {'production_gate': 'blocked', 'stage': value['stage'], 'checks': {}}
    if 'last_work_stage' in value:
        if value['last_work_stage'] not in STAGES: raise Failure('malformed_catalog_result')
        result['last_work_stage'] = value['last_work_stage']
    checks = value.get('checks')
    if not isinstance(checks, dict): raise Failure('malformed_catalog_result')
    for key in CHECKS:
        if key in checks:
            if type(checks[key]) is not bool: raise Failure('malformed_catalog_result')
            result['checks'][key] = checks[key]
    requests = value.get('requests', [])
    if not isinstance(requests, list) or len(requests) > 16: raise Failure('malformed_catalog_result')
    result['requests'] = []
    for item in requests:
        if (not isinstance(item, dict) or item.get('model') not in ('tofa-catalog-a', 'tofa-catalog-b')
                or item.get('effort') not in ('low', 'high') or item.get('path') != '/responses'):
            raise Failure('malformed_catalog_result')
        result['requests'].append({key: item[key] for key in ('model', 'effort', 'path')})
    if 'picker' in value:
        picker = value['picker']
        if (not isinstance(picker, dict) or type(picker.get('ok')) is not bool
                or picker.get('stage') not in ('identity', 'model_button', 'model_choice', 'reasoning_button', 'reasoning_choice', 'complete')):
            raise Failure('malformed_catalog_result')
        result['picker'] = {key: picker[key] for key in ('ok', 'stage')}
        if 'mode' in picker:
            if picker['mode'] not in ('guided', 'automated'): raise Failure('malformed_catalog_result')
            result['picker']['mode'] = picker['mode']
        choices = picker.get('choices', [])
        if not isinstance(choices, list) or len(choices) > 2 or any(choice not in ('tofa-catalog-a', 'tofa-catalog-b') for choice in choices):
            raise Failure('malformed_catalog_result')
        result['picker']['choices'] = choices
    if 'identity' in value:
        identity = value['identity']
        if not isinstance(identity, dict) or any(not isinstance(identity.get(key), str) or not re.fullmatch('[0-9a-f]{64}', identity[key]) for key in ('engine_sha256', 'app_sha256')):
            raise Failure('malformed_catalog_result')
        result['identity'] = {key: identity[key] for key in ('engine_sha256', 'app_sha256')}
    events = value.get('events', [])
    if not isinstance(events, list) or len(events) > 512: raise Failure('malformed_catalog_result')
    result['protocol'] = []
    for event in events:
        if not isinstance(event, dict): raise Failure('malformed_catalog_result')
        kind = event.get('event')
        if not isinstance(kind, str): raise Failure('malformed_catalog_result')
        fields = {
            'catalog_advertised': ('models', 'complete'),
            'catalog_home': ('expected',),
            'catalog_layer_check': ('user_layers', 'matching_layers', 'version_present', 'exact_path', 'extended_path'),
            'catalog_default_write': ('method', 'keys', 'values', 'disposition', 'reload', 'versioned'),
            'catalog_selection': ('model', 'effort'),
            'catalog_background_turn_refused': ('category',),
            'catalog_unrelated_write': ('disposition',),
            'catalog_other_write_refused': ('keys',),
            'catalog_native_identity_refused': ('model', 'provider'),
            'tool_registration_refused': (), 'unrelated_turn_refused': ('reason',),
            'policy_refused': ('reason',), 'invalid_identity': (), 'invalid_observation': (),
            'turn_completed': ('success',),
            'thread_ready': ('model', 'provider', 'policy_verified', 'reviewer_verified', 'approval_verified', 'sandbox_verified', 'native_sandbox'),
            'synthetic_guard': ('thread_verified', 'sandbox_verified', 'model_verified'),
            'thread_settings_updated': ('model', 'provider', 'policy_verified'),
        }.get(kind)
        if fields is None: continue
        clean: dict[str, Any] = {'event': kind}
        for key in fields:
            if key not in event: continue
            item = event[key]
            # Only the owned synthetic protocol's bounded atoms leave the guest.
            atoms = item if isinstance(item, list) else [item]
            if len(atoms) > 16: raise Failure('malformed_catalog_result')
            allowed = {'tofa-catalog-a', 'tofa-catalog-b', 'tofa-catalog', 'openai', 'other',
                'low', 'high', 'medium', 'model', 'model_reasoning_effort', 'service_tier',
                'plan_mode_reasoning_effort', 'config/batchWrite', 'config/value/write',
                'session_override', 'pending', 'refused', 'native', 'unrelated_turn', 'synthetic_policy',
                'shared_write_unsupported', 'native_settings_changed', 'title', 'summary', 'unclassified'}
            allowed.update(('workspaceWrite', 'readOnly', 'dangerFullAccess', 'externalSandbox'))
            def atom(value):
                if value is None or type(value) is bool: return value
                if key in ('user_layers', 'matching_layers') and type(value) is int and 0 <= value <= 16: return value
                if isinstance(value, str) and value in allowed: return value
                if key == 'model' and isinstance(value, str) and re.fullmatch(r'gpt-[a-z0-9.-]{1,64}', value): return value
                return 'other'
            clean[key] = [atom(value) for value in atoms] if isinstance(item, list) else atom(item)
        result['protocol'].append(clean)
    return result


def validate(value):
    protocol = value.get('protocol', [])
    required_events = (
        {'event': 'catalog_advertised', 'models': ['tofa-catalog-a', 'tofa-catalog-b'], 'complete': True},
        {'event': 'catalog_selection', 'model': 'tofa-catalog-b', 'effort': 'high'},
        {'event': 'thread_settings_updated', 'model': 'tofa-catalog-b', 'provider': 'tofa-catalog', 'policy_verified': True},
        {'event': 'turn_completed', 'success': True},
    )
    if any(event not in protocol for event in required_events): raise Failure('catalog_observation_failed')
    if not any(event.get('event') == 'catalog_default_write' and event.get('disposition') == 'session_override'
               and 'model' in event.get('keys', []) and 'tofa-catalog-b' in event.get('values', []) for event in protocol):
        raise Failure('catalog_observation_failed')
    if (value['stage'] != 'complete' or any(value['checks'].get(key) is not True for key in CHECKS)
            or {key: value.get('picker', {}).get(key) for key in ('ok', 'stage', 'choices')} != {'ok': True, 'stage': 'complete', 'choices': ['tofa-catalog-a', 'tofa-catalog-b']}
            or value['requests'] != [{'model': 'tofa-catalog-b', 'effort': 'high', 'path': '/responses'}]):
        raise Failure('catalog_observation_failed')
