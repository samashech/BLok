"""Opt-in checks for the reported commands, using the signed-in browser."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.commands import parse
from hyprash.browser import request
phrases={
 'tab':'open a new tab',
 'artist':'play a justin bieber song',
 'video':'search for bbs in youtube and play the second video',
 'github':'open github and go to my repositories and find clickyAI and open it',
}
for case in sys.argv[1:] or phrases:
    if case=='inspect':
        result=request({'action':'inspect'});print(result,flush=True);continue
    phrase=phrases[case]
    task=json.loads(parse(phrase)[0].value)
    try:print(case,request(task),flush=True)
    except Exception as e:print('FAIL',case,str(e),flush=True)
