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
BEGIN = '-- BEGIN HYPRASH\n'
END = '-- END HYPRASH\n'
bindings = Path.home()/'.config/hypr/bindings.lua'
desktop = Path.home()/'.local/share/applications/hyprash.desktop'

def remove_block(text):
    if BEGIN in text and END in text:
        start=text.index(BEGIN)
        end=text.index(END,start)+len(END)
        return text[:start]+text[end:]
    return text

def main():
    uninstall = '--uninstall' in sys.argv
    original=bindings.read_text()
    if not uninstall:
        current=json.loads(subprocess.check_output(['hyprctl','-j','binds']))
        conflicts=[b for b in current if b['key'].lower() in ('period','.') and b['modmask'] in (0,4) and not b.get('description','').startswith('Hyprash')]
        if conflicts: raise SystemExit('Ctrl+. or period-release is already bound; installation stopped.')
    updated=remove_block(original)
    if not uninstall:
        command=shlex.quote(str(ROOT/'hyprash.sh'))
        updated=updated.rstrip()+'\n\n'+BEGIN
        updated+='o.bind("CTRL + period", "Hyprash hold to speak", '+json.dumps(command+' ptt-start')+')\n'
        updated+='o.bind("CTRL + period", "Hyprash release to execute", '+json.dumps(command+' ptt-finish')+', { release = true, ignore_mods = true })\n'+END
    backup=bindings.with_name('bindings.lua.hyprash-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.write_text(original)
    bindings.write_text(updated)
    subprocess.run(['hyprctl','reload'],check=True)
    errors=subprocess.check_output(['hyprctl','configerrors'],text=True).strip()
    if errors and errors != 'ok':
        bindings.write_text(original)
        subprocess.run(['hyprctl','reload'],check=True)
        raise SystemExit('Config validation failed; restored original bindings.\n'+errors)
    if uninstall:
        desktop.unlink(missing_ok=True)
        print('Removed Hyprash keybinding and launcher. Project and notes preserved.')
    else:
        desktop.parent.mkdir(parents=True,exist_ok=True)
        executable=str(ROOT/'hyprash.sh').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
        desktop.write_text('[Desktop Entry]\nType=Application\nName=Hyprash\nComment=Local voice assistant for Hyprland\nExec="'+executable+'" show\nIcon=audio-input-microphone\nTerminal=false\nCategories=Utility;\n')
        manifest=json.loads((ROOT/'browser-extension/manifest.json').read_text())
        digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        extension_id=''.join(chr(ord('a')+int(c,16)) for c in digest)
        host={'name':'io.hyprash.browser','description':'Local Hyprash browser control','path':str(ROOT/'scripts/browser_host.py'),'type':'stdio','allowed_origins':['chrome-extension://'+extension_id+'/']}
        for profile in ['Brave-Origin','Brave-Browser']:
            directory=Path.home()/'.config/BraveSoftware'/profile/'NativeMessagingHosts'
            directory.mkdir(parents=True,exist_ok=True)
            (directory/'io.hyprash.browser.json').write_text(json.dumps(host,indent=2)+'\n')
        print('Installed Ctrl+. hold/release and local browser host. Backup: '+str(backup))
        print('Load unpacked extension from '+str(ROOT/'browser-extension'))

if __name__=='__main__': main()
