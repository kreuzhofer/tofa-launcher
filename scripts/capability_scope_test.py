"""Declared qualification scope at the authenticated Observer HTTP boundary."""
import hashlib
import json
from pathlib import Path
import unittest

from capability_observer import NAMING_MODEL, Observer, hashed
import capability_observer_test as boundary_tests


class DeclaredScopeTests(unittest.TestCase):
    services = {'moonshotai/Kimi-K3': 'token_factory', 'gpt-6-astra': 'native'}

    def boundary(self, change=None, file_change=None, **options):
        helper = boundary_tests.SplitAuthorizationTests()
        def create(run, **kwargs):
            declaration = {'schema': 'tofa-observer-scope-v1', 'attempt': 'scope-test',
                'root': str(run.resolve()), 'threads': [{'label': 'switch', 'thread_id': None,
                    'workspace': str((run / 'workspace').resolve()), 'initial_user_messages_sha256': None,
                    'turns': [{'model': model, 'service': self.services[model], 'prompt': prompt}
                        for model, prompt in [('moonshotai/Kimi-K3', 'Remember scoped lighthouse.'),
                                              ('gpt-6-astra', 'Recall scoped lighthouse.'),
                                              ('moonshotai/Kimi-K3', 'Finish scoped lighthouse.')]]}]}
            if change: change(declaration)
            path = run / 'scope.json'
            raw = json.dumps(declaration).encode(); path.write_bytes(raw); path.chmod(0o600)
            digest = hashlib.sha256(raw).hexdigest()
            if file_change: digest = file_change(path, digest)
            return Observer(run, **kwargs, scope_declaration=path,
                scope_sha256=digest, scope_attempt='scope-test')
        def upstream(handler):
            body = json.loads(handler.raw_body)
            handler.send_response(200); handler.end_headers()
            event = {'type': 'response.completed', 'response': {'model': NAMING_MODEL if body['model'] == 'gpt-6-luna' else body['model'], 'output': [], 'usage': {'output_tokens': 2}}}
            handler.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
        return helper.boundary(observer_type=create, model_services=self.services, response=upstream, **options)

    def body(self, observer, model, prompt, turn='turn-1', thread='thread-1', prior=None):
        users = prior or [{'role': 'user', 'content': str((observer.run / 'workspace').resolve())}]
        return {'model': model, 'stream': True, 'tools': [],
            'client_metadata': {'thread_id': thread, 'turn_id': turn},
            'input': users + [{'role': 'user', 'content': prompt}]}

    def send(self, observer, body, expected=200):
        helper = boundary_tests.SplitAuthorizationTests()
        status, data = helper.request(observer, '/responses',
            [('Authorization', 'Bearer ' + helper.native), ('X-TOFA-Launch', helper.inference)], body)
        self.assertEqual(status, expected, data)

    def test_predeclared_switching_and_tool_continuation_are_bounded(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            first = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.')
            self.send(observer, first)
            continued = dict(first, input=first['input'] + [
                {'type': 'function_call', 'name': 'exec_command', 'call_id': 'inspect', 'arguments': '{"cmd":"printf scoped"}'},
                {'type': 'function_call_output', 'call_id': 'inspect', 'output': 'scoped'}])
            self.send(observer, continued)
            second = self.body(observer, 'gpt-6-astra', 'Recall scoped lighthouse.', 'turn-2', prior=first['input'])
            self.send(observer, second)
            third = self.body(observer, 'moonshotai/Kimi-K3', 'Finish scoped lighthouse.', 'turn-3', prior=second['input'])
            self.send(observer, third)
            self.assertEqual(len([entry for entry in seen if entry[0] == '/responses']), 4)
            self.assertEqual([r['scope']['turn_index'] for r in observer.records], [0, 0, 1, 2])
            state = json.loads((observer.run / 'scope-state.json').read_text())
            self.assertEqual(state['threads'][0]['thread_id'], 'thread-1')
            self.assertEqual(state['threads'][0]['user_messages_sha256'], hashed(third['input'])['sha256'])
            self.assertNotIn('lighthouse', json.dumps(observer.records))
            self.send(observer, self.body(observer, 'moonshotai/Kimi-K3', 'Undeclared task.', 'turn-4', prior=third['input']), 403)
            self.assertEqual(len([entry for entry in seen if entry[0] == '/responses']), 4)
            self.assertEqual(observer.reason, 'scope_mismatch')

    def test_new_turns_cannot_escape_declared_thread_model_prompt_or_history(self):
        changes = {
            'model': lambda body: body.update(model='moonshotai/Kimi-K3'),
            'prompt': lambda body: body['input'][-1].update(content='Undeclared private prompt.'),
            'thread': lambda body: body['client_metadata'].update(thread_id='foreign-thread'),
            'turn-reuse': lambda body: body['client_metadata'].update(turn_id='turn-1'),
            'history': lambda body: body['input'][1].update(content='Replaced previous task.'),
            'missing-origin': lambda body: body.update(client_metadata={}),
            'additional-user': lambda body: body['input'].insert(-1, {'role': 'user', 'content': 'Extra task.'}),
        }
        helper = boundary_tests.SplitAuthorizationTests()
        for name, change in changes.items():
            with self.subTest(name=name), self.boundary() as (observer, seen, registration):
                helper.register(observer, registration)
                first = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.')
                self.send(observer, first)
                following = self.body(observer, 'gpt-6-astra', 'Recall scoped lighthouse.', 'turn-2', prior=first['input'])
                change(following)
                self.send(observer, following, 400 if name == 'turn-reuse' else 403)
                self.assertEqual(len([entry for entry in seen if entry[0] == '/responses']), 1)
                self.assertEqual(observer.reason, 'conflicting_review_origin' if name == 'turn-reuse' else 'scope_mismatch')

    def test_scope_is_consumed_once_and_file_changes_stop_the_attempt(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            path = observer.run / 'scope.json'; digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                Observer(observer.run, model=observer.model, guardian=observer.guardian, limits=observer.limits,
                    model_services=self.services, scope_declaration=path, scope_sha256=digest, scope_attempt='scope-test')
            self.assertEqual((observer.run / 'scope-consumed.json').stat().st_mode & 0o777, 0o600)
            helper.register(observer, registration)
            path.write_text(path.read_text() + ' ')
            self.send(observer, self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.'), 403)
            self.assertFalse(any(entry[0] == '/responses' for entry in seen))

    def test_malformed_declarations_never_start_an_observer(self):
        changes = {
            'extra': lambda d: d.update(wildcard=True),
            'root': lambda d: d.update(root='/tmp/foreign-run'),
            'attempt': lambda d: d.update(attempt='different-attempt'),
            'service': lambda d: d['threads'][0]['turns'][0].update(service='native'),
            'duplicate-prompt': lambda d: d['threads'][0]['turns'][1].update(prompt=d['threads'][0]['turns'][0]['prompt']),
            'existing-without-hash': lambda d: d['threads'][0].update(thread_id='existing-thread'),
            'fresh-outside-root': lambda d: d['threads'][0].update(workspace='/tmp'),
            'too-many-turns': lambda d: d['threads'][0].update(turns=d['threads'][0]['turns'] * 6),
        }
        for name, change in changes.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                with self.boundary(change): self.fail('invalid scope listened')

    def test_independent_threads_bind_once_and_do_not_share_progress(self):
        def declaration(data):
            thread = dict(data['threads'][0], label='independent', turns=[{
                'model': 'gpt-6-astra', 'service': 'native', 'prompt': 'Independent scoped task.'}])
            data['threads'].append(thread)
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary(declaration) as (observer, seen, registration):
            helper.register(observer, registration)
            first = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.')
            self.send(observer, first)
            self.send(observer, self.body(observer, 'gpt-6-astra', 'Independent scoped task.', thread='independent'))
            self.send(observer, self.body(observer, 'gpt-6-astra', 'Recall scoped lighthouse.', 'turn-2', prior=first['input']))
            self.assertEqual([r['scope']['label'] for r in observer.records], ['switch', 'independent', 'switch'])
            self.send(observer, self.body(observer, 'gpt-6-astra', 'Independent scoped task.', thread='another'), 403)

    def test_existing_history_requires_exact_predeclared_user_prefix(self):
        import tempfile
        helper = boundary_tests.SplitAuthorizationTests()
        with tempfile.TemporaryDirectory() as old_workspace:
            prefix = [{'role': 'user', 'content': str(Path(old_workspace).resolve())},
                      {'role': 'user', 'content': 'Private earlier task.'}]
            def declaration(data):
                data['threads'][0].update(thread_id='existing', workspace=str(Path(old_workspace).resolve()),
                    initial_user_messages_sha256=hashed(prefix)['sha256'])
            with self.boundary(declaration) as (observer, seen, registration):
                helper.register(observer, registration)
                body = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.', thread='existing', prior=prefix)
                body['input'].insert(-1, {'role': 'assistant', 'content': 'Earlier answer.'})
                self.send(observer, body)
                self.assertEqual(observer.records[0]['scope']['turn_index'], 0)
                self.assertEqual(list(Path(old_workspace).iterdir()), [])
            with self.boundary(declaration) as (observer, seen, registration):
                helper.register(observer, registration)
                changed = [prefix[0], {'role': 'user', 'content': 'Different history.'}]
                self.send(observer, self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.', thread='existing', prior=changed), 403)

    @staticmethod
    def title(prompt):
        body = json.loads((boundary_tests.SCRIPT_ROOT / 'internal/tofa/testdata/desktop-luna6-title-request.json').read_text())
        body['input'][-1]['content'][0]['text'] = 'Return a title and description for: ' + prompt
        return body

    def test_title_only_scope_never_claims_parent_or_main_observation(self):
        def declaration(data):
            data.update(threads=[], titles=[{'thread_id': 'intended-ui-history', 'prompt': 'Native history naming task.'}])
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary(declaration) as (observer, seen, registration):
            helper.register(observer, registration)
            self.send(observer, self.title('Native history naming task.'))
            scope = observer.records[0]['scope']
            self.assertTrue(scope['parent_unverified'])
            self.assertFalse(scope['main_observed'])
            self.assertEqual(scope['contexts'][0]['intended_ui_thread_sha256'], hashed('intended-ui-history')['sha256'])
            self.assertEqual(observer.records[0]['routed_model'], NAMING_MODEL)
            self.assertEqual(observer.review_origins, {})
            self.send(observer, self.body(observer, 'gpt-6-astra', 'Native history naming task.', thread='intended-ui-history'), 403)
            self.assertEqual(len([r for r in seen if r[0] == '/responses']), 1)
        with self.boundary(declaration) as (observer, seen, registration):
            helper.register(observer, registration)
            review = boundary_tests.BoundaryTests.developer_review()
            review['client_metadata']['x-codex-parent-thread-id'] = 'intended-ui-history'
            self.send(observer, review, 400)
            self.assertFalse(any(r[0] == '/responses' for r in seen))

    def test_title_scope_preserves_strict_role_and_exact_declared_context(self):
        changes = {
            'undeclared-context': lambda body: body['input'][-1]['content'][0].update(text='An unrelated private task.'),
            'guardian-role': lambda body: body['client_metadata'].update({'x-openai-subagent': 'guardian'}),
            'unknown-role': lambda body: body['client_metadata'].update({'x-codex-turn-metadata': '{"thread_source":"compaction"}'}),
        }
        helper = boundary_tests.SplitAuthorizationTests()
        for name, change in changes.items():
            def declaration(data):
                data.update(threads=[], titles=[{'thread_id': 'intended-ui-history', 'prompt': 'Native history naming task.'}])
            with self.subTest(name=name), self.boundary(declaration) as (observer, seen, registration):
                helper.register(observer, registration)
                body = self.title('Native history naming task.'); change(body)
                self.send(observer, body, 403 if name == 'undeclared-context' else 400)
                self.assertFalse(any(r[0] == '/responses' for r in seen))

    def test_routed_title_requires_admitted_main_and_review_keeps_original_turn(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            self.send(observer, self.title('Remember scoped lighthouse.'), 403)
            self.assertFalse(any(r[0] == '/responses' for r in seen))
        with self.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            first = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.')
            self.send(observer, first)
            self.send(observer, self.body(observer, 'gpt-6-astra', 'Recall scoped lighthouse.', 'turn-2', prior=first['input']))
            review = boundary_tests.BoundaryTests.developer_review()
            review['client_metadata'].update({'x-codex-parent-thread-id': 'thread-1', 'parent_turn_id': 'turn-1'})
            self.send(observer, review)
            self.send(observer, self.title('Remember scoped lighthouse.'))
            self.assertEqual(observer.records[2]['scope']['turn_index'], 0)
            self.assertEqual(observer.records[2]['routed_model'], observer.guardian)
            self.assertTrue(observer.records[3]['scope']['main_observed'])
            self.assertTrue(observer.records[3]['scope']['parent_unverified'])
            review['client_metadata']['parent_turn_id'] = 'unobserved-turn'
            self.send(observer, review, 400)
            self.assertEqual(len([r for r in seen if r[0] == '/responses']), 4)

    def test_changed_scope_file_permissions_are_rejected_before_forwarding(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            (observer.run / 'scope.json').chmod(0o644)
            self.send(observer, self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.'), 403)
            self.assertFalse(any(r[0] == '/responses' for r in seen))


    def test_declaration_file_integrity_is_checked_before_listening(self):
        def shared(path, digest):
            path.chmod(0o644); return digest
        def duplicate(path, digest):
            raw = path.read_bytes().replace(b'{', b'{"schema":"duplicate",', 1)
            path.write_bytes(raw); return hashlib.sha256(raw).hexdigest()
        def symlink(path, digest):
            target = path.with_name('scope-original.json'); path.rename(target)
            path.symlink_to(target); return digest
        for name, change in [('private-mode', shared), ('duplicate-json', duplicate),
                             ('symlink', symlink), ('wrong-digest', lambda p, d: '0' * 64)]:
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                with self.boundary(file_change=change): self.fail('invalid scope listened')

    def test_repeated_prompt_with_a_new_turn_does_not_advance_or_replay(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            helper.register(observer, registration)
            first = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.')
            self.send(observer, first)
            self.send(observer, self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.',
                'turn-2', prior=first['input']), 403)
            self.assertEqual(len([r for r in seen if r[0] == '/responses']), 1)

    def test_scope_never_downgrades_to_legacy_single_bearer_registration(self):
        helper = boundary_tests.SplitAuthorizationTests()
        with self.boundary() as (observer, seen, registration):
            status, _ = helper.request(observer, '/register', [('Authorization', 'Bearer ' + observer.secret)],
                {'endpoint': registration['endpoint'], 'token': helper.control})
            self.assertEqual(status, 200)
            status, _ = helper.request(observer, '/responses', [('Authorization', 'Bearer ' + helper.control)],
                self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.'))
            self.assertEqual(status, 403)
            self.assertFalse(any(r[0] == '/responses' for r in seen))


    def test_workspace_uses_exact_canonical_cwd_not_substring_matching(self):
        helper = boundary_tests.SplitAuthorizationTests()
        for valid in (True, False):
            with self.subTest(valid=valid), self.boundary() as (observer, seen, registration):
                helper.register(observer, registration)
                workspace = str((observer.run / 'workspace').resolve())
                alias = workspace.replace('/private/tmp/', '/tmp/') if valid else workspace + '-unrelated'
                body = self.body(observer, 'moonshotai/Kimi-K3', 'Remember scoped lighthouse.',
                    prior=[{'role': 'user', 'content': '<environment_context>\n<cwd>' + alias + '</cwd>\n</environment_context>'}])
                self.send(observer, body, 200 if valid else 403)
                self.assertEqual(len([r for r in seen if r[0] == '/responses']), 1 if valid else 0)


if __name__ == '__main__':
    unittest.main()
