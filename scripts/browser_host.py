#!/usr/bin/python
"""Chrome native messaging ↔ owner-only Unix socket. No HTTP listener or page endpoint."""
import fcntl
import json
import os
from pathlib import Path
import queue
import socket
import struct
import sys
import threading
import uuid

runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
path=runtime/'hyprash-browser.sock'
lock=open(runtime/'hyprash-browser.lock','w')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit(0)
path.unlink(missing_ok=True)
server=socket.socket(socket.AF_UNIX)
server.bind(str(path));os.chmod(path,0o600);server.listen(8)
pending={};write_lock=threading.Lock()
def read_exact(n):
    data=b''
    while len(data)<n:
        chunk=sys.stdin.buffer.read(n-len(data))
        if not chunk: raise EOFError
        data+=chunk
    return data
def reader():
    try:
        while True:
            size=struct.unpack('=I',read_exact(4))[0]
            if size>1024*1024: raise ValueError('Message too large')
            msg=json.loads(read_exact(size));q=pending.get(msg.get('id'))
            if q:q.put(msg)
    except (EOFError,ValueError):
        path.unlink(missing_ok=True);os._exit(0)
def client(conn):
    key=uuid.uuid4().hex
    try:
        conn.settimeout(50)
        request=json.loads(conn.makefile('rb').readline(16384))
        if request.get('action') not in {'ping','cancel','inspect','search','navigate','result','play','click','fill','new_tab','sequence','github_repo'}:raise ValueError('Unsupported action')
        request['id']=key;pending[key]=queue.Queue()
        payload=json.dumps(request).encode()
        with write_lock:
            sys.stdout.buffer.write(struct.pack('=I',len(payload))+payload);sys.stdout.buffer.flush()
        response=pending[key].get(timeout=45)
        conn.sendall(json.dumps(response).encode()+b'\n')
    except Exception as error:
        try:conn.sendall(json.dumps({'error':str(error)}).encode()+b'\n')
        except OSError:pass
    finally:
        pending.pop(key,None);conn.close()
threading.Thread(target=reader,daemon=True).start()
while True:
    conn,_=server.accept();threading.Thread(target=client,args=(conn,),daemon=True).start()
