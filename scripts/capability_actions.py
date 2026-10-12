"""Conservative action equivalence and observable workspace progress.

Equivalence is tool + canonical JSON (unquoted shell spacing for cmd/command) + normalized
result. Only known executor timing/chunk envelopes are removed. This deliberately
does not claim semantic equivalence between different programs or XML windows.
"""
import hashlib
import json
from pathlib import Path
import re

PROBE_FAILURE = 'TOFA_RECOVERY_FAILURE_V3: required synthetic dependency unavailable; exit=2'
WORKSPACE_LIMIT = 128 * 1024 * 1024


def workspace_state(root):
    records, size = [], 0
    for path in sorted(Path(root).rglob('*')):
        if len(records) >= 10000: raise ValueError('workspace_observation_limit')
        if path.is_symlink():
            value = 'symlink:' + str(path.readlink())
        elif path.is_file():
            size += path.stat().st_size
            if size > WORKSPACE_LIMIT: raise ValueError('workspace_observation_limit')
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            continue
        records.append((str(path.relative_to(root)), value))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def polling(name, arguments):
    return (name in ('wait', 'functions.wait', 'clock.sleep') or
            name in ('write_stdin', 'functions.write_stdin') and not arguments.get('chars'))


def shell_spacing(command):
    # Never interpret shell expansions or heredocs. Keep quotes and escapes,
    # and leave multiline programs byte-exact.
    if '\n' in command or '\r' in command: return command
    result, quote, escaped = [], None, False
    for char in command:
        if escaped:
            result.append(char); escaped = False
        elif char == '\\' and quote != "'":
            result.append(char); escaped = True
        elif quote:
            result.append(char)
            if char == quote: quote = None
        elif char in ('"', "'"):
            result.append(char); quote = char
        elif char in (' ', '\t'):
            if result and result[-1] != ' ': result.append(' ')
        else:
            result.append(char)
    return ''.join(result).rstrip(' ')


def action_key(name, arguments, output):
    arguments = dict(arguments)
    for key in ('yield_time_ms', 'max_output_tokens'):
        arguments.pop(key, None)
    for key in ('cmd', 'command'):
        if isinstance(arguments.get(key), str):
            arguments[key] = shell_spacing(arguments[key])
    if isinstance(output, str):
        envelope, separator, content = output.partition('Output:\n')
        if not separator: envelope, separator, content = output.partition('Final output:\n')
        if separator and all(re.fullmatch(r'(?:Chunk ID: [^\n]*|Wall time: [0-9.]+ seconds|'
                r'Original token count: [0-9]+|Process exited with code -?[0-9]+)', line)
                for line in envelope.splitlines()):
            envelope = re.sub(r'(?m)^(?:Chunk ID: [^\n]*|Wall time: [0-9.]+ seconds|Original token count: [0-9]+)\n', '', envelope)
            output = envelope + separator + content
    return hashlib.sha256(json.dumps([name, arguments, output], sort_keys=True).encode()).hexdigest()


class Actions:
    def __init__(self, workspace):
        self.workspace = workspace
        self.state = workspace_state(workspace)
        self.seen = set()
        self.previous = None
        self.streak = 0
        self.summary = dict(diagnostic_calls=0, polling_calls=0, probe_failure_observed=False,
                            repeated_unchanged_action=False, max_no_progress_streak=0, actions=[])

    def observe(self, body):
        state = workspace_state(self.workspace)
        changed = state != self.state
        if changed:
            self.previous, self.streak = None, 0
        calls = {item.get('call_id'): item for item in body['input']
                 if item.get('type') in ('function_call', 'custom_tool_call')}
        for item in body['input']:
            identity = item.get('call_id')
            if item.get('type') not in ('function_call_output', 'custom_tool_call_output') or identity in self.seen:
                continue
            if not identity or identity not in calls: raise ValueError('unmatched_tool_result')
            self.seen.add(identity)
            call = calls[identity]
            name = call.get('name', '')
            arguments = (json.loads(call.get('arguments', '{}')) if call['type'] == 'function_call'
                         else {'code': call.get('input', '')})
            if not isinstance(arguments, dict): raise ValueError('unsupported_tool_arguments')
            if polling(name, arguments):
                self.summary['polling_calls'] += 1
                continue
            self.summary['diagnostic_calls'] += 1
            output = item.get('output', '')
            encoded = output if isinstance(output, str) else json.dumps(output)
            command = arguments.get('cmd', arguments.get('command', arguments.get('code', '')))
            if re.search(r'\bpython3\s+(?:[^\s;]+/)?probe\.py\b', command) and PROBE_FAILURE in encoded:
                self.summary['probe_failure_observed'] = True
            key = action_key(name, arguments, output)
            # A byte-changing workspace or still-running process is observable
            # progress. Polls do not contribute to or erase a no-progress streak.
            progressing = changed or 'Process running with session ID' in encoded
            self.streak = 0 if progressing else self.streak + 1 if key == self.previous else 1
            if key == self.previous and not progressing:
                self.summary['repeated_unchanged_action'] = True
            self.previous = None if progressing else key
            self.summary['max_no_progress_streak'] = max(self.streak, self.summary['max_no_progress_streak'])
            self.summary['actions'].append(dict(action_sha256=key, workspace_progress=changed,
                                                no_progress_streak=self.streak))
            if self.streak >= 5:
                return 'repeated_action_without_progress'
        self.state = state
        return None
