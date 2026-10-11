from pathlib import Path
import sys,time,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.browser import focus,run,control
focus()
if '--fullscreen' in sys.argv:
    run(['wtype','-k','F11']);time.sleep(.5)
if '--navigate' in sys.argv:
    control('browser_type','chrome://extensions');control('browser_key','enter');time.sleep(.8)
if '--dismiss-picker' in sys.argv:run(['wtype','-k','Escape'])
if '--select-folder' in sys.argv:run(['wtype','-M','alt','-k','s','-m','alt'])
if '--tab' in sys.argv:run(['wtype','-k','Tab'])
if '--space' in sys.argv:run(['wtype','-k','space'])
if '--open-picker' in sys.argv:
    run(['wtype','-k','Tab','-k','Return'])
    time.sleep(1)
if '--load' in sys.argv:
    run(['wtype','-k','Tab','-k','Return'])
    time.sleep(.4)
    run(['wtype','-M','ctrl','-k','l','-m','ctrl','--',str(Path(__file__).resolve().parent.parent/'browser-extension')])
    run(['wtype','-k','Return'])
    time.sleep(.5)
    run(['wtype','-k','Return'])
time.sleep(.5)
subprocess.run(['grim','/tmp/hyprash-extensions.png'],check=True)
