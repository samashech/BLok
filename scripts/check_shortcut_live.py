"""Check real Wayland key delivery in a disposable GTK entry; no user text is edited."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
if len(sys.argv)>1:
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk
    app=Gtk.Application(application_id='io.hyprash.ShortcutCheck')
    def activate(app):
        win=Gtk.ApplicationWindow(application=app,title='Hyprash shortcut check')
        entry=Gtk.Entry();entry.connect('changed',lambda e:Path(sys.argv[1]).write_text(e.get_text()))
        win.set_child(entry);win.set_default_size(320,100);win.present();entry.grab_focus()
    app.connect('activate',activate);app.run([sys.argv[0]])
else:
    with tempfile.TemporaryDirectory(prefix='hyprash-shortcut-') as directory:
        output=Path(directory)/'text';output.write_text('')
        app=subprocess.Popen(['/usr/bin/python',__file__,str(output)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                clients=json.loads(subprocess.check_output(['hyprctl','-j','clients']))
                target=next((c for c in clients if c['title']=='Hyprash shortcut check'),None)
                if target:break
                time.sleep(.1)
            assert target,'Test entry did not open'
            subprocess.run(['hyprctl','dispatch','hl.dsp.focus({window="address:'+target['address']+'"})'],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['wtype','-k','period'],check=True)
            time.sleep(.2)
            assert output.read_text()=='.',repr(output.read_text())
            print('PASS: plain period reaches the focused app',flush=True)
            subprocess.run(['wtype','-M','ctrl','-P','period','-s','800','-m','ctrl','-p','period'],check=True)
            subprocess.run([str(ROOT/'hyprash.sh'),'hide'],check=True,stdout=subprocess.DEVNULL)
            time.sleep(.4)
            status=json.loads(subprocess.check_output(['voxtype','status','--format','json']))
            assert status['class']=='idle',status
            assert not Path(os.environ['XDG_RUNTIME_DIR'],'hyprash-key-held').exists()
            assert output.read_text()=='.',repr(output.read_text())
            print('PASS: Ctrl+. does not insert a dot; releasing Ctrl first still finishes; microphone idle',flush=True)
        finally:
            subprocess.run([str(ROOT/'hyprash.sh'),'hide'],stdout=subprocess.DEVNULL)
            app.terminate();app.wait(timeout=5)
