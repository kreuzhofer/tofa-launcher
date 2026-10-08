"""Allowlisted #102 prototype evidence. No result grants production admission."""
import re

from windows_template_transport import Failure


CASES = ('ordinary_first', 'launcher_first', 'simultaneous', 'two_launchers',
         'pipe_precreated', 'pipe_replaced', 'ordinary_recovery')
BLOCKERS = ('unverified_native_pipe_connection', 'atomic_acquisition_unproven',
            'cross_user_session_unavailable', 'runtime_source_mapping_unavailable',
            'native_observation_incomplete')


def sanitize(value):
    def require(ok):
        if not ok: raise Failure('malformed_atomic_ownership_result')

    def fields(item, patterns=(), integers=(), booleans=()):
        require(isinstance(item, dict))
        result = {}
        for key, pattern in patterns:
            if key in item:
                require(isinstance(item[key], str) and len(item[key]) <= 240
                        and re.fullmatch(pattern, item[key]) is not None)
                result[key] = item[key]
        for key in integers:
            if key in item:
                require(type(item[key]) is int and 0 <= item[key] < 2**64)
                result[key] = item[key]
        for key in booleans:
            if key in item:
                require(type(item[key]) is bool)
                result[key] = item[key]
        return result

    require(isinstance(value, dict) and value.get('production_gate') == 'blocked')
    result = fields(value, (('stage', r'preparation|source|races|pipe|cleanup|complete'),
        ('failed_stage', r'preparation|source|races|pipe|cleanup'),
        ('failure_reason', r'ownership_startup_failed|native_client_busy|pipe_unavailable|desktop_readiness_failed'),
        ('failure_kind', r'ValueError|TimeoutExpired|OSError|BrokenBarrierError|UnexpectedError')))
    result['production_gate'] = 'blocked'
    identity = value.get('identity', {})
    result['identity'] = fields(identity, (
        ('package', r'OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}'),
        *((key, r'[0-9a-f]{64}') for key in ('app_sha256', 'engine_sha256', 'asar_sha256')),
        ('sid', r'S-1-5-21-(?:[0-9]+-){3}[0-9]+'),
        ('runtime_version', r'[0-9]+(?:\.[0-9]+){1,3}')),
        ('session',))
    checks = value.get('checks', {})
    result['checks'] = fields(checks, booleans=('owned_apps_exited', 'cli_defaults_unchanged',
                                               'vendor_service_preserved', 'synthetic_histories_preserved'))
    for key, limit in (('sources', 32), ('trials', 16), ('blockers', len(BLOCKERS))):
        require(isinstance(value.get(key), list) and len(value[key]) <= limit)
    result['sources'] = [fields(item, (('name', r'[a-zA-Z0-9_./-]+'), ('sha256', r'[0-9a-f]{64}')),
        integers=('singleton_calls', 'fixed_pipe_names', 'collision_handlers', 'reconnect_handlers')) for item in value['sources']]
    result['trials'] = [fields(item, (('case', '|'.join(CASES)), ('winner', r'ordinary|launcher|competing_launcher|both|neither'),
        ('failure', r'startup_failed|pipe_unavailable|client_identity_unavailable|observation_timeout')),
        integers=('client_pid', 'bytes_available', 'pipe_error', 'ordinary_pid', 'launcher_pid', 'competing_launcher_pid',
                  'pipe_server_pid', 'ordinary_exit', 'launcher_exit', 'main_initializations',
                  'admitted_turns', 'client_session', 'client_created_ticks', 'first_exit', 'second_exit'),
        booleans=('connected', 'admitted', 'client_matches_app', 'client_matches_user', 'client_matches_session',
                  'normal_quit', 'cleanup_complete', 'incumbent_preserved', 'client_same_process')) for item in value['trials']]
    require(all(isinstance(item, str) and item in BLOCKERS for item in value['blockers']))
    result['blockers'] = value['blockers']
    return result
