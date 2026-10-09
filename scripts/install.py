#!/usr/bin/env python3
"""Install reversible user integration without modifying packaged Omarchy files."""
from pathlib import Path
import datetime
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
        conflicts=[b for b in current if b['key'].upper()=='J' and b['modmask']==65 and b.get('description')!='Hyprash voice assistant']
        if conflicts: raise SystemExit('Super+Shift+J is already bound; installation stopped.')
    updated=remove_block(original)
    if not uninstall:
        command=shlex.quote(str(ROOT/'hyprash.sh'))+' toggle'
        updated=updated.rstrip()+'\n\n'+BEGIN+'o.bind("SUPER + SHIFT + J", "Hyprash voice assistant", '+json.dumps(command)+')\n'+END
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
        print('Installed Super+Shift+J and Hyprash launcher. Backup: '+str(backup))

if __name__=='__main__': main()
