import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from blok import browser, clicker, screen
from blok.backend import Backend

WINDOW = {'address': '0xabc', 'at': [100, 200], 'size': [800, 600], 'title': 'App'}


def word(text, x, y=50, conf=90.0):
    return {'text': text, 'x': x, 'y': y, 'w': 40, 'h': 10, 'conf': conf}


class ClickerTests(unittest.TestCase):
    def tearDown(self):
        clicker._daemon = None

    def test_says_how_to_install_when_missing(self):
        with patch.object(clicker.shutil, 'which', return_value=None):
            self.assertFalse(clicker.available())
            with self.assertRaisesRegex(RuntimeError, 'sudo pacman -S ydotool'):
                clicker.click()

    def test_private_daemon_can_only_click(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder}), \
             patch.object(clicker.shutil, 'which', return_value='/usr/bin/x'), patch.object(clicker, '_answers', return_value=True), \
             patch.object(clicker.atexit, 'register'), patch.object(clicker.subprocess, 'Popen') as popen, patch.object(clicker.subprocess, 'run') as run:
            popen.return_value.poll.return_value = None
            run.return_value = Mock(returncode=0)
            clicker.click()
            clicker.click()
        popen.assert_called_once()                       # one daemon, reused
        args = popen.call_args.args[0]
        self.assertIn('--keyboard-off', args)
        self.assertIn('--socket-perm=0600', args)
        self.assertEqual(run.call_args.args[0], ['ydotool', 'click', '0xC0'])
        self.assertTrue(run.call_args.kwargs['env']['YDOTOOL_SOCKET'].endswith('blok-ydotool.sock'))

    def test_reports_why_the_daemon_failed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder}), \
             patch.object(clicker.shutil, 'which', return_value='/usr/bin/x'), patch.object(clicker.atexit, 'register'), \
             patch.object(clicker.subprocess, 'Popen') as popen, patch.object(clicker.subprocess, 'run') as run:
            popen.return_value.poll.return_value = 1
            popen.return_value.stderr.read.return_value = b'failed to open uinput device'
            with self.assertRaisesRegex(RuntimeError, 'uinput'):
                clicker.click()
        run.assert_not_called()


class ClickBySightTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.hide_overlay = Mock()
        self.words = [word('Save', 10), word('Cancel', 100)]
        self.active = dict(WINDOW)
        self.pointer = None
        self.commands = []
        self.clicked = []
        patches = [patch.object(screen, 'ocr_window', side_effect=lambda **_: {'words': self.words, 'window': dict(WINDOW)}),
                   patch.object(screen, 'active_window', side_effect=lambda: self.active),
                   patch.object(browser, 'run', side_effect=self.run_command),
                   patch.object(clicker, 'available', return_value=True),
                   patch.object(clicker, 'click', side_effect=lambda: self.clicked.append(self.backend.hide_overlay.call_args.args[0]))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def run_command(self, args):
        self.commands.append(args)
        if args[1] == 'cursorpos':
            return self.pointer or f'{self.x}, {self.y}'
        if args[1] == 'dispatch':
            found = args[2].split('x = ')[1]
            self.x, self.y = int(found.split(',')[0]), int(found.split('y = ')[1].split(' ')[0])
        return 'ok'

    def test_clicks_the_center_of_the_label_with_the_overlay_hidden(self):
        self.assertEqual(self.backend.click_by_sight('Save button'), 'Clicked Save')
        self.assertEqual((self.x, self.y), (100 + 10 + 20, 200 + 50 + 5))
        self.assertEqual(self.clicked, [True])
        self.assertEqual(self.backend.hide_overlay.call_args.args[0], False)     # and it comes back

    def test_overlay_comes_back_even_if_the_click_fails(self):
        with patch.object(clicker, 'click', side_effect=RuntimeError('no')):
            with self.assertRaises(RuntimeError):
                self.backend.click_by_sight('Save')
        self.assertEqual(self.backend.hide_overlay.call_args.args[0], False)

    def test_refuses_a_word_in_several_places(self):
        self.words = [word('Save', 10), word('Save', 300, y=400)]
        with self.assertRaisesRegex(RuntimeError, '2 places'):
            self.backend.click_by_sight('Save')
        self.assertEqual(self.clicked, [])

    def test_ignores_words_the_ocr_barely_read(self):
        self.words = [word('Save', 10, conf=20.0)]
        with self.assertRaisesRegex(RuntimeError, "can't see"):
            self.backend.click_by_sight('Save')

    def test_refuses_if_focus_moved_or_the_window_moved(self):
        for change in ({'address': '0xdef'}, {'at': [0, 0]}, {'size': [10, 10]}):
            self.active = {**WINDOW, **change}
            with self.assertRaisesRegex(RuntimeError, 'window changed'):
                self.backend.click_by_sight('Save')
        self.assertEqual(self.clicked, [])

    def test_a_changed_title_alone_is_not_a_different_window(self):
        self.active = {**WINDOW, 'title': 'App - edited'}
        self.assertEqual(self.backend.click_by_sight('Save'), 'Clicked Save')

    def test_refuses_if_the_pointer_did_not_arrive(self):
        self.pointer = '5, 5'
        with self.assertRaisesRegex(RuntimeError, 'pointer'):
            self.backend.click_by_sight('Save')
        self.assertEqual(self.clicked, [])

    def test_risky_label_is_confirmed_and_checked_again(self):
        self.words = [word('Delete', 10)]
        self.backend.request_approval = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, 'Delete'):
            self.backend.click_by_sight('Delete')
        self.assertEqual(self.clicked, [])

        def moved(*_, **__):
            self.words = [word('Delete', 300)]    # the page scrolled while you decided
            return True
        self.backend.request_approval = Mock(side_effect=moved)
        with self.assertRaisesRegex(RuntimeError, 'moved'):
            self.backend.click_by_sight('Delete')
        self.assertEqual(self.clicked, [])

    def test_without_ydotool_it_points_and_says_how_to_finish(self):
        with patch.object(clicker, 'available', return_value=False):
            message = self.backend.click_by_sight('Save')
        self.assertIn('The pointer is on Save', message)
        self.assertIn('sudo pacman -S ydotool', message)


class BrowserFallbackTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.laya = None
        self.backend.click_by_sight = Mock(return_value='Clicked Launch')
        self.sees = True

    def click(self, target='launch', snapshot=None, error=None, truncated=False):
        def request(payload, **_):
            if payload['action'] == 'snapshot':
                if error:
                    raise browser.BrowserTaskError(error)
                return {'controls': snapshot or [{'ref': 'e1', 'role': 'link', 'name': 'Pricing', 'control': {'id': 'c'}}], 'page': 'p', 'truncated': truncated}
            if payload['action'] == 'click':
                raise browser.BrowserTaskError('No visible control named ' + target)
            raise AssertionError(payload)
        with patch.object(browser, 'ping', return_value={'version': 'phase12-v1'}), patch.object(browser, 'request', side_effect=request), \
             patch.object(clicker, 'available', return_value=self.sees):
            return self.backend.browser_task({'action': 'click', 'target': target})

    def test_looks_at_the_screen_when_the_page_has_no_such_control(self):
        self.assertEqual(self.click(), 'Clicked Launch')
        self.backend.click_by_sight.assert_called_once_with('launch')

    def test_also_past_the_end_of_a_long_page(self):
        self.assertEqual(self.click(truncated=True), 'Clicked Launch')

    def test_pages_extensions_cant_touch_use_the_screen(self):
        self.assertEqual(self.click(error='Cannot access a chrome:// URL'), 'Clicked Launch')

    def test_screen_is_not_used_when_the_page_has_the_control(self):
        with patch.object(Backend, 'click_observed', return_value='Clicked Pricing'):
            self.assertEqual(self.click('pricing'), 'Clicked Pricing')
        self.backend.click_by_sight.assert_not_called()

    def test_not_on_screen_either_offers_the_closest_controls(self):
        self.backend.click_by_sight = Mock(side_effect=RuntimeError('I can\'t see "launch" in this window.'))
        with self.assertRaisesRegex(RuntimeError, 'No visible control named launch.*Pricing'):
            self.click()

    def test_a_refusal_from_the_screen_is_kept(self):
        self.backend.click_by_sight = Mock(side_effect=RuntimeError('I can see "launch" in 2 places here'))
        with self.assertRaisesRegex(RuntimeError, '2 places'):
            self.click()

    def test_without_ydotool_the_page_error_stands(self):
        self.sees = False
        with self.assertRaisesRegex(RuntimeError, 'No visible control'):
            self.click()
        self.backend.click_by_sight.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'Cannot access'):
            self.click(error='Cannot access a chrome:// URL')


