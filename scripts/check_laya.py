"""Run real, offline Laya inference. No desktop actions are executed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.decision import LayaDecision
agent=LayaDecision()
agent.load()
cases=[
 ('open browser',('open','browser')),
 ('open hyprash notes',('open','hyprash_notes')),
 ('open hyprash camera',('open','hyprash_camera')),
 ('Go to the address bar.',('address','')),
 ('Type weather in Delhi.',('browser_type','weather in delhi')),
 ('Press enter.',('browser_key','enter')),
 ('New tab.',('web_task','{"action": "new_tab"}')),
 ('Go back.',('browser_key','back')),
 ('Look up rock and roll.',('url','https://www.google.com/search?q=rock+and+roll')),
 ('Can you bring up my terminal?',('open','terminal')),
 ('open notes',('open','notes')),
 ('create a note titled hello',('new_note','hello')),
 ('make the title say hello',('title','hello')),
 ('write this is a local note',('write','this is a local note')),
 ('search for robin williams',('url','https://www.google.com/search?q=robin+williams')),
 ('open x dot com',('url','https://x.com')),
 ('open camera',('open','camera')),
 ('take a picture of me',('photo','')),
 ('switch to workspace three',('workspace','3')),
 ('stop listening',('stop','')),
 ("don't open browser",None),
 ('hello how are you',None),
 ('delete all my files',None),
]
from hyprash.commands import parse
for phrase in ['create a note saying hello in obsidian','play a justin bieber song','play a song by adele','open a new tab','search for bbs in youtube and play the first video','search for bbs in youtube and play the second video','open github and go to my repositories and find clickyAI and open it']:
    action=parse(phrase)[0]
    cases.append((phrase,(action.kind,action.value)))
failed=[]
for text,expected in cases:
    d=agent.decide(text)
    actual=(d.action.kind,d.action.value) if d.action else None
    print(('PASS' if expected==actual else 'FAIL'),repr(text),actual,d.intent,d.probability,str(d.elapsed_ms)+'ms',flush=True)
    if expected!=actual: failed.append(text)
if failed: raise SystemExit(f'{len(failed)} inference cases failed')
