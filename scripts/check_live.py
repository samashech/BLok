"""Check real Voxtype recording and stop cleanup; no transcript is persisted."""
from collections import deque
import json
import os
from pathlib import Path
import select
import subprocess
import time

root=Path(__file__).resolve().parent.parent
process=subprocess.Popen([str(root/'.venv/bin/python'),'-m','hyprash.backend'],cwd=root,
                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
def send(command):
    process.stdin.write(json.dumps({'command':command})+'\n'); process.stdin.flush()
buffer=b''
pending=deque()
def wait_for(predicate,timeout=30):
    global buffer
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        while pending:
            event=pending.popleft()
            if event.get('state')=='error': raise RuntimeError(event['message'])
            if predicate(event): return event
        ready,_,_=select.select([process.stdout],[],[],0.5)
        if not ready: continue
        chunk=os.read(process.stdout.fileno(),65536)
        if not chunk: raise AssertionError('Backend exited before expected event')
        buffer+=chunk
        while b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1)
            pending.append(json.loads(line))
    raise AssertionError('Timed out waiting for backend event')

try:
    wait_for(lambda e:e.get('state')=='ready')
    wait_for(lambda e:e.get('type')=='engine' and 'offline' in e.get('message',''))
    send('listen')
    wait_for(lambda e:e.get('state')=='listening')
    send('stop')
    wait_for(lambda e:e.get('message')=='Microphone off')
    time.sleep(.3)
    status=json.loads(subprocess.check_output(['voxtype','status','--format','json']))
    assert status['class']=='idle',status
    print('PASS: existing Voxtype records; stop cancels and returns daemon to idle')
finally:
    process.stdin.close()
    process.wait(timeout=5)
