"""Check the installed Voxtype bridge and browser keys on the real desktop."""
import json
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from hyprash.speech import VoxtypeSession
from hyprash import browser

voice=VoxtypeSession()
try:
    voice.start()
    assert voice.state()=='recording'
    assert voice.path.parent.stat().st_mode & 0o077 == 0
    print('PASS: existing Voxtype recording; model',voice.model,flush=True)
    voice.cancel()
    for _ in range(30):
        if voice.state()=='idle': break
        time.sleep(.1)
    assert voice.state()=='idle',voice.state()
    print('PASS: cancellation returns the existing daemon to idle',flush=True)
finally:
    voice.cancel()
    voice.close()
if '--browser' in sys.argv:
    browser.control('browser_key','new tab')
    browser.control('browser_type','https://example.com')
    browser.control('browser_key','enter')
    time.sleep(2)
    window=json.loads(browser.run(['hyprctl','-j','activewindow']))
    assert browser.BROWSERS.fullmatch(window['class']),window['class']
    assert 'Example Domain' in window['title'],window['title']
    print('PASS: browser focused; address typed; Enter loaded Example Domain',flush=True)

if '--finish' in sys.argv:
    voice=VoxtypeSession()
    try:
        voice.start()
        time.sleep(.7)
        voice.finish()
        for _ in range(300):
            if voice.state()=='idle': break
            time.sleep(.1)
        assert voice.state()=='idle',voice.state()
        voice.owned=False
        print('PASS: finish transcribes and returns to idle; output file present:',voice.path.exists(),flush=True)
    finally:
        voice.close()
