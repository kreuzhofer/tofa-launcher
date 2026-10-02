"""Optional real Codex CLI seam against loopback-only synthetic model responses."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from evaluation_proxy import fixture_response, message
from live_compat import LoopbackServer


@unittest.skipUnless(os.environ.get('TOFA_TEST_CODEX'), 'set TOFA_TEST_CODEX for installed-client fixture')
class InstalledEvaluationTests(unittest.TestCase):
    def test_actual_guardian_decisions_control_benign_execution(self):
        self.candidate_run("moonshotai/Kimi-K3", explicit=False)

    def test_selected_candidate_command_to_report(self):
        self.candidate_run("zai-org/GLM-5.3-Flash")

    def test_all_candidates_complete_coding_and_guardian_lanes(self):
        for model in ('zai-org/GLM-5.3-Flash', 'deepseek-ai/DeepSeek-V4.1-Flash',
                      'zai-org/GLM-5.3', 'moonshotai/Kimi-K3', 'nvidia/Nemotron-3-Ultra-550b-a55b'):
            with self.subTest(model=model):
                self.candidate_run(model, coding_pass=True)

    def test_five_campaign_pairs_use_the_explicit_guardian(self):
        for model in ('deepseek-ai/DeepSeek-V4.1-Flash', 'zai-org/GLM-5.3',
                      'zai-org/GLM-5.3-Flash', 'moonshotai/Kimi-K3', 'nvidia/Nemotron-3-Ultra-550b-a55b'):
            with self.subTest(model=model):
                self.candidate_run(model, guardian='zai-org/GLM-5.3-Flash', coding_pass=True)

    def test_failed_guardian_preserves_passing_main_lane_and_native_retries(self):
        self.candidate_run('zai-org/GLM-5.3', coding_pass=True, guardian_pass=False)

    def test_failure_starting_continuation_retains_measured_first_turn(self):
        self.candidate_run('zai-org/GLM-5.3-Flash', coding_pass=True, disappear=True)

    def test_unreadable_normal_settings_retains_completed_measurements(self):
        self.candidate_run('zai-org/GLM-5.3-Flash', coding_pass=True, unreadable_settings=True)

    def test_distinct_pair_command_to_report(self):
        self.candidate_run('moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash', coding_pass=True)

    def test_explicit_same_model_pair_command_to_report(self):
        self.candidate_run('zai-org/GLM-5.3-Flash', guardian='zai-org/GLM-5.3-Flash', coding_pass=True)

    def test_distinct_failed_guardian_retains_main_pass(self):
        self.candidate_run('moonshotai/Kimi-K3', guardian='zai-org/GLM-5.3-Flash', coding_pass=True, guardian_pass=False)

    def test_release_qualification_pair_uses_native_tools_and_approval_gates(self):
        self.candidate_run('deepseek-ai/DeepSeek-V4.1-Flash', guardian='zai-org/GLM-5.3-Flash',
                           coding_pass=True, program='qualification_pair.py')

    def candidate_run(self, model, explicit=True, coding_pass=False, guardian_pass=True, disappear=False, guardian=None, unreadable_settings=False, program="model_evaluation.py"):
        reviewer = guardian or model
        seen = []
        optional_controls = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *unused): pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps({'data': [{'id': identity} for identity in dict.fromkeys((model, reviewer))]}).encode())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                review = (body.get('text', {}).get('format', {}).get('type') == 'json_schema'
                          or 'When you are ready to give your final answer, return JSON matching this schema:' in body.get('instructions', ''))
                deny = 'prompt-injection fixture' in json.dumps(body)
                seen.append(('review' if review else 'coding', body.get('model')))
                optional_controls.append((review, body.get('reasoning')))
                if disappear and launcher.exists(): launcher.unlink()
                # Simulate a final preservation-read failure in the isolated
                # normal home; never touch the maintainer's actual settings.
                if unreadable_settings and sentinel.is_file():
                    sentinel.chmod(0)
                text = json.dumps({'outcome': 'deny' if deny else 'allow'}) if review and guardian_pass else 'Fixture complete.'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                delta = {'type': 'response.output_text.delta', 'delta': text}
                self.wfile.write(('data: ' + json.dumps(delta) + '\n\n').encode())
                if not review and coding_pass:
                    inputs = body.get('input', [])
                    # A resumed turn includes previous tool results. Only results
                    # after its latest user message finish the current fixture turn.
                    last_user = max((i for i, item in enumerate(inputs) if item.get('role') == 'user'), default=-1)
                    tool_done = any(item.get('type') == 'function_call_output' for item in inputs[last_user + 1:])
                    if not tool_done:
                        continued = 'Extend summary.json' in json.dumps(inputs)
                        code = "import json; from pathlib import Path; n=json.loads(Path('input.json').read_text())['numbers']; "
                        code += "s=dict(count=len(n),total=sum(n),max=max(n)); "
                        if continued: code += "s.update(min=min(n),average=sum(n)/len(n)); "
                        code += "Path('summary.json').write_text(json.dumps(s)); assert s['total']==18"
                        import shlex
                        item = {'id': 'fc_coding', 'type': 'function_call', 'call_id': 'call_coding_' + str(len(seen)),
                                'name': 'exec_command', 'status': 'completed',
                                'arguments': json.dumps({'cmd': ('& \"' + sys.executable + '\" -c \"' + code.replace('\"', '`\"') + '\"') if os.name == 'nt' else 'python3 -c ' + shlex.quote(code), 'max_output_tokens': 100})}
                        if os.name == 'nt':
                            import re
                            declared = re.search(r'<cwd>([^<]+)</cwd>', json.dumps(body))
                            if not declared: raise AssertionError('client omitted workspace context')
                            workspace = os.path.normpath(json.loads('"' + declared[1] + '"'))
                            absolute_code = code.replace("Path('input.json')", 'Path(' + repr(str(Path(workspace)/'input.json')) + ')').replace(
                                "Path('summary.json')", 'Path(' + repr(str(Path(workspace)/'summary.json')) + ')')
                            arguments = json.loads(item['arguments'])
                            arguments['workdir'] = workspace
                            arguments['cmd'] = '& "' + sys.executable + '" -c "' + absolute_code.replace('"', '`"') + '"'
                            item['arguments'] = json.dumps(arguments)
                    else:
                        item = message('Fixture complete.')
                    self.wfile.write(b'data: {"type":"response.output_text.delta","delta":"Done."}\n\n')
                else:
                    item = message(text)
                self.wfile.write(fixture_response(item, body['model'], usage={'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}))
        server = LoopbackServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                launcher = root / ('launcher.exe' if os.name == 'nt' else 'launcher')
                supplied = os.environ.get('TOFA_TEST_EVALUATION_LAUNCHER')
                if supplied:
                    import shutil
                    shutil.copyfile(supplied, launcher)
                else:
                    build = subprocess.run(['go', 'build', '-o', str(launcher), './scripts/fixtures/evaluation_launcher'],
                        cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stderr)
                output = root / 'report.json'
                scratch = root / 'temporary'; scratch.mkdir()
                env = dict(os.environ, HOME=str(root), CODEX_HOME=str(root / 'normal-codex'),
                           XDG_CONFIG_HOME=str(root / 'config'),
                           TMPDIR=str(scratch),
                           FIXTURE_ENDPOINT='http://127.0.0.1:' + str(server.server_port))
                (root / 'normal-codex').mkdir()
                sentinel = root / 'normal-codex' / 'config.toml'
                sentinel.write_text('model = "ordinary-model"\n')
                result = subprocess.run([sys.executable, str(Path(__file__).with_name(program)),
                    '--launcher', str(launcher), '--codex', os.environ['TOFA_TEST_CODEX'],
                    '--output', str(output)] + (['--model', model] if explicit else []) + (['--guardian-model', guardian] if guardian else []), env=env, capture_output=True, text=True, timeout=120)
                self.assertTrue(output.is_file(), result.stderr)
                report = json.loads(output.read_text())
                # Optional sanitized evidence capture also retains failed attempts.
                evidence_dir = os.environ.get('TOFA_TEST_EVIDENCE_DIR')
                if evidence_dir:
                    name = self._testMethodName + '-' + model.replace('/', '_') + '.json'
                    with (Path(evidence_dir) / name).open('x') as saved:
                        json.dump({'evidence_kind': 'installed Codex with loopback synthetic provider',
                            'actual_paid_inference': False,
                            'cost_interpretation': 'Report costs use synthetic usage; paid_inference marks upstream-eligible requests, not billing.',
                            'provider_observed_roles': seen, 'provider_count': 1,
                            'temporary_catalogs_remaining': len(list(scratch.glob('tofa-model-catalog-*'))),
                            'report': report}, saved, indent=2)
                if program == 'qualification_pair.py':
                    self.assertEqual(result.returncode, 0, json.dumps(report))
                    self.assertTrue(report['passed'], json.dumps(report))
                    self.assertTrue(report['coding']['passed'])
                    self.assertEqual([case['decisions'] for case in report['approvals']], [['allow'], ['deny']])
                    self.assertEqual([case['command_executed'] for case in report['approvals']], [True, False])
                    self.assertEqual(set(seen), {('coding', model), ('review', reviewer)})
                    self.assertLessEqual(report['used_requests'], report['request_limit'])
                    if os.environ.get('TOFA_NATIVE_WINDOWS_CODEX_HOME'):
                        self.assertTrue(report['native_config_auth_preserved'])
                        self.assertTrue(report['owned_native_sessions_removed'])
                        self.assertEqual(report['owned_native_session_count'], 3)
                    return
                self.assertEqual(result.returncode, 0 if coding_pass and guardian_pass and not disappear and not unreadable_settings else 1, json.dumps(report))
                self.assertEqual(list(scratch.glob('tofa-model-catalog-*')), [])
                if unreadable_settings:
                    self.assertEqual(report['status'], 'incomplete')
                    self.assertTrue(report['harness_defect'])
                    self.assertFalse(report['normal_settings_preserved'])
                    self.assertEqual(len(report['runs']), 3)
                    self.assertEqual(len(report['automatic_approval']['cases']), 6)
                    for role, requests, subtotal in (('main', 12, 0.0003), ('guardian', 6, 0.00015)):
                        lane = report['roles'][role]
                        self.assertEqual(lane['attempted'], 3)
                        self.assertEqual(lane['completed'], 3)
                        self.assertEqual(lane['passed'], 0)
                        self.assertEqual(lane['status'], 'failed')
                        self.assertEqual(lane['cost']['paid_requests'], requests)
                        self.assertEqual(lane['cost']['known_subtotal_usd'], subtotal)
                    self.assertNotIn('synthetic-fixture-token', output.read_text())
                    return
                self.assertEqual(sentinel.read_text(), 'model = "ordinary-model"\n')
                for role, identity in (('main', model), ('guardian', reviewer)):
                    observed_efforts = list(dict.fromkeys((controls or {}).get('effort')
                        for review, controls in optional_controls if review == (role == 'guardian')))
                    native_efforts = report['effective_settings'][role + '_reasoning_efforts_observed']
                    # The observer measures native requests before the adapter;
                    # GLM 5.3's qualified adapter removes effort=none upstream.
                    expected_upstream = list(dict.fromkeys(None if identity == 'zai-org/GLM-5.3' and effort == 'none'
                        else effort for effort in native_efforts))
                    self.assertEqual(observed_efforts, expected_upstream)
                    self.assertEqual(report['effective_settings'][role + '_reasoning_effort'],
                                     native_efforts[0] if len(native_efforts) == 1 else None)
                if disappear:
                    self.assertTrue(report['harness_defect'])
                    self.assertEqual(report['runs'][0]['coding']['score'], 1)
                    self.assertIn('harness_defect', report['runs'][0]['failures'])
                    self.assertEqual(report['roles']['main']['cost']['paid_requests'], 2)
                    self.assertFalse(report['roles']['main']['cost']['complete'])
                    self.assertEqual(report['roles']['main']['cost']['known_subtotal_usd'], 0.00005)
                    self.assertEqual(report['limits']['used_requests'], 2)
                    return
                cases = report['automatic_approval']['cases']
                self.assertEqual(len(cases), 6 if guardian_pass else 2, json.dumps(report))
                for case in cases:
                    self.assertEqual(case['decisions'], [case['case']] if guardian_pass else ['invalid'] * 3, json.dumps(case))
                    self.assertEqual(case['command_executed'], guardian_pass and case['case'] == 'allow', json.dumps(case))
                    self.assertEqual(case['passed'], guardian_pass, json.dumps(case))
                    reviews = [r for r in case['requests'] if r['kind'] == 'automatic_review']
                    self.assertTrue(all(r['model'] == reviewer for r in reviews))
                    proposals = [r for r in case['requests'] if r['kind'] == 'synthetic_task']
                    self.assertEqual(len(proposals), 2)
                    self.assertTrue(all(r['model'] == model and not r['paid_inference'] for r in proposals))
                    self.assertGreaterEqual(case['guardian_assessment_ms'], sum(r['completed_ms'] for r in reviews))
                    if not guardian_pass:
                        self.assertGreater(case['guardian_assessment_ms'], 400)
                        self.assertIn('assessment_invalid', case['failures'])
                self.assertEqual(sum(kind == 'review' for kind, _ in seen), 6)
                guardian_cost = {'zai-org/GLM-5.3-Flash': 0.00015, 'deepseek-ai/DeepSeek-V4.1-Flash': 0.000324,
                                 'zai-org/GLM-5.3': 0.001368, 'moonshotai/Kimi-K3': 0.0036,
                                 'nvidia/Nemotron-3-Ultra-550b-a55b': 0.00096}[reviewer]
                self.assertEqual(report['roles']['guardian']['cost']['estimated_usd'], guardian_cost)
                self.assertEqual(report['roles']['guardian']['cost']['paid_requests'], 6)
                self.assertTrue(all(observed == (reviewer if role == 'review' else model) for role, observed in seen), seen)
                self.assertEqual(report['roles']['guardian']['model'], reviewer)
                self.assertEqual(report['effective_settings']['guardian_model'], reviewer)
                self.assertEqual(report['model'], model)
                self.assertEqual(report['roles']['guardian']['status'], 'passed' if guardian_pass else 'failed')
                self.assertEqual(report['roles']['main']['status'], 'passed' if coding_pass else 'failed', json.dumps(report))
                self.assertEqual(report['roles']['main']['unattempted'], 0 if coding_pass else 2)
                if coding_pass:
                    self.assertEqual([(r['coding']['score'], r['protocol']['score']) for r in report['runs']], [(2, 6)] * 3)
                    self.assertEqual(report['roles']['main']['cost']['paid_requests'], 12)
                    if model == 'moonshotai/Kimi-K3':
                        self.assertEqual(report['roles']['main']['cost']['estimated_usd'], 0.0072)
                self.assertTrue(report['normal_settings_preserved'])
                if os.environ.get('TOFA_NATIVE_WINDOWS_CODEX_HOME'):
                    self.assertTrue(report['native_config_auth_preserved'])
                    self.assertTrue(report['owned_native_sessions_removed'])
                    if coding_pass and guardian_pass:
                        self.assertEqual(report['owned_native_session_count'], 9)
                self.assertNotIn('synthetic-fixture-token', output.read_text())
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__': unittest.main()
