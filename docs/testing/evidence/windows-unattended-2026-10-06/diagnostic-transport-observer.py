#!/usr/bin/python3
import subprocess,sys,json,time,hashlib
r=subprocess.run(['/Applications/UTM.app/Contents/MacOS/utmctl',*sys.argv[1:]],input=sys.stdin.buffer.read() if sys.argv[1:3]==['file','push'] else None,capture_output=True)
b=r.stdout+r.stderr
if r.returncode or r.stderr or b'Error from event:' in r.stdout:
 patterns={ 'missing_file':b'The system cannot find the file specified.', 'missing_path':b'The system cannot find the path specified.', 'sharing_violation':b'being used by another process', 'access_denied':b'Access is denied', 'agent_not_running':b'guest agent is not running', 'agent_timeout':b'guest agent', 'osstatus_2700':b'OSStatus error -2700', 'clixml_progress':b'#< CLIXML', 'connection_reset':b'Connection reset', 'transport_closed':b'closed', 'file_open_failed':b'failed to open file', 'file_read_failed':b'failed to read file', 'sharing_violation_named':b'sharing violation', 'file_busy':b'file is in use', 'permission_denied':b'Permission denied', 'cannot_access':b'cannot access', 'io_error':b'I/O error'}
 with open('/private/tmp/tofa84-transport-observations.jsonl','a') as f:f.write(json.dumps({'at':time.time(),'operation':sys.argv[1:3] if sys.argv[1]=='file' else sys.argv[1:2],'returncode':r.returncode,'stdout_bytes':len(r.stdout),'stderr_bytes':len(r.stderr),'diagnostic_sha256':hashlib.sha256(b).hexdigest(),'categories':[k for k,v in patterns.items() if v.lower() in b.lower()]})+'\n')
if sys.argv[1:3]==['file','pull'] and r.stderr and not any(v in b for v in (b'The system cannot find the file specified.',b'The system cannot find the path specified.')):
 # Private diagnostic only: this command reads an owned synthetic result, never account files.
 import os
 fd=os.open('/private/tmp/tofa84-private-transfer-error.txt',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 with os.fdopen(fd,'ab') as f:f.write(r.stderr[:4096]+b'\n')
sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)
