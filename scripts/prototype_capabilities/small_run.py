"""THROWAWAY macOS CLI runner for cases 05/07 only; requires explicit --live.

The existing observer rejects images/auxiliary contracts. Such rejections are
harness limitations, not model failures. Desktop execution is operator-owned.
"""
import argparse
import hashlib
import http.client
import threading
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from evaluation_proxy import EvaluationProxy
from pilot import plan, supervise, catalog_variant


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def observe(args):
    root = Path(os.environ['TOFA_PILOT_RUN'])
    settings = json.loads((root / 'settings.json').read_text())
    catalog_index = next(i for i,arg in enumerate(args) if arg.startswith('model_catalog_json='))
    catalog_path = Path(json.loads(args[catalog_index].split('=',1)[1]))
    if settings['variant'] == 'file-citations-v1':
        changed = catalog_variant(json.loads(catalog_path.read_text()),settings['model'])
        new_catalog = root/'variant-catalog.json'
        new_catalog.write_text(json.dumps(changed))
        args[catalog_index] = 'model_catalog_json='+json.dumps(str(new_catalog))
    original_request = http.client.HTTPConnection.request
    audit = []
    lock = threading.Lock()
    def audit_request(connection,method,url,body=None,headers={},**kwargs):
        if method=='POST' and url=='/responses' and isinstance(body,(bytes,str)):
            decoded=json.loads(body)
            instructions=decoded.get('instructions','')
            instruction_parts=[instructions] if isinstance(instructions,str) and instructions else []
            for item in decoded.get('input',[]):
                if not isinstance(item,dict) or item.get('role') not in ('system','developer'): continue
                content=item.get('content',[])
                if isinstance(content,str): instruction_parts.append(content)
                elif isinstance(content,list):
                    instruction_parts.extend(part['text'] for part in content
                        if isinstance(part,dict) and isinstance(part.get('text'),str))
            instructions='\n\n'.join(instruction_parts)
            with lock:
                audit.append({'model':decoded.get('model'),
                    'instructions_sha256':hashlib.sha256(instructions.encode()).hexdigest(),
                    'instruction_parts':len(instruction_parts),
                    'file_citation_guidance_present':':codex-file-citation' in instructions,
                    'inline_code_guidance_present':'Use inline code to make file paths clickable' in instructions,
                    'tools_count':len(decoded.get('tools',[]))})
                (root/'request-audit.json').write_text(json.dumps(audit))
        return original_request(connection,method,url,body,headers,**kwargs)
    http.client.HTTPConnection.request = audit_request
    index = next(i for i, arg in enumerate(args) if arg.startswith('model_providers.nebius-tofa='))
    match = re.search(r'base_url\s*=\s*("[^"]+")', args[index])
    with EvaluationProxy(json.loads(match.group(1)), os.environ['TOFA_API_KEY'],
            root/'requests.json', root/'budget.json', 'coding', 180,
            model=settings['model'], guardian_model='zai-org/GLM-5.3-Flash') as proxy:
        args[index] = args[index][:match.start(1)] + json.dumps(proxy.url) + args[index][match.end(1):]
        return subprocess.call([settings['codex'], *args], env=os.environ)


