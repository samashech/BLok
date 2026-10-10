"""Real offline Laya → backend → persisted notes, plus in-flight cancellation."""
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='hyprash-pipeline-') as data:
    env = dict(os.environ, HYPRASH_DATA=data)
    process = subprocess.Popen([str(ROOT/'.venv/bin/python'), '-m', 'hyprash.backend'],
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    events = queue.Queue()
    def reader():
        for line in process.stdout:
            events.put(json.loads(line))
    threading.Thread(target=reader, daemon=True).start()
    def send(command, **args):
        process.stdin.write(json.dumps(dict(command=command, **args))+'\n')
        process.stdin.flush()
    def wait(predicate, timeout=30):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            event = events.get(timeout=max(.01,deadline-time.monotonic()))
            if event.get('error'): raise AssertionError(event)
            if predicate(event): return event
        raise AssertionError('Timed out waiting for event')
    try:
        wait(lambda e: e.get('type')=='engine' and 'offline' in e.get('message',''))
        send('text',text='open hyprash notes and create a note titled hello')
        note=wait(lambda e: e.get('type')=='note' and e.get('title')=='hello')
        wait(lambda e: e.get('type')=='activity' and e.get('state')=='idle')
        send('text',text='write this is a local note')
        wait(lambda e: e.get('type')=='note' and e.get('body')=='this is a local note')
        wait(lambda e: e.get('type')=='activity' and e.get('state')=='idle')
        saved=json.loads((Path(data)/'notes'/(note['id']+'.json')).read_text())
        assert saved['body']=='this is a local note',saved
        print('PASS: real offline model decisions create and update a persisted note',flush=True)
        send('text',text='create a note titled cancelled')
        send('stop')
        wait(lambda e: e.get('message')=='Microphone off')
        time.sleep(.7)
        while not events.empty():
            event=events.get_nowait()
            assert event.get('type') not in ('note','decision'),event
        assert not any(json.loads(p.read_text())['title']=='cancelled' for p in Path(data).glob('notes/*.json'))
        print('PASS: stopping discards an in-flight decision without writing its note',flush=True)
    finally:
        process.stdin.close()
        process.wait(timeout=5)
