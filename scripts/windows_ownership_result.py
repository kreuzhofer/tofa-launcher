"""Allowlisted experiment metadata; no ordinary conversation/account contents."""
import re
from windows_template_transport import Failure

CHECKS = ('argv_environment_stdio_exit', 'reparse_refused', 'case_equivalent', 'competing_guards_refused', 'ordinary_refused', 'incumbent_preserved',
          'same_profile_singleton', 'separate_profile_measured', 'ordinary_still_alive',
          'separate_owned_exit', 'ordinary_normal_quit', 'vendor_service_preserved', 'owned_apps_exited')


def sanitize(value):
    def require(condition):
        if not condition: raise Failure('malformed_ownership_result')
    def string(item, pattern, limit=600):
        require(isinstance(item, str) and len(item) <= limit and re.fullmatch(pattern, item) is not None)
        return item
    def integer(item):
        require(type(item) is int and 0 <= item < 2**32)
        return item
    def path(item):
        return string(item, r'C:\\(?:Program Files\\WindowsApps\\OpenAI\.Codex_[a-zA-Z0-9_.]+(?:\\[a-zA-Z0-9_. -]+)*|Users\\tofa-test\\[a-zA-Z0-9_. \\-]+)')
    require(isinstance(value, dict) and value.get('production_gate') == 'blocked'
            and value.get('blocker') == 'atomic_profile_ipc_ownership_unproven')
    result = {key: value[key] for key in ('production_gate', 'blocker')}
    if 'stage' in value: result['stage'] = string(value['stage'], r'argv|paths|discovery|ordinary_start|ordinary_inspect|singleton|separate_profile|cleanup|complete')
    checks = value.get('checks')
    if not isinstance(checks, dict): raise Failure('malformed_ownership_result')
    result['checks'] = {}
    for key in CHECKS:
        if key in checks:
            require(type(checks[key]) is bool)
            result['checks'][key] = checks[key]
    for phase in ('before', 'ordinary', 'separate', 'after'):
        if phase not in value: continue
        item = value[phase]
        require(isinstance(item, dict))
        clean = {'sid': string(item.get('sid'), r'S-1-5-21-(?:[0-9]+-){3}[0-9]+')}
        for key in ('paths_safe', 'process_inventory_complete'):
            require(type(item.get(key)) is bool)
            clean[key] = item[key]
        for key in ('packages', 'engines', 'incumbents', 'profiles', 'standalone'):
            require(isinstance(item.get(key), list) and len(item[key]) <= 32)
        for key in ('packages', 'engines', 'incumbents'):
            require(all(isinstance(entry, dict) for entry in item[key]))
        clean['packages'] = [{
            'name': string(p.get('name'), r'OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}'),
            'root': path(p.get('root')), 'app': path(p.get('app')),
            'status': string(p.get('status'), r'[A-Za-z, ]{1,80}'),
            'architecture': string(p.get('architecture'), r'Arm64'),
            'engine_sha256': string(p.get('engine_sha256'), r'[0-9a-f]{64}')} for p in item['packages']]
        clean['engines'] = [{'path': path(e.get('path')), 'sha256': string(e.get('sha256'), r'[0-9a-f]{64}'),
                             'architecture': string(e.get('architecture'), r'ARM64|AMD64|Unknown')} for e in item['engines']]
        clean['incumbents'] = [{'pid': integer(p.get('pid')), 'path': path(p.get('path')),
                                'created': string(p.get('created'), r'[0-9]{1,20}')} for p in item['incumbents']]
        clean['profiles'] = [path(p) for p in item['profiles']]
        clean['standalone'] = [path(p) for p in item['standalone']]
        service = item.get('service', {})
        require(isinstance(service, dict))
        clean['service'] = {'pid': integer(service.get('pid')), 'state': string(service.get('state'), r'Running|Stopped')}
        pipe = item.get('pipe', {})
        require(isinstance(pipe, dict))
        require(pipe.get('name') == 'codex-ipc')
        clean['pipe'] = dict(name='codex-ipc', **{key: integer(pipe.get(key)) for key in ('open_error', 'server_pid', 'security_error')})
        clean['pipe']['sddl'] = None if pipe.get('sddl') is None else string(pipe['sddl'], r'[A-Za-z0-9:;()\-]+', 3000)
        result[phase] = clean
    if 'synthetic_histories' in value:
        histories = value['synthetic_histories']
        require(isinstance(histories, list) and len(histories) <= 32)
        require(all(isinstance(item, dict) and type(item.get('exists')) is bool for item in histories))
        result['synthetic_histories'] = [{'path': path(item.get('path')), 'exists': item['exists']} for item in histories]
    if 'separate_profile_result' in value: result['separate_profile_result'] = string(value['separate_profile_result'], r'window|exited_without_window')
    if 'same_profile_exit' in value: result['same_profile_exit'] = integer(value['same_profile_exit'])
    if 'bridge_initializations' in value:
        initializations = value['bridge_initializations']
        require(isinstance(initializations, list) and len(initializations) <= 32)
        require(all(isinstance(item, dict) and type(item.get('main')) is bool and type(item.get('ok')) is bool for item in initializations))
        result['bridge_initializations'] = [{'main': item['main'], 'ok': item['ok']} for item in initializations]
    return result


def validate(value):
    if (any(value['checks'].get(key) is not True for key in CHECKS)
            or any(phase not in value for phase in ('before', 'ordinary', 'separate', 'after'))):
        raise Failure('ownership_observation_failed')
    pipe = value['ordinary']['pipe']
    if pipe['open_error'] or pipe['security_error'] or not pipe['sddl'] or not pipe['server_pid']:
        raise Failure('ownership_observation_failed')