@unittest.skipUnless(shutil.which('tesseract') and shutil.which('magick'), 'needs tesseract and imagemagick')
class RealOcrTests(unittest.TestCase):
    """Real OCR on a drawn window. Reading it as one block of text finds no buttons at all."""
    BUTTONS = (('Zebra', 40, 40), ('Walrus', 320, 40), ('Twice', 40, 200), ('Twice', 320, 200))

    def read(self, background, ink, box, size=34):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder}):
            drawn = os.path.join(folder, 'drawn.png')
            command = ['magick', '-size', '604x600', f'xc:{background}', '-pointsize', str(size)]
            for text, x, y in self.BUTTONS:
                command += ['-fill', box, '-stroke', ink, '-draw', f'rectangle {x},{y} {x + 240},{y + 80}',
                            '-stroke', 'none', '-fill', ink, '-annotate', f'+{x + 50}+{y + 52}', text]
            subprocess.run(command + [drawn], check=True)
            real = subprocess.run

            def run(args, *rest, **kw):
                if args[0] == 'grim':
                    shutil.copy(drawn, args[-1])
                    return Mock(returncode=0)
                return real(args, *rest, **kw)
            with patch.object(screen.subprocess, 'run', side_effect=run):
                return screen.ocr_window({'at': [0, 0], 'size': [604, 600]}, sparse=True)

    def test_finds_scattered_buttons_on_light_and_dark_windows_large_and_small(self):
        for colors in (('white', 'black', '#eeeeee'), ('#1e1e2e', '#dddddd', '#303040'),
                       ('white', 'black', '#eeeeee', 14), ('#1e1e2e', '#dddddd', '#303040', 14)):
            words = self.read(*colors)['words']
            for label, left in (('Zebra', 40), ('Walrus', 320)):
                boxes = screen.find_words(words, label)
                self.assertEqual(len(boxes), 1, (label, colors))
                self.assertTrue(left < boxes[0]['x'] + boxes[0]['w'] // 2 < left + 240, (label, boxes))
                self.assertTrue(40 < boxes[0]['y'] + boxes[0]['h'] // 2 < 120, (label, boxes))
            sure = [box for box in screen.find_words(words, 'Twice') if box['conf'] >= 50]
            # Small dim text can be too blurry to read ("Tuvice"): then it's not found, never guessed.
            self.assertIn(len(sure), (2,) if colors[3:] == () or colors[0] == 'white' else (0, 2), colors)


class MergeTests(unittest.TestCase):
    def test_keeps_words_from_every_treatment_once(self):
        first = {'text': '', 'score': 80.0, 'words': [word('Zebra', 10), word('Save', 100, conf=60.0)]}
        second = {'text': '', 'score': 70.0, 'words': [word('Walrus', 200), word('Save', 102, conf=95.0)]}
        merged = screen._merge(first, second)
        self.assertEqual([w['text'] for w in merged['words']], ['Zebra', 'Save', 'Walrus'])
        self.assertEqual(merged['words'][1]['conf'], 95.0)

    def test_the_same_word_elsewhere_is_a_second_word(self):
        merged = screen._merge({'text': '', 'score': 1, 'words': [word('Save', 10)]}, {'text': '', 'score': 1, 'words': [word('Save', 300)]})
        self.assertEqual(len(screen.find_words(merged['words'], 'Save')), 2)

    def test_multi_word_labels_stay_in_sequence(self):
        merged = screen._merge({'text': '', 'score': 1, 'words': [word('as', 60), word('Other', 300)]}, {'text': '', 'score': 1, 'words': [word('Save', 10)]})
        self.assertEqual(screen.find_word(merged['words'], 'save as')['x'], 10)


class ScaleTests(unittest.TestCase):
    def test_positions_are_mapped_back_on_a_scaled_display(self):
        def run(args, **_):
            if args[:2] == ['magick', 'identify']:
                return Mock(stdout='1600')      # an 800 wide window captured at scale 2
            return Mock(stdout='0.2', returncode=0)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder}), \
             patch.object(screen.shutil, 'which', return_value='/usr/bin/x'), patch.object(screen, '_run', side_effect=run), \
             patch.object(screen, '_tesseract', return_value={'text': 'Save', 'score': 90.0, 'words': [word('Save', 200, y=100)]}):
            seen = screen.ocr_window(dict(WINDOW))
        self.assertEqual((seen['words'][0]['x'], seen['words'][0]['y'], seen['words'][0]['w']), (100, 50, 20))


if __name__ == '__main__':
    unittest.main()
