"""Synthetic presentation responses using the actual client's advertised tools.

This module proposes the fixed calibration task; it never executes tools, forwards
inference, or makes approval decisions. SyntheticObserver owns that boundary.
"""
import json
from pathlib import Path
import re
import shlex
import sys
import threading

from capability_runtime import catalog_tools, loader_tools, smoke_execution
from capability_evaluation import save
from evaluation_proxy import fixture_response, message
from presentation_runtime import from_loader_output, check_node_version


def objects(value, depth=0):
    if depth > 10:
        raise ValueError('tool_output_nesting_limit')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return
    if isinstance(value, dict):
        if value.get('isError') is True or value.get('success') is False:
            raise ValueError('actual_tool_failed')
        yield value
        for key in ('content', 'contentItems', 'text', 'output', 'structuredContent'):
            if key in value:
                yield from objects(value[key], depth + 1)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item, depth + 1)


def execution_result(value):
    results = [item for item in objects(value) if 'exit_code' in item or 'session_id' in item]
    if results:
        if len(results) != 1:
            raise ValueError('execution_result_missing_or_ambiguous')
        return results[0]
    # Direct exec_command has a textual envelope; functions.exec returns the
    # structured result. A status line in command stdout is never authoritative.
    if not isinstance(value, str) or not value.startswith('Chunk ID: ') or '\nOutput:\n' not in value:
        raise ValueError('execution_result_missing_or_ambiguous')
    header, output = value.split('\nOutput:\n', 1)
    exits = re.findall(r'(?m)^Process exited with code (-?\d+)$', header)
    sessions = re.findall(r'(?m)^Process running with session ID (\d+)$', header)
    if len(exits) + len(sessions) != 1:
        raise ValueError('execution_status_missing_or_ambiguous')
    status = {'exit_code': int(exits[0])} if exits else {'session_id': int(sessions[0])}
    return {'output': output, **status}


