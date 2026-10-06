"""Require a correlated native review and its actual execution enforcement."""
from windows_template_transport import Failure


def sanitized_guardian(value):
    if not isinstance(value, dict): raise Failure('malformed_guardian_result')
    result = {}
    enums = {'decision': ('approved', 'denied', 'timedOut', 'aborted'),
             'source': ('agent',), 'command_status': ('completed', 'failed', 'declined')}
    for key, choices in enums.items():
        if key in value:
            if value[key] not in choices: raise Failure('malformed_guardian_result')
            result[key] = value[key]
    for key in ('marker_present', 'synthetic_command', 'execution_succeeded', 'exit_code_present'):
        if key in value:
            if type(value[key]) is not bool: raise Failure('malformed_guardian_result')
            result[key] = value[key]
    for name in ('started', 'completed', 'command'):
        count = name + '_count'
        if count in value:
            if type(value[count]) is not int or not 0 <= value[count] <= 16: raise Failure('malformed_guardian_result')
            result[count] = value[count]
        if name not in value: continue
        fields = ('bridge_pid', 'thread', 'turn', 'item') + (() if name == 'command' else ('review',))
        item = value[name]
        if not isinstance(item, dict) or any(type(item.get(key)) is not int or not 0 < item[key] < 2**32 for key in fields):
            raise Failure('malformed_guardian_result')
        result[name] = {key: item[key] for key in fields}
    return result


def validate_guardian(result, case):
    if case == 'deny' and result.get('checks', {}).get('denial_target_absent') is not True:
        raise Failure('guardian_target_unavailable')
    value = result.get('guardian', {})
    started, completed, command = (value.get(key) for key in ('started', 'completed', 'command'))
    if not started or not completed or any(value.get(name + '_count') != 1 for name in ('started', 'completed', 'command')):
        raise Failure('guardian_review_missing')
    if (started != completed or not command or any(command[key] != started[key] for key in command)
            or any(started[key] != result['execution']['admitted'][key] for key in ('bridge_pid', 'thread', 'turn'))):
        raise Failure('guardian_review_mismatch')
    expected = 'approved' if case == 'allow' else 'denied'
    if value.get('source') != 'agent' or value.get('decision') != expected:
        raise Failure('guardian_decision_mismatch')
    if (value.get('synthetic_command') is not True or value.get('marker_present') is not (case == 'allow')
            or value.get('execution_succeeded') is not (case == 'allow') or value.get('exit_code_present') is not (case == 'allow')
            or value.get('command_status') != ('completed' if case == 'allow' else 'declined')):
        raise Failure('guardian_enforcement_failed')
