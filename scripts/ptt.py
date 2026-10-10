#!/usr/bin/env python3
"""Release-safe push-to-talk, including release while Quickshell starts."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parent.parent
runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))
held=runtime/'hyprash-key-held'
lock=open(runtime/'hyprash-ptt.lock','w')
def ipc(method):
    return subprocess.run(['quickshell','ipc','-p',str(root/'ui'),'call','hyprash',method],capture_output=True,timeout=8)
if sys.argv[1]=='start':
    with lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if held.exists():raise SystemExit(0)
        held.touch(mode=0o600)
    subprocess.run([str(root/'hyprash.sh'),'show'],check=True,timeout=10)
    with open(runtime/'hyprash-ptt.lock','w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        if held.exists():ipc('beginRecording')
else:
    with lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not held.exists():raise SystemExit(0)
        held.unlink()
        ipc('finishRecording')