class PresentationResponder:
    def __init__(self, run, runtime, skill, *, worker=None):
        self.run = Path(run)
        self.runtime = runtime
        self.skill = Path(skill)
        self.provider = runtime['provider']
        if self.provider not in ('codex_app', 'tofa_presentation_runtime'):
            raise ValueError('unqualified_loader_provider')
        self.loader = 'mcp__' + self.provider + '__load_workspace_dependencies'
        self.worker = Path(worker) if worker else Path(__file__).with_name('presentation_smoke.py')
        self.state = {'loader_name': None, 'runtime': None, 'calls': 0, 'failure': None}
        self.session = None
        self.last = None
        self.parts = []
        self.executions = []
        self.polls = 0
        self.done = False
        self.lock = threading.Lock()
        self.lane = None
        self.direct_tools = {}

    def custom_call(self, call_id, code):
        return {'type': 'custom_tool_call', 'id': 'ct_' + call_id, 'call_id': call_id,
                'name': 'exec', 'namespace': 'functions', 'status': 'completed',
                'input': '// @exec: {"yield_time_ms": 30000, "max_output_tokens": 5000}\n' + code}

    def tool(self, call_id, name, arguments):
        if self.lane == 'orchestrated':
            return self.custom_call(call_id, 'text(await tools.' + name + '(' + json.dumps(arguments) + '));')
        namespace, actual = self.direct_tools[name]
        item = {'type': 'function_call', 'id': 'fc_' + call_id, 'call_id': call_id,
                'name': actual, 'arguments': json.dumps(arguments), 'status': 'completed'}
        if namespace:
            item['namespace'] = namespace
        return item

    def select_lane(self, body):
        catalog = catalog_tools(body)
        loaders = [(ns, tool) for ns, tool in catalog
                   if (ns == 'mcp__' + self.provider and tool.get('name') == 'load_workspace_dependencies')
                   or (ns is None and tool.get('name') == self.loader)]
        commands = {}
        for name in ('exec_command', 'write_stdin'):
            commands[name] = [(ns, tool) for ns, tool in catalog if ns in (None, 'functions')
                              and tool.get('type') == 'function' and tool.get('name') == name]
        orchestrators = [tool for ns, tool in catalog if ns == 'functions'
                        and tool.get('name') == 'exec' and tool.get('type') == 'custom']
        if loaders:
            if (len(loaders) != 1 or len(loader_tools(body, self.provider)) != 1
                    or any(len(items) != 1 for items in commands.values())):
                raise ValueError('actual_direct_tools_missing_or_ambiguous')
            lane = 'direct'
            selected = {self.loader: loaders[0], **{name: items[0] for name, items in commands.items()}}
            self.direct_tools = {name: (ns, tool['name']) for name, (ns, tool) in selected.items()}
        elif len(orchestrators) == 1:
            lane = 'orchestrated'
        else:
            raise ValueError('actual_tools_missing_or_ambiguous')
        if self.lane is not None and self.lane != lane:
            raise ValueError('actual_tool_lane_changed')
        self.lane = lane

    def discover(self, outputs):
        if 'runtime-discovery' not in outputs:
            fields = []
            for key, name in (('loader', self.loader), ('exec', 'exec_command'), ('wait', 'write_stdin')):
                fields.append(key + ':ALL_TOOLS.filter(t=>t.name===' + json.dumps(name) + ').map(t=>t.name)')
            return self.custom_call('runtime-discovery', 'text({tofa_discovery_v1:{' + ','.join(fields) + '}});')
        found = [item['tofa_discovery_v1'] for item in objects(outputs['runtime-discovery'])
                 if 'tofa_discovery_v1' in item]
        if found != [{'loader': [self.loader], 'exec': ['exec_command'], 'wait': ['write_stdin']}]:
            raise ValueError('required_actual_tools_missing_or_ambiguous')
        return None

    def item(self, body):
        if body['model'] == 'nvidia/Nemotron-3_5-Lightning':
            return message(json.dumps({'title': 'Supplied runtime smoke', 'description': 'Synthetic native runtime preview check'}))
        self.select_lane(body)
        outputs = {}
        for item in body.get('input', []):
            if item.get('type') in ('custom_tool_call_output', 'function_call_output'):
                call_id = item.get('call_id')
                if call_id in outputs:
                    raise ValueError('duplicate_actual_tool_output')
                outputs[call_id] = item.get('output')
        if self.lane == 'orchestrated':
            discovery = self.discover(outputs)
            if discovery:
                return discovery
        if 'runtime-loader' not in outputs:
            self.state['loader_name'] = self.loader
            return self.tool('runtime-loader', self.loader, {})
        if self.state['runtime'] is None:
            value = outputs['runtime-loader']
            runtime = from_loader_output(value, self.provider)
            if runtime != self.runtime:
                raise ValueError('actual_loader_runtime_changed')
            save(self.run / 'loader-result.json', value)
            save(self.run / 'actual-runtime.json', runtime)
            self.state['runtime'] = runtime
        if self.last is None:
            self.last = 'runtime-smoke'
            command = shlex.join([sys.executable, str(self.worker), '--workspace', str(self.run / 'workspace'),
                                  '--skill', str(self.skill), '--provider', self.provider,
                                  '--loader-result', str(self.run / 'loader-result.json')])
            return self.tool(self.last, 'exec_command', {'cmd': command, 'login': False,
                             'yield_time_ms': 30000, 'max_output_tokens': 4000})
        if self.last not in outputs:
            raise ValueError('expected_actual_execution_result_missing')
        value = outputs[self.last]
        self.parts.append(value)
        result = execution_result(value)
        if not isinstance(result.get('output'), str):
            raise ValueError('execution_stdout_missing')
        # Intermediate sessions have no exit status. Preserve their stdout without
        # treating a null exit as failure or duplicating encoded success markers.
        complete = result.get('exit_code') is not None
        self.executions.append({'output': result['output'], **({'exit_code': result['exit_code']} if complete else {})})
        if complete:
            artifacts = smoke_execution(self.executions, self.run / 'workspace')
            if self.done:
                raise ValueError('unexpected_request_after_delivery')
            self.done = True
            save(self.run / 'smoke-output.json', self.parts)
            save(self.run / 'smoke-result.json', self.executions)
            save(self.run / 'artifact-result.json', {'artifacts': artifacts, 'synthetic': True, 'qualified': False})
            return message('[Deck](' + str(self.run / 'workspace/output/deck.pptx') + ') [PDF](' +
                           str(self.run / 'workspace/output/deck.pdf') + ')')
        session = result.get('session_id')
        if type(session) is not int or (self.session is not None and session != self.session):
            raise ValueError('execution_session_changed')
        self.session = session
        self.polls += 1
        if self.polls > 8:
            raise ValueError('synthetic_poll_budget_exceeded')
        self.last = 'runtime-poll-' + str(self.polls)
        return self.tool(self.last, 'write_stdin', {'session_id': session, 'chars': '',
                         'yield_time_ms': 10000, 'max_output_tokens': 4000})

    def respond(self, body):
        with self.lock:
            self.state['calls'] += 1
            save(self.run / ('model-request-' + str(self.state['calls']) + '.json'), body)
            try:
                return fixture_response(self.item(body), body['model'])
            except (ValueError, OSError, KeyError, TypeError) as error:
                if self.state['failure'] is None:
                    self.state['failure'] = str(error)
                    save(self.run / 'synthetic-error.json', {'failure': str(error),
                         'request': self.state['calls'], 'qualified': False})
                raise
