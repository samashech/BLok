"""Create and register the explicitly requested local Hyprash vault, preserving others."""
import datetime,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.desktop import start_app
ROOT=Path(__file__).resolve().parent.parent
config=Path.home()/'.config/obsidian/obsidian.json'
vault=ROOT/'data/Obsidian'
(vault/'.obsidian').mkdir(parents=True,exist_ok=True)
original=config.read_text() if config.exists() else '{}'
settings=json.loads(original)
key=next((k for k,v in settings.get('vaults',{}).items() if v['path']==str(vault)),hashlib.sha256(str(vault).encode()).hexdigest()[:16])
if key not in settings.get('vaults',{}):
    if config.exists():config.with_name('obsidian.json.hyprash-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')).write_text(original)
    settings.setdefault('vaults',{})[key]={'path':str(vault),'ts':int(datetime.datetime.now().timestamp()*1000),'open':False}
    config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text(json.dumps(settings))
(ROOT/'data/obsidian-vault.json').write_text(json.dumps({'id':key,'path':str(vault)}))
start_app(['xdg-open','obsidian://open?vault='+key])
print('Created and opened local Hyprash vault:',vault)
