"""App themes; Omarchy palette is read-only and follows desktop changes."""
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'blok'
# Theme packs are folders (<name>/theme.json plus any images it names). Your own
# packs in ~/.config/blok/themes/ are added to the cycle and override shipped ones.
SEARCH = (ROOT/'themes', CONFIG/'themes')
# Cycle order for the ▦ button; other packs follow alphabetically.
ORDER = ('omarchy', 'liquid', 'halloween', 'diwali', 'minecraft')

def packs():
    found = {}
    for folder in SEARCH:
        if not folder.is_dir():
            continue
        for path in folder.glob('*/theme.json'):
            found[path.parent.name] = path
        for path in folder.glob('*.json'):   # single-file themes still work
            found.setdefault(path.stem, path)
    return found

def available():
    found = set(packs())
    return tuple(t for t in ORDER if t in found) + tuple(sorted(found - set(ORDER)))

THEMES = available()

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
            if value in available(): self.selected=value
        except (OSError,ValueError,AttributeError): pass
        self.last=None

    def select(self,name):
        themes=available()
        if name == 'next':
            name=themes[(themes.index(self.selected)+1)%len(themes)] if self.selected in themes else themes[0]
        if name not in themes: raise ValueError('Choose one of these themes: '+', '.join(themes))
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
        path=packs().get(self.selected) or packs()['omarchy']
        theme=json.loads(path.read_text())
        theme.setdefault('id', path.parent.name if path.name == 'theme.json' else path.stem)
        theme.setdefault('name', theme['id'].title())
        theme.setdefault('followDesktop', False)
        # Image fields (badge, micIcon) are resolved against the pack's own folder.
        theme['assetBase']=path.parent.resolve().as_uri()+'/'
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
