"""Run typed commands through the live UI, offline Laya and action worker."""
import json,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def call(*args):return subprocess.check_output([str(ROOT/'hyprash.sh'),*args],text=True)

def command(text,expected):
    call('text',text)
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        status=json.loads(call('status'))
        if expected in status.get('action',''):
            print('PASS',text,'→',status['action'],flush=True)
            return status
        if status.get('state')=='error':raise AssertionError(status)
        time.sleep(.2)
    raise AssertionError(status)
try:
    command('open notes','Opened Hyprash Notes')
    command('click the note title','Focused note title')
    command('click Close','Closed Notes')
    command('open camera','Opened camera')
    command('click Picture Mode','Activated Picture Mode')
    command('click Close','Activated Close')
    command('open youtube and search for games','Searched youtube for games')
    command('click the search bar','Focused Search')
finally:call('hide')