def run(options):
    cells = [r for r in plan()['runs'] if r['client']=='cli' and r['model']==options.model and r['case']==options.case]
    if len(cells)!=1: raise ValueError('unsupported model/case')
    root = Path(tempfile.mkdtemp(prefix='tofa-capability-run-', dir='/private/tmp'))
    workspace = root/'workspace'; workspace.mkdir()
    (workspace/'fixtures').mkdir()
    for filename in ('sample-deck.pptx', 'sample-deck.pdf'):
        shutil.copy2(HERE/'fixtures'/filename, workspace/'fixtures'/filename)
    shutil.copy2(HERE/'fixtures'/'probe.py', workspace/'probe.py')
    (root/'settings.json').write_text(json.dumps({'model':options.model,'codex':options.codex,'variant':options.variant}))
    (root/'budget.json').write_text(json.dumps({'used':0,'maximum':12}))
    before_fixtures = {p.name:digest(p) for p in (workspace/'fixtures').iterdir()}
    normal_home = Path.home()
    codex_home = Path(os.environ.get('CODEX_HOME', str(normal_home/'.codex')))
    protected = [codex_home/'config.toml',codex_home/'auth.json',normal_home/'.config/tofa/config.yml']
    before = [digest(p) for p in protected]
    shim_dir = root/'bin'; shim_dir.mkdir()
    shim = shim_dir/'codex'
    shim.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' '+shlex.quote(str(Path(__file__).resolve()))+' --observe "$@"\n')
    shim.chmod(0o700)
    env = dict(os.environ, PATH=str(shim_dir)+os.pathsep+os.environ.get('PATH',''),TOFA_PILOT_RUN=str(root))
    command = [options.launcher,'launch','codex','--model',options.model,'--allow-unverified',
        '--guardian-model','zai-org/GLM-5.3-Flash','--','--approve-for-me',
        'exec','--skip-git-repo-check','--json','-']
    result = supervise(command,180,plan()['prompts'][options.case],workspace,env)
    answers = '\n'.join(result.pop('final_messages'))
    commands = result.pop('command_evidence')
    fixture_preserved = before_fixtures=={p.name:digest(p) for p in (workspace/'fixtures').iterdir()}
    requests = json.loads((root/'requests.json').read_text()) if (root/'requests.json').exists() else []
    limitations = sorted({r.get('failure') for r in requests if r.get('failure')})
    evidence = {**cells[0], **result, 'id':cells[0]['id'].replace('baseline-1',options.variant+'-probe'), 'variant':options.variant, 'settings_unchanged':before==[digest(p) for p in protected],
        'corpus_version':plan()['corpus_version'],
        'source_sha256':{name:digest(HERE/name) for name in ('pilot.py','small_run.py')},
        'fixture_manifest_sha256':digest(HERE/'fixtures/manifest.json'),
        'prompt_sha256':hashlib.sha256(plan()['prompts'][options.case].encode()).hexdigest(),
        'fixtures_unchanged':fixture_preserved,'requests_used':json.loads((root/'budget.json').read_text())['used'],
        'observer_failures':limitations,'skill_read_observed':any('presentations/SKILL.md' in c['command'] for c in commands),
        'artifact_reference_syntax':{
            'native_citations':len(re.findall(r':codex-file-citation\{',answers)),
            'markdown_links':len(re.findall(r'\[[^\]]+\]\([^\)]+\)',answers)),
            'citation_paths_verified':all(Path(p).is_absolute() and Path(p).is_file() for p in re.findall(r':codex-file-citation\{path="([^"]+)"',answers)) if ':codex-file-citation{' in answers else False,
            'both_fixture_names_present':all(n in answers for n in ('sample-deck.pptx','sample-deck.pdf'))},
        'probe_exit_2_observed':any(c['exit_code']==2 and 'probe.py' in c['command'] for c in commands),
        'status':'inconclusive', 'reason':'criterion_review_required',
        'phase':'preflight_calibration', 'baseline_eligible':False,
        'run_directory_retained_locally':True}
    if limitations:
        evidence.update(status='infra_blocked',reason='observer_or_upstream_failure')
    elif not result['turn_completed'] or result['stop_reason']:
        evidence.update(status='failed',reason=result['stop_reason'] or 'client_turn_incomplete')
    evidence['guidance_target'] = 'desktop' if options.variant!='baseline' else 'native_cli_baseline'
    evidence['renderer_tested'] = False
    evidence['request_audit'] = json.loads((root/'request-audit.json').read_text()) if (root/'request-audit.json').exists() else []
    evidence['request_summary'] = [{'status':r.get('status'),'role':r.get('role'),'completed':r.get('completed'),
        'usage':r.get('usage'),'failure':r.get('failure')} for r in requests]
    # Raw diagnostics stay private and outside Git; public report is categorical.
    (root/'private-final.txt').write_text(answers)
    (root/'private-commands.json').write_text(json.dumps(commands))
    for p in root.iterdir():
        if p.is_file(): p.chmod(0o600)
    with options.output.open('x') as stream: json.dump(evidence,stream,indent=2);stream.write('\n')
    print(json.dumps({'report':str(options.output),'status':evidence['status'],
                      'requests':evidence['requests_used'],'private_run':str(root)}))


def main():
    if sys.argv[1:2]==['--observe']: return observe(sys.argv[2:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--case',choices=['05','07'],required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--variant',choices=['baseline','file-citations-v1'],default='baseline')
    parser.add_argument('--launcher',required=True)
    parser.add_argument('--codex',required=True)
    parser.add_argument('--output',type=Path,required=True)
    options=parser.parse_args()
    if options.output.exists() or not options.output.parent.is_dir(): parser.error('new report path required')
    run(options)
    return 0

if __name__=='__main__':sys.exit(main())
