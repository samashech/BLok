"""Check real PipeWire capture and stop cleanup; no transcript is persisted."""
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
def wait_for(predicate,timeout=20):
    # os.read avoids TextIO's buffered readline/select mismatch.
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        ready,_,_=select.select([process.stdout],[],[],0.5)
        if not ready: continue
        data=os.read(process.stdout.fileno(),65536).decode()
        for line in data.splitlines():
            event=json.loads(line)
            if event.get('state')=='error': raise RuntimeError(event['message'])
            if predicate(event): return event
    raise AssertionError('Timed out waiting for backend event')
try:
    wait_for(lambda e:e.get('state')=='ready')
    send('listen')
    wait_for(lambda e:e.get('state')=='listening')
    wait_for(lambda e:e.get('type')=='level')
    send('stop')
    wait_for(lambda e:e.get('message')=='Microphone off')
    children=subprocess.run(['pgrep','-P',str(process.pid),'pw-record'],capture_output=True,text=True)
    assert children.returncode == 1, 'Recorder survived stop'
    print('PASS: real PipeWire samples received; stop terminates microphone capture')
finally:
    process.stdin.close()
    process.wait(timeout=5)
