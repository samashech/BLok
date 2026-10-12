from pathlib import Path
import sys,time,subprocess,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.browser import focus,run,control
def setup_focus():
    candidates=[c for c in json.loads(run(['hyprctl','-j','clients'])) if c.get('class')=='brave-origin' and c.get('title','').startswith('Extensions')]
    if candidates:
        c=min(candidates,key=lambda c:c.get('focusHistoryID',999))
        run(['hyprctl','dispatch','hl.dsp.focus({window="address:'+c['address']+'"})'])
    else:focus()
setup_focus()
if '--fullscreen' in sys.argv:
    run(['wtype','-k','F11']);time.sleep(.5)
if '--navigate' in sys.argv:
    control('browser_type','brave://extensions')
    control('browser_key','enter');time.sleep(1.5);setup_focus()
if '--click' in sys.argv:
    i=sys.argv.index('--click');x=int(sys.argv[i+1]);y=int(sys.argv[i+2])
    print(run(['hyprctl','dispatch',f'hl.dsp.cursor.move({{x={x},y={y}}})']))
    for state in ['down','up']:
        print(run(['hyprctl','dispatch',f'hl.dsp.send_key_state({{state="{state}",mods="",key="mouse:272"}})']))
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
