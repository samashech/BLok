"""Inspect installed Notes/Camera controls without editing notes or taking photos."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash import desktop
for app in sys.argv[1:] or ['notes','camera']:
    print('LAUNCH',app,desktop.launch(app),flush=True)
    try:print('CONTROLS',desktop.control({'action':'inspect'}),flush=True)
    except Exception as e:print('ERROR',str(e),flush=True)
