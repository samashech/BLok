#!/usr/bin/env python3
"""Install reversible user integration without modifying packaged Omarchy files."""
from pathlib import Path
import datetime
import hashlib
import base64
import json
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BEGIN = '-- BEGIN BLOK\n'
END = '-- END BLOK\n'
bindings = Path.home()/'.config/hypr/bindings.lua'
desktop = Path.home()/'.local/share/applications/blok.desktop'

# Installs made before the rename used these names; they are migrated, never duplicated.
LEGACY_NAME = 'Hyprash'
LEGACY_BLOCKS = [('-- BEGIN '+LEGACY_NAME.upper()+'\n', '-- END '+LEGACY_NAME.upper()+'\n')]
LEGACY_DESKTOP = Path.home()/'.local/share/applications'/(LEGACY_NAME.lower()+'.desktop')
LEGACY_HOST = 'io.'+LEGACY_NAME.lower()+'.browser.json'

def remove_block(text):
    for begin, end in [(BEGIN, END)] + LEGACY_BLOCKS:
        if begin in text and end in text:
            start=text.index(begin)
            stop=text.index(end,start)+len(end)
            text=text[:start]+text[stop:]
    return text

def main():
    uninstall = '--uninstall' in sys.argv
    # --launcher PATH: what the keybinding and app entry run (a wrapper for packaged installs).
    launcher = Path(sys.argv[sys.argv.index('--launcher')+1]) if '--launcher' in sys.argv else ROOT/'blok.sh'
    original=bindings.read_text()
    if not uninstall:
        current=json.loads(subprocess.check_output(['hyprctl','-j','binds']))
        conflicts=[b for b in current if b['key'].lower() in ('period','.') and b['modmask'] in (0,4) and not b.get('description','').startswith(('BLoK', LEGACY_NAME))]
        if conflicts: raise SystemExit('Ctrl+. or period-release is already bound; installation stopped.')
    updated=remove_block(original)
    if not uninstall:
        command=shlex.quote(str(launcher))
        updated=updated.rstrip()+'\n\n'+BEGIN
        updated+='o.bind("CTRL + period", "BLoK hold to speak", '+json.dumps(command+' ptt-start')+')\n'
        updated+='o.bind("CTRL + period", "BLoK release to execute", '+json.dumps(command+' ptt-finish')+', { release = true, ignore_mods = true, non_consuming = true })\n'+END
    backup=bindings.with_name('bindings.lua.blok-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.write_text(original)
    bindings.write_text(updated)
    subprocess.run(['hyprctl','reload'],check=True)
    errors=subprocess.check_output(['hyprctl','configerrors'],text=True).strip()
    if errors and errors != 'ok':
        bindings.write_text(original)
        subprocess.run(['hyprctl','reload'],check=True)
        raise SystemExit('Config validation failed; restored original bindings.\n'+errors)
    LEGACY_DESKTOP.unlink(missing_ok=True)
    for profile in ['Brave-Origin','Brave-Browser']:
        (Path.home()/'.config/BraveSoftware'/profile/'NativeMessagingHosts'/LEGACY_HOST).unlink(missing_ok=True)
    if uninstall:
        desktop.unlink(missing_ok=True)
        for profile in ['Brave-Origin','Brave-Browser']:
            host=Path.home()/'.config/BraveSoftware'/profile/'NativeMessagingHosts/io.blok.browser.json'
            if host.exists() and json.loads(host.read_text()).get('path')==str(ROOT/'scripts/browser_host.py'):
                host.unlink()
        print('Removed BLoK keybinding and launcher. Project and notes preserved.')
    else:
        desktop.parent.mkdir(parents=True,exist_ok=True)
        executable=str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
        desktop.write_text('[Desktop Entry]\nType=Application\nName=BLoK\nComment=Offline voice assistant for Hyprland\nExec="'+executable+'" show\nIcon=audio-input-microphone\nTerminal=false\nCategories=Utility;\n')
        manifest=json.loads((ROOT/'browser-extension/manifest.json').read_text())
        digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        extension_id=''.join(chr(ord('a')+int(c,16)) for c in digest)
        host={'name':'io.blok.browser','description':'Local BLoK browser control','path':str(ROOT/'scripts/browser_host.py'),'type':'stdio','allowed_origins':['chrome-extension://'+extension_id+'/']}
        for profile in ['Brave-Origin','Brave-Browser']:
            directory=Path.home()/'.config/BraveSoftware'/profile/'NativeMessagingHosts'
            directory.mkdir(parents=True,exist_ok=True)
            (directory/'io.blok.browser.json').write_text(json.dumps(host,indent=2)+'\n')
        print('Installed Ctrl+. hold/release and local browser host. Backup: '+str(backup))
        print('Load unpacked extension from '+str(ROOT/'browser-extension'))

if __name__=='__main__': main()
