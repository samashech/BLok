"""Check clicking by reading the screen: `./blok.sh click-test`.

Opens a small test window, clicks its buttons with the real pointer and ydotool, and
reports which buttons felt it. Keep your hands off the mouse and keyboard while it runs.
Nothing outside the test window is clicked: it stops if focus goes anywhere else.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blok import clicker, screen
from blok.backend import Backend

WINDOW = """import QtQuick
import Quickshell
FloatingWindow {
    implicitWidth: 600; implicitHeight: 340
    title: "blok-click-test"
    color: "white"
    Repeater {
        model: [{t: "Zebra", x: 20, y: 20}, {t: "Walrus", x: 310, y: 20}, {t: "Twice", x: 20, y: 180}, {t: "Twice", x: 310, y: 180}]
        Rectangle {
            required property var modelData
            id: button
            property bool done: false
            x: modelData.x; y: modelData.y; width: 270; height: 80; color: done ? "#88cc88" : "#eeeeee"; border.color: "black"
            Text { anchors.centerIn: parent; text: modelData.t; font.pixelSize: 34; color: "black" }
            MouseArea { anchors.fill: parent; onClicked: { button.done = true; console.log("PRESSED " + modelData.t) } }
        }
    }
}
"""


def hypr(*args):
    return subprocess.run(['hyprctl', *args], capture_output=True, text=True).stdout


def clients():
    return json.loads(hypr('-j', 'clients'))


def main():
    if not clicker.available():
        print(clicker.INSTALL_HINT)
        return 1
    print('Hands off the mouse and keyboard for about 15 seconds. Starting in 5…')
    time.sleep(5)
    previous = json.loads(hypr('-j', 'activewindow')).get('address')
    pointer = hypr('cursorpos').strip()
    failures = 0
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / 'shell.qml').write_text(WINDOW)
        log = Path(folder) / 'log'
        with log.open('w') as output:
            window = subprocess.Popen(['quickshell', '-p', str(Path(folder) / 'shell.qml')], stdout=output, stderr=subprocess.STDOUT)
        pressed = lambda: [line.split('PRESSED ')[1].strip() for line in log.read_text().splitlines() if 'PRESSED' in line]
        try:
            address = None
            for _ in range(50):
                time.sleep(0.1)
                address = next((c['address'] for c in clients() if c.get('title') == 'blok-click-test'), None)
                if address:
                    break
            if not address:
                print('The test window did not open.')
                return 1
            for _ in range(8):
                hypr('dispatch', f'hl.dsp.focus({{window="address:{address}"}})')
                time.sleep(0.2)
                found = next(c for c in clients() if c['address'] == address)
                hypr('dispatch', f'hl.dsp.cursor.move({{ x = {found["at"][0] + found["size"][0] // 2}, y = {found["at"][1] + found["size"][1] - 20} }})')
                time.sleep(0.4)
                if screen.active_window().get('address') == address:
                    break
            else:
                print('Something kept taking focus from the test window, so nothing was clicked. Try again with your hands off the mouse.')
                return 1
            time.sleep(0.6)
            backend = Backend()
            backend.emit, backend.hide_overlay = Mock(), Mock()

            def step(label, expected, says):
                nonlocal failures
                before = len(pressed())
                try:
                    message = backend.click_by_sight(label)
                except RuntimeError as error:
                    message = f'refused: {error}'
                time.sleep(0.4)
                got = pressed()[before:]
                good = got == expected and says in message
                failures += not good
                print(f'{"PASS" if good else "FAIL"}  {label}: {message} (the window felt: {got or "nothing"})')

            step('Zebra', ['Zebra'], 'the window changed')      # the button turns green, and BLoK sees that
            step('Walrus', ['Walrus'], 'the window changed')
            step('Twice', [], '2 places')                       # it's in two places: must refuse
        finally:
            window.terminate()
            window.wait()
            clicker.stop()
            if previous:
                hypr('dispatch', f'hl.dsp.focus({{window="address:{previous}"}})')
            x, y = pointer.split(',')
            hypr('dispatch', f'hl.dsp.cursor.move({{ x = {int(float(x))}, y = {int(float(y))} }})')
    print('Clicking by reading the screen works.' if not failures else f'{failures} check(s) failed.')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
