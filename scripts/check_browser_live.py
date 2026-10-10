"""Explicit live browser smoke checks; uses existing signed-in Brave tabs."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.browser import request
if len(sys.argv)>1 and sys.argv[1]=='spotify':
    print(request({'action':'play','site':'spotify','query':"god's plan"}),flush=True)
else:
    for site in ['google','youtube']:
        print(request({'action':'search','site':site,'query':'games'}),flush=True)
        time.sleep(2)
        before=request({'action':'inspect'})
        print('RESULTS',before['url'],before['title'],flush=True)
        print(request({'action':'result','index':1}),flush=True)
        after=request({'action':'inspect'})
        print('OPENED',after['url'],after['title'],flush=True)
