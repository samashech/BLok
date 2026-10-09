"""Run real, offline Laya inference. No desktop actions are executed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.decision import LayaDecision
agent=LayaDecision()
agent.load()
cases=[
 ('open browser',('open','browser')),
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
failed=[]
for text,expected in cases:
    d=agent.decide(text)
    actual=(d.action.kind,d.action.value) if d.action else None
    print(('PASS' if expected==actual else 'FAIL'),repr(text),actual,d.intent,d.probability,str(d.elapsed_ms)+'ms',flush=True)
    if expected!=actual: failed.append(text)
if failed: raise SystemExit(f'{len(failed)} inference cases failed')
