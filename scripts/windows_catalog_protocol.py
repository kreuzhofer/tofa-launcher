"""Opt-in synthetic catalog protocol experiment; no production routing."""
import json
from pathlib import Path

MODELS = ('tofa-catalog-a', 'tofa-catalog-b')
PROVIDER = 'tofa-catalog'
DEFAULT_KEYS = {'model', 'model_reasoning_effort', 'service_tier', 'plan_mode_reasoning_effort'}


class CatalogProtocol:
    def __init__(self, config, record, write):
        self.config = config
        self.record = record
        self.write = write
        self.pending = {}

    def error(self, identity):
        self.write((json.dumps({'id': identity, 'error': {'code': -32600,
            'message': 'Synthetic desktop default write refused; no settings were changed'}}) + '\n').encode())

    def background(self, params):
        # Capture only fixed metadata markers, never prompt text or thread IDs.
        markers = set()
        def visit(value, depth=0):
            if depth > 8: return
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ('thread_source', 'turn_trigger', 'threadSource', 'turnTrigger') and child in ('thread_title', 'thread_summary'):
                        markers.add(child)
                    visit(child, depth + 1)
            elif isinstance(value, list):
                for child in value[:64]: visit(child, depth + 1)
            elif isinstance(value, str) and value.startswith('{') and len(value) < 4096:
                try: visit(json.loads(value), depth + 1)
                except ValueError: pass
        visit(params)
        self.record('catalog_background_turn_refused', category='title' if 'thread_title' in markers else
                    'summary' if 'thread_summary' in markers else 'unclassified')

    def request(self, raw):
        message = json.loads(raw)
        if not isinstance(message, dict):
            self.error(None)
            return None
        method, params = message.get('method'), message.get('params', {})
        if method not in ('config/value/write', 'config/batchWrite'): return raw
        if not isinstance(params, dict):
            self.error(message.get('id'))
            return None
        edits = params.get('edits') if method == 'config/batchWrite' else [params]
        if not isinstance(edits, list) or not edits or not all(isinstance(edit, dict) for edit in edits):
            self.error(message.get('id'))
            return None
        keys = [edit.get('keyPath') for edit in edits]
        if any(not isinstance(key, str) for key in keys):
            self.error(message.get('id'))
            return None
        defaults = any(key in DEFAULT_KEYS or isinstance(key, str) and key.startswith(('profiles', 'model.')) for key in keys)
        if not defaults: return raw
        valid = (params.get('filePath') is None and all(key in DEFAULT_KEYS for key in keys)
                 and all(edit.get('mergeStrategy') in ('replace', 'upsert') and 'value' in edit
                         and (edit['value'] is None or isinstance(edit['value'], str)) for edit in edits))
        fields = dict(method=method, keys=[key if key in DEFAULT_KEYS else 'other' for key in keys],
                    values=[edit.get('value') if edit.get('value') in (*MODELS, 'low', 'high', None) else 'other' for edit in edits],
                    reload=params.get('reloadUserConfig') is True, versioned=params.get('expectedVersion') is not None)
        self.record('catalog_default_write', **fields, disposition='pending' if valid else 'refused')
        if not valid:
            self.error(message.get('id'))
            return None
        if len(self.pending) >= 128: raise ValueError('pending_request_limit')
        self.pending[str(message['id'])] = (params.get('expectedVersion'), fields)
        return (json.dumps({'id': message['id'], 'method': 'config/read',
                            'params': {'includeLayers': True}}) + '\n').encode()

    def response(self, raw):
        message = json.loads(raw)
        identity = str(message.get('id'))
        if message.get('method') or identity not in self.pending: return raw
        expected, fields = self.pending.pop(identity)
        if 'error' in message:
            self.record('catalog_default_write', **fields, disposition='refused')
            return raw
        result = message.get('result', {})
        def user_file(layer):
            name = layer.get('name', {})
            if not isinstance(name, dict) or name.get('type') != 'user' or not isinstance(name.get('file'), str): return False
            try: return Path(name['file']).samefile(self.config['config_file'])
            except OSError: return False
        layers = result.get('layers', [])
        versions = [layer.get('version') for layer in layers if user_file(layer)]
        self.record('catalog_layer_check', user_layers=sum(layer.get('name', {}).get('type') == 'user' for layer in layers),
                    matching_layers=len(versions), version_present=len(versions) == 1 and bool(versions[0]),
                    exact_path=any(layer.get('name', {}).get('file') == self.config['config_file'] for layer in layers),
                    extended_path=any(str(layer.get('name', {}).get('file', '')).startswith('\\\\?\\') for layer in layers))
        if len(versions) != 1 or not versions[0] or expected not in (None, versions[0]):
            self.record('catalog_default_write', **fields, disposition='refused')
            self.error(message.get('id'))
            return None
        version = versions[0]
        self.record('catalog_default_write', **fields, disposition='session_override')
        return (json.dumps({'id': message['id'], 'result': {'status': 'okOverridden', 'version': version,
            'filePath': self.config['config_file'], 'overriddenMetadata': {
                'message': 'Synthetic desktop session override; CLI defaults were not written.',
                'effectiveValue': result.get('config', {}).get('model'),
                'overridingLayer': {'name': {'type': 'sessionFlags'}, 'version': version}}}}) + '\n').encode()
