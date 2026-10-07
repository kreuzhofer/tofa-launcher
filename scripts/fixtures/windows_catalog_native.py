"""External native engine stand-in for catalog settings protocol tests."""
import json
import os
from pathlib import Path
import sys

path = Path(os.environ['CATALOG_TEST_SETTINGS'])
for line in sys.stdin:
    message = json.loads(line)
    params = message.get('params', {})
    if message['method'] == 'model/list':
        result = {'data': [{'model': model} for model in ('tofa-catalog-a', 'tofa-catalog-b')], 'nextCursor': None}
    elif message['method'] == 'thread/start':
        result = {'thread': {'id': 'synthetic-thread', 'cwd': os.environ['CATALOG_TEST_WORKSPACE']},
            'model': 'tofa-catalog-a', 'modelProvider': 'tofa-catalog', 'approvalsReviewer': 'auto_review',
            'approvalPolicy': 'on-request', 'sandbox': {'type': 'workspaceWrite', 'networkAccess': False},
            'runtimeWorkspaceRoots': []}
    elif message['method'] == 'turn/start':
        result = {'turn': {'id': 'synthetic-turn'}, 'receivedModel': params.get('model'), 'receivedEffort': params.get('effort')}
    elif message['method'] == 'config/read':
        if os.environ.get('CATALOG_TEST_MODE') == 'native_error':
            print(json.dumps({'id': message['id'], 'error': {'code': -32603, 'message': 'synthetic engine failure'}}), flush=True)
            continue
        result = {'config': json.loads(path.read_text()), 'layers': [
            {'name': {'type': 'user', 'file': str(path)}, 'version': 'fixture-version'}]}
        if os.environ.get('CATALOG_TEST_MODE') == 'missing_layer': result['layers'] = []
        if os.environ.get('CATALOG_TEST_MODE') in ('same_file', 'different_file'):
            alias = path.parent / 'native-layer.toml'
            if os.environ['CATALOG_TEST_MODE'] == 'same_file': os.link(path, alias)
            else: alias.write_text(path.read_text())
            result['layers'][0]['name']['file'] = str(alias)
    elif message['method'] in ('config/value/write', 'config/batchWrite'):
        settings = json.loads(path.read_text())
        for edit in params.get('edits', [params]): settings[edit['keyPath']] = edit['value']
        path.write_text(json.dumps(settings))
        result = {'status': 'ok', 'version': 'fixture-updated', 'filePath': str(path)}
    else:
        result = {}
    print(json.dumps({'id': message['id'], 'result': result}), flush=True)
