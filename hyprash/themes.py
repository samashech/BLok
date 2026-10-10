"""App themes; Omarchy palette is read-only and follows desktop changes."""
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent.parent
THEMES = ('omarchy', 'liquid')

def desktop_palette():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    for current in (state/'omarchy/current', config/'omarchy/current'):
        try:
            palette=tomllib.loads((current/'theme/colors.toml').read_text())
            name=(current/'theme.name').read_text().strip() if (current/'theme.name').exists() else 'Desktop'
            return palette,name
        except (OSError,ValueError):
            continue
    return {},'Fallback'

class ThemeStore:
    def __init__(self, data):
        self.path=Path(data)/'settings.json'
        self.selected='omarchy'
        try:
            value=json.loads(self.path.read_text()).get('theme')
            if value in THEMES: self.selected=value
        except (OSError,ValueError,AttributeError): pass
        self.last=None

    def select(self,name):
        if name not in THEMES: raise ValueError('Choose the omarchy or liquid theme')
        settings={}
        try:
            settings=json.loads(self.path.read_text())
            if not isinstance(settings,dict): settings={}
        except (OSError,ValueError): pass
        settings['theme']=name
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(settings,indent=2)+'\n')
        temp.replace(self.path)
        self.selected=name

    def current(self):
        theme=json.loads((ROOT/'themes'/(self.selected+'.json')).read_text())
        if theme['followDesktop']:
            palette,name=desktop_palette()
            theme['desktopName']=name
            mapping={
                'background':'background','backgroundTop':'background','backgroundBottom':'background',
                'foreground':'foreground','muted':'dark_foreground','accent':'accent',
                'border':'accent','surface':'lighter_background','hover':'selection',
                'success':'green','error':'bright_red','orb':'bright_foreground',
            }
            for key,source in mapping.items():
                color=palette.get(source)
                if isinstance(color,str) and re.fullmatch(r'#[a-fA-F0-9]{6}',color): theme[key]=color
            if palette.get('mode') in ('light','dark'): theme['mode']=palette['mode']
        return theme

    def changed(self):
        value=self.current()
        if value==self.last: return None
        self.last=value
        return value
