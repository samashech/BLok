import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch, Mock

from blok import choreo
from blok.backend import Backend
from blok.nlu import resolve_intent


class FakeHyprland:
    """Just enough of hyprctl: clients, workspaces, and the window dispatchers BLoK uses."""
    def __init__(self, windows):
        self.windows = [dict(mapped=True, floating=False, size=[800, 600], focusHistoryID=i, pid=100 + i, **w)
                        for i, w in enumerate(windows)]
        self.active = 1
        self.calls = []

    def tile(self):
        by_ws = {}
        for w in self.windows:
            if not w['floating']:
                by_ws.setdefault(w['workspace']['name'], []).append(w)
        for group in by_ws.values():
            for i, w in enumerate(group):
                w['at'] = [i * 960, 30]

    def __call__(self, *args):
        if args[:2] == ('-j', 'clients'):
            return json.dumps(self.windows)
        if args[:2] == ('-j', 'activeworkspace'):
            return json.dumps({'id': self.active, 'name': str(self.active)})
        if args[:2] == ('-j', 'monitors'):
            return json.dumps([{'focused': True, 'x': 0, 'y': 0, 'width': 1920, 'height': 1200, 'scale': 1, 'reserved': [0, 28, 0, 0]}])
        expression = args[1]
        self.calls.append(expression)
        address = re.search(r'address:(0x\w+)', expression)
        w = next((w for w in self.windows if address and w['address'] == address[1]), None)
        if 'window.move' in expression and 'workspace' in expression:
            name = re.search(r'workspace = "([^"]+)"', expression)[1]
            self.windows.remove(w); self.windows.append(w)        # arrival order decides tiling
            w['workspace'] = {'id': int(name) if name.isdigit() else -98, 'name': name}
        elif 'window.float' in expression:
            w['floating'] = 'enable' in expression
        elif 'window.move' in expression:
            w['at'] = [int(re.search(r'x = (\d+)', expression)[1]), int(re.search(r'y = (\d+)', expression)[1])]
        elif 'window.resize' in expression:
            w['size'] = [int(re.search(r'x = (\d+)', expression)[1]), int(re.search(r'y = (\d+)', expression)[1])]
        elif 'window.close' in expression:
            self.windows.remove(w)
        elif 'focus' in expression and 'workspace' in expression:
            self.active = int(re.search(r'workspace = "(\d+)"', expression)[1])
        self.tile()
        return 'ok'


def win(address, cls, workspace, title=''):
    return {'address': address, 'class': cls, 'initialClass': cls, 'title': title or cls,
            'workspace': {'id': workspace, 'name': str(workspace)}, 'at': [0, 30]}


class ChoreoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for target, value in (('LAYOUTS', root / 'layouts'), ('FOCUS_STATE', root / 'focus.json')):
            p = patch.object(choreo, target, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(choreo.time, 'sleep'); p.start(); self.addCleanup(p.stop)
        p = patch.object(choreo, '_dnd'); self.dnd = p.start(); self.addCleanup(p.stop)

    def fake(self, windows):
        self.hypr = FakeHyprland(windows)
        p = patch.object(choreo, 'hypr', self.hypr); p.start(); self.addCleanup(p.stop)
        return self.hypr

    def test_arrange_puts_apps_side_by_side_on_a_free_workspace(self):
        h = self.fake([win('0x1', 'brave-browser', 1), win('0x2', 'code', 2), win('0x3', 'foot', 3)])
        message = choreo.arrange('code', 'browser')
        code, brave = (next(w for w in h.windows if w['class'] == c) for c in ('code', 'brave-browser'))
        self.assertEqual(code['workspace']['name'], '4')
        self.assertEqual(brave['workspace']['name'], '4')
        self.assertLess(code['at'][0], brave['at'][0])
        self.assertIn('code on the left', message)
        self.assertEqual(next(w for w in h.windows if w['class'] == 'foot')['workspace']['name'], '3')  # untouched

    def test_save_and_restore_reopens_missing_apps(self):
        h = self.fake([win('0x1', 'code', 1), win('0x2', 'obsidian', 2)])
        with patch.object(choreo, '_command_for', return_value=['gtk-launch', 'obsidian']):
            self.assertEqual(choreo.save_layout('Coding'), 'Saved 2 windows as Coding')
        self.assertTrue(choreo.has_layout('coding'))
        h.windows = [w for w in h.windows if w['class'] != 'obsidian']
        choreo.move_to(h.windows[0], '7')
        def launch(argv, **_):
            h.windows.append(dict(win('0x9', 'obsidian', 5), mapped=True, floating=False, size=[1, 1], focusHistoryID=9, pid=9))
        with patch.object(choreo.subprocess, 'Popen', side_effect=launch) as popen:
            message = choreo.restore_layout('coding')
        popen.assert_called_once()
        self.assertEqual({w['class']: w['workspace']['name'] for w in h.windows}, {'code': '1', 'obsidian': '2'})
        self.assertIn('opened 1', message)

    def test_focus_mode_hides_distractions_and_restores_them(self):
        h = self.fake([win('0x1', 'code', 1), win('0x2', 'discord', 2), win('0x3', 'org.telegram.desktop', 3)])
        on = choreo.focus_on()
        self.assertEqual(sorted(w['workspace']['name'] for w in h.windows), ['1', choreo.FOCUS_WORKSPACE, choreo.FOCUS_WORKSPACE])
        self.dnd.assert_called_with(True)
        self.assertIn('discord', on)
        self.assertIn('Focus mode is already on', choreo.focus_on())
        choreo.focus_off()
        self.assertEqual({w['class']: w['workspace']['name'] for w in h.windows},
                         {'code': '1', 'discord': '2', 'org.telegram.desktop': '3'})
        self.dnd.assert_called_with(False)

    def test_close_others_needs_approval(self):
        h = self.fake([win('0x1', 'code', 1), win('0x2', 'foot', 1), win('0x3', 'discord', 2)])
        backend = Backend(); backend.emit = Mock(); backend.request_approval = Mock(return_value=False)
        with self.assertRaises(RuntimeError):
            backend.run_tool({'tool': 'close_others', 'keep': 'code'})
        self.assertIn('foot', backend.request_approval.call_args[0][0])
        self.assertEqual(len(h.windows), 3)

    def test_questions(self):
        self.fake([win('0x1', 'foot', 3), win('0x2', 'code', 3)])
        self.assertEqual(choreo.where('terminal'), 'foot is on workspace 3')
        self.assertEqual(choreo.on_workspace('3'), 'Workspace 3: foot, code')

    def test_layout_names_only_win_when_saved(self):
        self.fake([win('0x1', 'code', 1)])
        self.assertEqual(resolve_intent('coding mode').intent_type, 'unclassified')
        with patch.object(choreo, '_command_for', return_value=None):
            choreo.save_layout('coding')
        self.assertEqual(json.loads(resolve_intent('coding mode').action_value), {'tool': 'layout_restore', 'name': 'coding'})
        self.assertEqual(json.loads(resolve_intent('diwali mode').action_value)['tool'], 'theme')


if __name__ == '__main__':
    unittest.main()
