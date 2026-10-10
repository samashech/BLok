"""Capture the camera-origin reveal at six points, and check reverse completion."""
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parent.parent
OUT=Path('/tmp/hyprash-motion')
OUT.mkdir(exist_ok=True)
def call(command):
    return subprocess.check_output([str(ROOT/'hyprash.sh'),command],text=True)
monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors']))
monitor=next((m for m in monitors if m.get('focused')),monitors[0])
width=int(monitor['width']/monitor['scale'])
x=monitor['x']+(width-500)//2
y=monitor['y']
call('hide'); time.sleep(1.3)
print('Show result:',repr(call('show')),flush=True); start=time.monotonic()
print('After show:',call('status'),flush=True)
for i,at in enumerate([.10,.25,.40,.60,.85,1.25]):
    time.sleep(max(0,at-(time.monotonic()-start)))
    subprocess.run(['grim','-g',f'{x},{y} 500x250',str(OUT/f'{i:02}.png')],check=True)
    print('frame',i,round(time.monotonic()-start,3),call('status'),flush=True)
status=json.loads(call('status'))
assert status['reveal']==1,status
call('hide'); time.sleep(1.3)
status=json.loads(call('status'))
assert status['reveal']==0,status
assert status['message']=='Microphone off',status
# Reverse an unfinished transition in both directions.
call('show'); time.sleep(.3)
call('hide'); time.sleep(.2)
call('show'); time.sleep(1.3)
status=json.loads(call('status'))
assert status['reveal']==1,status
assert status['message']=='Microphone off',status
print('PASS: opening frames captured; closing and interrupted transitions complete; mic is off')
