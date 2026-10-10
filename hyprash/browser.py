"""Bounded browser controls for the installed Hyprland Lua dispatcher API."""
import json
import re
import subprocess
import time

BROWSERS = re.compile(r'^(?:brave(?:-browser|-origin)?|chromium|google-chrome(?:-stable)?|firefox|org\.mozilla\.firefox|zen(?:-browser)?)$', re.I)

def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:180] or result.stdout.strip()[:180] or f'{args[0]} failed')
    return result.stdout

def focus():
    clients = json.loads(run(['hyprctl', '-j', 'clients']))
    browsers = [c for c in clients if c.get('mapped') and BROWSERS.fullmatch(c.get('class', ''))]
    if not browsers:
        raise RuntimeError('Open your browser first, then repeat the address-bar command.')
    target = min(browsers, key=lambda c: c.get('focusHistoryID', 999))
    address = target['address']
    if not re.fullmatch(r'0x[0-9a-fA-F]+', address):
        raise RuntimeError('Invalid browser window identifier')
    response = run(['hyprctl', 'dispatch', f'hl.dsp.focus({{window="address:{address}"}})'])
    if 'ok' not in response.lower():
        raise RuntimeError('Could not focus the browser: ' + response[:150])
    for _ in range(20):
        if json.loads(run(['hyprctl', '-j', 'activewindow'])).get('address') == address:
            return
        time.sleep(.05)
    raise RuntimeError('Browser did not gain focus; no keys were sent')

def control(kind, value=''):
    focus()
    if kind == 'address':
        run(['wtype', '-M', 'ctrl', '-k', 'l', '-m', 'ctrl'])
    elif kind == 'browser_type':
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Address-bar text cannot contain control characters')
        run(['wtype', '-M', 'ctrl', '-k', 'l', '-m', 'ctrl', '-s', '80', '--', value])
    elif kind == 'browser_key':
        shortcuts = {'enter': ['-k', 'Return'], 'new tab': ['-M', 'ctrl', '-k', 't', '-m', 'ctrl'],
                     'back': ['-M', 'alt', '-k', 'Left', '-m', 'alt'],
                     'forward': ['-M', 'alt', '-k', 'Right', '-m', 'alt'], 'reload': ['-k', 'F5']}
        run(['wtype', *shortcuts[value]])
