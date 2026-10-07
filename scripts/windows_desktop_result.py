"""Sanitized desktop observations and qualification requirements."""
import re

from windows_template_transport import Failure
from windows_guardian_result import sanitized_guardian

READINESS = ('authenticated', 'workspace_trusted', 'automatic_review', 'full_access_disabled', 'readiness_engine_exited')
CHECKS = (*READINESS,
          'bridge_policy_preserved', 'bridge_initialized', 'desktop_started', 'desktop_permissions_configured', 'command_effect', 'normal_quit',
          'owned_children_exited', 'cli_defaults_unchanged', 'vendor_service_preserved', 'diagnostics_written')
REASONS = {'desktop_authentication_required', 'desktop_workspace_invalid', 'desktop_control_unsupported',
           'native_client_busy', 'engine_identity_mismatch', 'wrong_user_session', 'desktop_readiness_failed',
           'desktop_policy_mismatch', 'desktop_startup_failed', 'desktop_command_failed',
           'desktop_cleanup_failed', 'desktop_smoke_passed', 'desktop_readiness_passed', 'guardian_review_missing',
           'guardian_review_denied', 'guardian_review_timed_out', 'guardian_review_aborted',
           'ownership_discovery_failed', 'ownership_startup_failed', 'ownership_observation_failed', 'guardian_target_unavailable', 'guardian_decision_mismatch', 'guardian_enforcement_failed', 'guardian_review_mismatch'}


def sanitized_desktop(value):
    result = {'ok': value['ok'], 'reason': value.get('reason') if value.get('reason') in REASONS else 'desktop_readiness_failed',
              'checks': {}}
    checks = value.get('checks', {})
    if not isinstance(checks, dict): raise Failure('malformed_desktop_result')
    for key in (*CHECKS, 'denial_target_absent'):
        if key in checks:
            if type(checks[key]) is not bool: raise Failure('malformed_desktop_result')
            result['checks'][key] = checks[key]
    if value.get('route') == 'native-desktop-bridge': result['route'] = value['route']
    restrictions = value.get('restrictions', {})
    if not isinstance(restrictions, dict): raise Failure('malformed_desktop_result')
    result['restrictions'] = {}
    for key in ('tool_registration_writes_refused', 'unrelated_turns_refused', 'native_visualization_roots'):
        if key in restrictions:
            if type(restrictions[key]) is not int or not 0 <= restrictions[key] <= (1 if key == 'native_visualization_roots' else 128):
                raise Failure('malformed_desktop_result')
            result['restrictions'][key] = restrictions[key]
    identity = value.get('identity', {})
    if not isinstance(identity, dict): raise Failure('malformed_desktop_result')
    clean = {}
    patterns = {'model': r'(?:gpt-[a-z0-9.-]+|o[0-9][a-z0-9.-]*|codex-[a-z0-9.-]+)',
                'provider': r'openai', 'reviewer': r'auto_review', 'engine_sha256': r'[0-9a-f]{64}',
                'app_sha256': r'[0-9a-f]{64}', 'bridge_sha256': r'[0-9a-f]{64}',
                'shell_sha256': r'[0-9a-f]{64}',
                'package': r'OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}'}
    for key, pattern in patterns.items():
        if key in identity:
            item = identity[key]
            if not isinstance(item, str) or len(item) > 180 or not re.fullmatch(pattern, item):
                raise Failure('desktop_identity_invalid')
            clean[key] = item
    for key in ('app_pid', 'bridge_pid', 'engine_pid'):
        if key in identity:
            if type(identity[key]) is not int or not 0 < identity[key] < 2**32:
                raise Failure('desktop_identity_invalid')
            clean[key] = identity[key]
    result['identity'] = clean
    execution = value.get('execution', {})
    if not isinstance(execution, dict): raise Failure('malformed_desktop_result')
    result['execution'] = {}
    for name in ('admitted', 'command', 'completed'):
        if name not in execution: continue
        item = execution[name]
        if not isinstance(item, dict) or any(type(item.get(key)) is not int or not 0 < item[key] < 2**32
                                             for key in ('bridge_pid', 'thread', 'turn')):
            raise Failure('malformed_desktop_result')
        result['execution'][name] = {key: item[key] for key in ('bridge_pid', 'thread', 'turn')}
    if 'control_failure' in value:
        fields = {'action': ('configure', 'submit', 'quit'),
                  'stage': ('identity', 'search', 'pattern', 'expand', 'select', 'invoke'),
                  'error': ('other', 'missing_control', 'identity_mismatch', 'stale_element',
                            'invalid_operation', 'element_not_enabled')}
        detail = value['control_failure']
        if (value['ok'] is not False or not isinstance(detail, dict)
                or any(detail.get(key) not in choices for key, choices in fields.items())):
            raise Failure('malformed_desktop_result')
        result['control_failure'] = {key: detail[key] for key in fields}
    if 'ownership' in value:
        from windows_ownership_result import sanitize
        result['ownership'] = sanitize(value['ownership'])
    if 'guardian' in value: result['guardian'] = sanitized_guardian(value['guardian'])
    return result


def validate_desktop_readiness(task, result):
    if not result['ok']: raise Failure(result['reason'])
    if (task.get('ok') is not True or task.get('completed') is not True or task.get('unregistered') is not True
            or type(task.get('last_result')) is not int or task['last_result'] != 0 or task.get('state') != 'Ready'):
        raise Failure('contradictory_desktop_completion')
    if any(result['checks'].get(key) is not True for key in READINESS):
        raise Failure('desktop_readiness_failed')


def validate_desktop(task, result, native, *, guardian_case=None):
    validate_desktop_readiness(task, result)
    required = tuple(key for key in CHECKS if guardian_case != 'deny' or key != 'command_effect')
    if result.get('route') != 'native-desktop-bridge' or any(result['checks'].get(key) is not True for key in required):
        raise Failure('desktop_assertion_failed')
    if any(key not in result['restrictions'] for key in ('tool_registration_writes_refused', 'unrelated_turns_refused', 'native_visualization_roots')):
        raise Failure('desktop_assertion_failed')
    identity = result['identity']
    if guardian_case is not None and not identity.get('shell_sha256'): raise Failure('desktop_identity_mismatch')
    if (any(identity.get(key) != native['identity'][key] for key in ('package', 'engine_sha256'))
            or any(key not in identity for key in ('app_pid', 'bridge_pid', 'engine_pid', 'app_sha256', 'bridge_sha256'))
            or not identity.get('model') or identity.get('provider') != 'openai' or identity.get('reviewer') != 'auto_review'):
        raise Failure('desktop_identity_mismatch')
    execution = result['execution']
    admitted = execution.get('admitted')
    if (not admitted or admitted['bridge_pid'] != identity['bridge_pid']
            or any(execution.get(name) != admitted for name in ('command', 'completed'))):
        raise Failure('desktop_execution_mismatch')
