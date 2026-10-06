"""Limited-user desktop qualification; use only a dedicated test session."""
import json
import os
import ntpath
from pathlib import Path
import re
import sys
import time

from windows_template_probe import NativeEngine, workspace_owner
from windows_desktop_runtime import desktop_smoke


def main():
    root = Path(__file__).resolve().parent
    request = json.loads((root / 'request.json').read_text(encoding='utf-8-sig'))
    report = {'run': request['run'], 'phase': 'desktop', 'ok': False,
              'reason': 'desktop_readiness_failed', 'checks': {}}
    engine = None
    started = time.monotonic()
    progress = json.loads((root / 'output/progress.json').read_text(encoding='utf-8-sig'))
    offset = progress['checkpoints'][-1]['elapsed_ms']
    def checkpoint(stage):
        progress['checkpoints'].append({'stage': stage, 'elapsed_ms': offset + int((time.monotonic() - started) * 1000)})
        temporary = root / 'output/progress.tmp'
        temporary.write_text(json.dumps(progress), encoding='utf-8')
        os.replace(temporary, root / 'output/progress.json')
    try:
        checkpoint('desktop_authentication')
        if request.get('test_auth') != 'native-session':
            raise ValueError('desktop_authentication_required')
        if not re.fullmatch(r'tofa-(?:run|template)-[0-9a-f]{32}', request.get('workspace_run', '')):
            raise ValueError('desktop_workspace_invalid')
        identity = json.loads((root / 'output/identity.json').read_text(encoding='utf-8-sig'))
        workspace = Path.home() / request['workspace_run'] / 'workspace'
        if not workspace.is_dir() or workspace_owner(workspace) != request['sid']:
            raise ValueError('desktop_workspace_invalid')
        engine = NativeEngine(identity['engine'], workspace, (
            'approval_policy="on-request"', 'approvals_reviewer="auto_review"',
            'projects={' + json.dumps(str(workspace)) + '={trust_level="trusted"}}'))
        initialized = engine.call('initialize', {'clientInfo': {'name': 'tofa_desktop_readiness', 'version': '1'},
                                               'capabilities': {'experimentalApi': True}})
        if 'result' not in initialized: raise ValueError('desktop_readiness_failed')
        engine.send({'method': 'initialized'})
        account = engine.call('account/read', {'refreshToken': False}).get('result', {}).get('account')
        report['checks']['authenticated'] = isinstance(account, dict) and account.get('type') == 'chatgpt'
        if not report['checks']['authenticated']: raise ValueError('desktop_authentication_required')
        settings = engine.call('config/read', {'includeLayers': False, 'cwd': str(workspace)}).get('result', {}).get('config', {})
        normalized = ntpath.normcase(ntpath.normpath(str(workspace)))
        report['checks'].update(
            workspace_trusted=any(ntpath.normcase(ntpath.normpath(key)) == normalized and value.get('trust_level') == 'trusted'
                                  for key, value in settings.get('projects', {}).items() if isinstance(value, dict)),
            automatic_review=settings.get('approvals_reviewer') == 'auto_review',
            full_access_disabled=settings.get('sandbox_mode') == 'workspace-write')
        if not all(report['checks'].values()): raise ValueError('desktop_policy_mismatch')
        if not engine.close(): raise ValueError('desktop_readiness_failed')
        engine = None
        if request.get('desktop_readiness_only'):
            report.update(ok=True, reason='desktop_readiness_passed')
        else:
            desktop_smoke(root, request, identity, workspace, report, checkpoint)
            report.update(ok=True, reason='desktop_smoke_passed')
    except ValueError as error:
        allowed = {'desktop_authentication_required', 'desktop_workspace_invalid', 'desktop_control_unsupported',
                   'desktop_policy_mismatch', 'desktop_startup_failed', 'desktop_command_failed', 'desktop_cleanup_failed',
                   'engine_identity_mismatch', 'native_client_busy'}
        report['reason'] = str(error) if str(error) in allowed else 'desktop_readiness_failed'
    except Exception:
        report['reason'] = 'desktop_readiness_failed'
    finally:
        try:
            report['checks']['readiness_engine_exited'] = engine.close() if engine else True
        except Exception:
            report['checks']['readiness_engine_exited'] = False
            report['ok'] = False
        (root / 'output/result.json').write_text(json.dumps(report), encoding='utf-8')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
