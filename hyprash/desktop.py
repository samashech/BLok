"""Installed desktop app launching, named accessible controls, and Obsidian notes."""
from functools import lru_cache
import configparser
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode, quote
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

def start_app(args):
    # Some URI handlers exec the GUI itself. Its lifetime is not the launch result.
    import threading
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        code=process.wait(timeout=.25)
        if code:raise RuntimeError('App launcher failed with exit code '+str(code))
    except subprocess.TimeoutExpired:
        threading.Thread(target=process.wait,daemon=True).start()


def launch(name):
    if name=='notes' and not obsidian_vault():return False
    apps=catalog()
    aliases={'notes':'obsidian','camera':'camera','snapshot':'camera'}
    key=aliases.get(name,name)
    app=apps.get(key)
    if not app:return False
    start_app(['gtk-launch',app])
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
    preference=Path(os.environ.get('HYPRASH_DATA',ROOT/'data'))/'obsidian-vault.json'
    try:
        preferred=json.loads(preference.read_text())
        if vaults.get(preferred['id'],{}).get('path')==preferred['path'] and Path(preferred['path']).is_dir():
            return preferred['id'],Path(preferred['path'])
    except (OSError,ValueError,KeyError):pass
    opened=[(key,Path(v['path'])) for key,v in vaults.items() if v.get('open')]
    if len(opened)==1:return opened[0] if opened[0][1].is_dir() else None
    if len(vaults)==1:
        key,v=next(iter(vaults.items()));directory=Path(v['path']);return (key,directory) if directory.is_dir() else None
    return None

def new_obsidian_note(title,content='',append=False):
    vault=obsidian_vault()
    if not vault:raise RuntimeError('Select one vault in Obsidian first, or say “open Hyprash notes”.')
    if '/' in title or '\\' in title or title in ('.','..'):raise ValueError('Use a note title without path separators.')
    key,directory=vault
    existing=list(directory.rglob(title+'.md'))
    if not append and existing:
        raise RuntimeError('A note with that title already exists. Choose a new title.')
    if append and len(existing)!=1:
        raise RuntimeError('The named note is missing or ambiguous; create a unique named note first.')
    params={'vault':key,'name':title,'content':content}
    if append:params['append']='true'
    # The app chooses its configured note folder; never write arbitrary vault paths.
    start_app(['xdg-open','obsidian://new?'+urlencode(params,quote_via=quote)])
    for _ in range(30):
        matches=list(directory.rglob(title+'.md'))
        if len(matches)==1 and (not content or content in matches[0].read_text()):return title
        time.sleep(.1)
    raise RuntimeError('Obsidian did not confirm the saved note. Check its vault/dialog.')


def create_obsidian_note(content):
    """Use literal dictated content as the body, with a short unique title."""
    import re
    vault=obsidian_vault()
    if not vault:raise RuntimeError('Open a valid vault in Obsidian first.')
    base=re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ',content).strip(' .')[:70] or 'Voice note'
    title=base
    counter=2
    while list(vault[1].rglob(title+'.md')):
        title=base+' ('+str(counter)+')';counter+=1
    return new_obsidian_note(title,content)
