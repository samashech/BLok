"""Installed desktop app launching, named accessible controls, and Obsidian notes."""
from functools import lru_cache
import configparser
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode
from hyprash import browser
ROOT=Path(__file__).resolve().parent.parent

@lru_cache(maxsize=1)
def catalog():
    found={}
    for directory in [Path('/usr/share/applications'),Path.home()/'.local/share/applications']:
        for path in directory.glob('*.desktop'):
            config=configparser.ConfigParser(interpolation=None,strict=False)
            try:
                config.read(path);entry=config['Desktop Entry']
                if entry.get('Hidden')=='true' or entry.get('NoDisplay')=='true':continue
                found[entry.get('Name',path.stem).lower()]=path.stem
            except (configparser.Error,KeyError):continue
    return found

def launch(name):
    apps=catalog()
    aliases={'notes':'obsidian','camera':'camera','snapshot':'camera'}
    key=aliases.get(name,name)
    app=apps.get(key)
    if not app:return False
    browser.run(['gtk-launch',app])
    classes={'obsidian':'obsidian','camera':'org.gnome.snapshot'}
    if key in classes:
        for _ in range(40):
            clients=json.loads(browser.run(['hyprctl','-j','clients']))
            matching=[c for c in clients if classes[key] in c.get('class','').lower() and c.get('mapped')]
            if matching:
                browser.run(['hyprctl','dispatch','hl.dsp.focus({window="address:'+matching[0]['address']+'"})'])
                return True
            time.sleep(.1)
        raise RuntimeError('The app did not show a window. Check its startup dialog.')
    return True

def control(request):
    active=json.loads(browser.run(['hyprctl','-j','activewindow']))
    if browser.BROWSERS.fullmatch(active.get('class','')):
        return browser.request(request)
    result=subprocess.run(['/usr/bin/python',str(ROOT/'scripts/accessibility.py')],
        input=json.dumps({**request,'pid':active.get('pid',0)}),capture_output=True,text=True,timeout=15)
    try: answer=json.loads(result.stdout)
    except ValueError: raise RuntimeError('Desktop accessibility is unavailable for this app.')
    if answer.get('error'):raise RuntimeError(answer['error'])
    return answer

def obsidian_vault():
    path=Path.home()/'.config/obsidian/obsidian.json'
    try: vaults=json.loads(path.read_text()).get('vaults',{})
    except (OSError,ValueError):return None
    opened=[(key,Path(v['path'])) for key,v in vaults.items() if v.get('open')]
    if len(opened)==1:return opened[0]
    if len(vaults)==1:
        key,v=next(iter(vaults.items()));return key,Path(v['path'])
    return None

def new_obsidian_note(title,content='',append=False):
    vault=obsidian_vault()
    if not vault:raise RuntimeError('Select one vault in Obsidian first, or say “open Hyprash notes”.')
    if '/' in title or '\\' in title or title in ('.','..'):raise ValueError('Use a note title without path separators.')
    key,directory=vault
    params={'vault':key,'name':title,'content':content}
    if append:params['append']='true'
    # The app chooses its configured note folder; never write arbitrary vault paths.
    browser.run(['xdg-open','obsidian://new?'+urlencode(params)])
    for _ in range(30):
        matches=list(directory.rglob(title+'.md'))
        if len(matches)==1 and (not content or content in matches[0].read_text()):return title
        time.sleep(.1)
    raise RuntimeError('Obsidian did not confirm the saved note. Check its vault/dialog.')
