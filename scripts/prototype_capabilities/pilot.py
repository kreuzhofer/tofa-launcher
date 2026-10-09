"""THROWAWAY capability pilot: replay, score, and plan; no inference by default."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import os
import signal
import subprocess
import sys
import threading
import time


def actions(path):
    calls = {}
    for line in path.open():
        event = json.loads(line)
        if 'tool' in event:
            yield event
            continue
        payload = event.get('payload', {})
        if event.get('type') != 'response_item':
            continue
        if payload.get('type') == 'function_call':
            arguments = json.loads(payload.get('arguments', '{}'))
            calls[payload['call_id']] = {
                'tool': payload.get('name'),
                'command': arguments.get('cmd', arguments.get('command', '')),
            }
        elif payload.get('type') == 'function_call_output' and payload.get('call_id') in calls:
            call = calls.pop(payload['call_id'])
            output = payload.get('output', '')
            if not isinstance(output, str):
                output = json.dumps(output, sort_keys=True)
            match = re.search(r'Process exited with code (\d+)', output)
            call.update(output=output.split('Output:', 1)[-1].strip(),
                        exit_code=int(match.group(1)) if match else None)
            yield call


class LoopWatch:
    def __init__(self):
        self.previous = None
        self.streak = 0
        self.count = 0

    def add(self, event):
        if event.get('tool') == 'write_stdin':
            return None
        self.count += 1
        if event.get('workspace_changed') is True:
            self.previous = None
            self.streak = 0
            return None
        command = event.get('command', '')
        if not isinstance(command, str):
            command = json.dumps(command, sort_keys=True)
        family = 'exact_action'
        if ('zipfile.ZipFile(' in command and 'print(s[max(0,i-' in command
                and 'i+20])' in command and event.get('exit_code') == 0):
            command = re.sub(r'max\(0,i-\d+\)', 'max(0,i-WINDOW)', command)
            family = 'expanding_xml_inspection'
        current = (event.get('tool'), command, event.get('output'), event.get('exit_code'))
        self.streak = self.streak + 1 if current == self.previous else 1
        self.previous = current
        if self.streak >= 5:
            return {'reason': 'repeated_action_without_progress', 'stop_after_action': self.count,
                    'action_family': family, 'observed': True, 'execution_stopped': False}
        return None


def replay(path):
    watch = LoopWatch()
    for event in actions(path):
        result = watch.add(event)
        if result:
            return result
    return {'reason': 'no_loop_observed', 'stop_after_action': None,
            'observed': True, 'execution_stopped': False}


def supervise(command, seconds, prompt='', cwd=None, env=None):
    if not 1 <= seconds <= 900:
        raise ValueError('deadline outside pilot limits')
    result = {'stop_reason': None, 'turn_completed': False, 'commands_completed': 0,
              'final_messages': [], 'command_evidence': [], 'client_error': False}
    watch = LoopWatch()
    def workspace_state():
        if cwd is None: return None
        state = []
        for path in Path(cwd).rglob('*'):
            if path.is_file() and not path.is_symlink():
                info = path.stat()
                state.append((str(path.relative_to(cwd)), info.st_size, info.st_mtime_ns))
        return sorted(state)
    previous_workspace = workspace_state()
    stopped = threading.Event()
    started = time.monotonic()
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    def terminate(reason):
        if stopped.is_set(): return
        result['stop_reason'] = reason
        stopped.set()
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    def consume(stream, parse):
        nonlocal previous_workspace
        size = 0
        for line in iter(lambda: stream.readline(1024 * 1024), b''):
            size += len(line)
            if size > 8 * 1024 * 1024:
                terminate('client_output_limit'); break
            if not parse: continue
            try: event = json.loads(line)
            except (ValueError, UnicodeDecodeError): continue
            if not isinstance(event, dict): continue
            kind = event.get('type')
            if kind == 'turn.completed': result['turn_completed'] = True
            if kind in ('error', 'turn.failed'): result['client_error'] = True
            if kind != 'item.completed': continue
            item = event.get('item', {})
            if item.get('type') == 'agent_message': result['final_messages'].append(item.get('text', ''))
            if item.get('type') == 'command_execution':
                result['commands_completed'] += 1
                action = {'tool': 'exec_command', 'command': item.get('command', ''),
                          'output': item.get('aggregated_output', ''), 'exit_code': item.get('exit_code')}
                current_workspace = workspace_state()
                action['workspace_changed'] = current_workspace != previous_workspace
                previous_workspace = current_workspace
                result['command_evidence'].append(action)
                if watch.add(action):
                    terminate('repeated_action_without_progress'); break
    readers = [threading.Thread(target=consume, args=(stream, parse), daemon=True)
               for stream, parse in ((child.stdout, True), (child.stderr, False))]
    for reader in readers: reader.start()
    try:
        child.stdin.write(prompt.encode()); child.stdin.close()
        while child.poll() is None:
            if time.monotonic() - started >= seconds: terminate('deadline')
            if stopped.wait(0.05):
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait(timeout=3)
                break
    finally:
        if child.poll() is None: terminate('supervisor_error')
        for reader in readers: reader.join(timeout=3)
        for stream in (child.stdout, child.stderr): stream.close()
    result.update(exit_code=child.returncode, elapsed_ms=round((time.monotonic()-started)*1000))
    return result


def score(evidence):
    def criterion(name):
        value = evidence.get(name)
        if value is not None and type(value) is not bool:
            raise ValueError('criterion evidence must be boolean or null')
        return {'status': 'not_run' if value is None else 'passed' if value else 'failed'}
    if evidence.get('client') not in ('cli', 'desktop'):
        raise ValueError('client must be cli or desktop')
    ui = criterion('ui_opened') if evidence['client'] == 'desktop' else {'status': 'not_applicable'}
    if ui['status'] == 'not_run':
        ui['reason'] = 'ui_check_pending'
    return {'task_artifact': criterion('artifact_valid'),
            'workflow_skill': criterion('skill_read'),
            'delivery_reference': criterion('citation_valid'),
            'delivery_ui': ui}


def plan():
    models = {'glm': 'zai-org/GLM-5.3', 'kimi': 'moonshotai/Kimi-K3',
              'deepseek': 'deepseek-ai/DeepSeek-V4.1-Flash'}
    prompts = {
        '03': 'Build me a 5-slide pitch deck for an app that texts you one genuine compliment every morning. Make the design go hard. No corporate stock-photo energy.',
        '05': 'The finished deck is in fixtures/sample-deck.pptx and its PDF copy is in fixtures/sample-deck.pdf. Give me both files so I can open them. Do not edit, regenerate, or upload them.',
        '07': 'Run python3 probe.py and diagnose the failure. Do not install anything or use the network. Make at most three diagnostic tool calls, then explain the blocker and one concrete next step. Do not repeat an unchanged command.',
    }
    prompts['04'] = 'Use the installed presentation skill; read its instructions before creating the deck. ' + prompts['03']
    runs = []
    for case in ('05', '07', '03', '04'):
        for client in ('cli', 'desktop'):
            for short, model in models.items():
                runs.append({'id': f'{client}-{short}-{case}-baseline-1', 'model': model,
                    'client': client, 'platform': 'macos-arm64', 'case': case,
                    'variant': 'baseline', 'status': 'not_run', 'attempt': 1,
                    'guardian': 'zai-org/GLM-5.3-Flash',
                    'limits': {'seconds': 900 if case in ('03', '04') else 180,
                               'repeated_actions': 5,
                               'requests': 80 if case in ('03', '04') else 12,
                               'output_tokens_per_request': 8192 if case in ('03', '04') else 4096}})
    return {'prototype': True, 'corpus_version':'prototype-v2-python3', 'prompts': prompts, 'runs': runs,
            'limits_status': 'declared; live enforcement must pass synthetic tests first'}


def catalog_variant(catalog, model):
    result = copy.deepcopy(catalog)
    mains = [entry for entry in result['models'] if entry['slug']==model]
    if len(mains)!=1: raise ValueError('exactly one selected main required')
    messages = mains[0]['model_messages']
    old = messages['instructions_template']
    start, end = old.index('**File References**'), old.index('**Structure**')
    if end<=start: raise ValueError('unexpected instruction section order')
    replacement = ('**File References**\n'
        'For each existing local deliverable, use the native file citation on its own line: '
        ':codex-file-citation{path="<verified absolute file path>" purpose="source"}. '
        'For a file you create or edit in this turn, use purpose="output". '
        'Emit the directive directly, outside backticks or code fences. '
        'Use the exact verified path and preserve the file.\n\n')
    messages['instructions_template'] = old[:start]+replacement+old[end:]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    replay_parser = sub.add_parser('replay')
    replay_parser.add_argument('trace', type=Path)
    score_parser = sub.add_parser('score')
    score_parser.add_argument('evidence', type=Path)
    sub.add_parser('plan')
    supervisor = sub.add_parser('supervise')
    supervisor.add_argument('--seconds', type=int, required=True)
    supervisor.add_argument('command', nargs=argparse.REMAINDER)
    variant_parser = sub.add_parser('catalog-variant')
    variant_parser.add_argument('catalog',type=Path)
    variant_parser.add_argument('--model',required=True)
    options = parser.parse_args()
    if options.operation == 'catalog-variant':
        result = catalog_variant(json.loads(options.catalog.read_text()),options.model)
    elif options.operation == 'supervise':
        command = options.command[1:] if options.command[:1] == ['--'] else options.command
        result = supervise(command, options.seconds)
        result.pop('final_messages'); result.pop('command_evidence')
    elif options.operation == 'plan':
        result = plan()
    elif options.operation == 'replay':
        result = replay(options.trace)
    else:
        result = score(json.loads(options.evidence.read_text()))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
