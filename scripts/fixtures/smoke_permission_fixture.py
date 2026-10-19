"""Owned executable fixtures for the real smoke collector's permission regression.

No installed runtime, model or native client is used. Semantic smoke validation
remains separately qualified; this drives actual generated-file creation paths.
"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import presentation_smoke

workspace, runtime, seed = map(Path, sys.argv[1:])
(runtime/'packages').mkdir(exist_ok=True)
node = runtime/'dependencies/node/bin/node'
node.write_text('''#!/usr/bin/env python3
import os,sys,shutil
from pathlib import Path
if 'mark_artifact_operation_started' in sys.argv[1]: sys.exit(0)
workspace=Path(sys.argv[2]); output=workspace/'output'; output.mkdir(exist_ok=True)
seed=Path(os.environ['SMOKE_SEED'])
for name in ('deck.pptx','slide.png'):shutil.copyfile(seed/name,output/name)
shutil.copyfile(seed/'finalization.json',workspace/'build/finalization.json')
''')
node.chmod(0o700)
for name in ('soffice','pdfinfo'):
    executable=runtime/'dependencies/bin/override'/name
    executable.write_text('''#!/usr/bin/env python3
import os,shutil,sys
from pathlib import Path
if Path(sys.argv[0]).name=='soffice':
    output=Path(sys.argv[sys.argv.index('--outdir')+1]);shutil.copyfile(Path(os.environ['SMOKE_SEED'])/'deck.pdf',output/'deck.pdf')
''')
    executable.chmod(0o700)
paths={'node':str(node),'node_modules':str(runtime/'packages'),'python':str(runtime/'dependencies/python/bin/python3'),'bin':str(runtime/'dependencies/bin/override')}
os.environ['SMOKE_SEED']=str(seed)
os.umask(0o022)
sys.argv=['presentation_smoke','--workspace',str(workspace),'--skill',str(seed),'--provider','codex_app','--loader-result',str(seed/'loader.json')]
with patch.object(presentation_smoke,'from_loader_output',return_value={'paths':paths}):
    presentation_smoke.main()
