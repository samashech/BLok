"""Exercise the configured press/release path; cancel transcription before actions."""
import json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def call(*args):return subprocess.check_output([str(ROOT/'hyprash.sh'),*args],text=True)
try:
    call('ptt-start')
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        state=json.loads(subprocess.check_output(['voxtype','status','--format','json']))
        if state['class']=='recording':break
        time.sleep(.1)
    assert state['class']=='recording',state
    call('ptt-finish')
    call('hide')
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        state=json.loads(subprocess.check_output(['voxtype','status','--format','json']))
        if state['class']=='idle':break
        time.sleep(.1)
    assert state['class']=='idle',state
    assert not Path('/run/user/1000/hyprash-key-held').exists()
    print('PASS: press records; release finishes; cancellation leaves Voxtype idle and no held-key marker')
finally:call('hide')
