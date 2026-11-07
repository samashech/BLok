import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import numpy

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
                   patch.object(clicker, 'click', side_effect=lambda: self.clicked.append(self.backend.hide_overlay.call_args.args[0])),
                   patch.object(screen, 'clients', side_effect=lambda: {'0xabc'}),
                   patch.object(screen, 'capture_gray', return_value=None),
                   patch.object(screen, 'lookalikes', return_value=0),
                   patch.object(screen, 'read_blobs', return_value=[])]
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
        self.assertEqual(self.backend.click_by_sight('Save button'), 'Clicked Save · nothing visibly changed')
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
        self.assertEqual(self.backend.click_by_sight('Save'), 'Clicked Save · nothing visibly changed')

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


class ClickEffectTests(ClickBySightTests):
    """What a click did, as the desktop saw it. Runs on top of the same stand-ins."""
    def said(self):
        with patch.object(time, 'sleep'):
            return self.backend.click_by_sight('Save')

    def looks(self, *images):
        queue = list(images)
        return patch.object(screen, 'capture_gray', side_effect=lambda window: queue.pop(0))

    def test_new_window(self):
        windows = iter([{'0xabc'}, {'0xabc', '0xnew'}])
        with patch.object(screen, 'clients', side_effect=lambda: next(windows)):
            self.assertEqual(self.said(), 'Clicked Save · opened a new window')

    def test_focus_moved(self):
        states = iter([WINDOW, WINDOW, {**WINDOW, 'address': '0xdef'}])
        with patch.object(screen, 'active_window', side_effect=lambda: next(states)):
            self.assertEqual(self.said(), 'Clicked Save · focus moved to another window')

    def test_window_changed_and_nothing_changed(self):
        still = numpy.zeros((100, 100), numpy.uint8)
        moved = still.copy()
        moved[10:40, 10:40] = 200
        with self.looks(still, still, moved):
            self.assertEqual(self.said(), 'Clicked Save · the window changed')
        with self.looks(still, still, still):
            self.assertEqual(self.said(), 'Clicked Save · nothing visibly changed')

    def test_an_animated_window_claims_nothing(self):
        still = numpy.zeros((100, 100), numpy.uint8)
        moving = still.copy()
        moving[:50] = 200
        with self.looks(still, moving, still):
            self.assertEqual(self.said(), 'Clicked Save')

    def test_browser_page_and_tab_changes_are_followed(self):
        self.backend.context.update_tab(7, url='https://example.com/')
        window = {**WINDOW, 'class': 'brave-browser'}
        self.active = window
        tabs = iter([{'tabId': 7, 'url': 'https://example.com/'}, {'tabId': 7, 'url': 'https://github.com/'}])
        with patch.object(screen, 'ocr_window', side_effect=lambda **_: {'words': self.words, 'window': window}), \
             patch.object(browser, 'request', side_effect=lambda *a, **k: next(tabs)):
            self.assertEqual(self.said(), 'Clicked Save · the page changed')
        self.assertEqual(self.backend.context.active_site, 'github')
        tabs = iter([{'tabId': 7, 'url': 'https://github.com/'}, {'tabId': 8, 'url': 'brave://newtab/'}])
        with patch.object(screen, 'ocr_window', side_effect=lambda **_: {'words': self.words, 'window': window}), \
             patch.object(browser, 'request', side_effect=lambda *a, **k: next(tabs)):
            self.assertEqual(self.said(), 'Clicked Save · opened a new tab')
        self.assertEqual(self.backend.context.active_tab_id, 8)

    def test_a_failed_look_never_undoes_the_click_report(self):
        with patch.object(screen, 'clients', side_effect=['0xabc', OSError('gone')]) as _:
            pass
        calls = iter([{'0xabc'}])

        def clients():
            try:
                return next(calls)
            except StopIteration:
                raise OSError('gone')
        with patch.object(screen, 'clients', side_effect=clients):
            self.assertEqual(self.said(), 'Clicked Save')


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
    """Real OCR and real pixels on a drawn window."""
    BUTTONS = (('Zebra', 40, 40), ('Walrus', 320, 40), ('Twice', 40, 200), ('Twice', 320, 200), ('Saved', 40, 360), ('Cancel', 320, 360))
    SCENES = (('white', 'black', '#eeeeee', 34), ('#1e1e2e', '#dddddd', '#303040', 34),
              ('white', 'black', '#eeeeee', 14), ('#1e1e2e', '#dddddd', '#303040', 14),
              ('#1e1e2e', '#9a9aa8', '#303040', 14), ('white', '#777777', '#f4f4f4', 13))

    def read(self, background, ink, box, size=34, buttons=None, factor=1):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_RUNTIME_DIR': folder}):
            drawn = os.path.join(folder, 'drawn.png')
            command = ['magick', '-size', f'{604 * factor}x{500 * factor}', f'xc:{background}', '-font', 'DejaVu-Sans', '-pointsize', str(size * factor)]
            for text, x, y in buttons or self.BUTTONS:
                x, y = x * factor, y * factor
                command += ['-fill', box, '-stroke', ink, '-draw', f'rectangle {x},{y} {x + 240 * factor},{y + 80 * factor}',
                            '-stroke', 'none', '-fill', ink, '-annotate', f'+{x + 50 * factor}+{y + 50 * factor}', text]
            subprocess.run(command + [drawn], check=True)
            real = subprocess.run

            def run(args, *rest, **kw):
                if args[0] == 'grim':
                    shutil.copy(drawn, args[-1])
                    return Mock(returncode=0)
                return real(args, *rest, **kw)
            with patch.object(screen.subprocess, 'run', side_effect=run):
                return screen.ocr_window({'at': [0, 0], 'size': [604, 500]}, sparse=True)

    def found(self, seen, label):
        boxes = [box for box in screen.find_words(seen['words'], label) if box['conf'] >= 50]
        if not boxes:
            boxes = [box for box in screen.find_words(seen['words'] + screen.read_blobs(seen, label), label) if box['conf'] >= 50]
        return boxes

    def test_finds_labels_in_every_scene_in_the_right_place(self):
        for scene in self.SCENES:
            seen = self.read(*scene)
            for label, left, top in (('Zebra', 40, 40), ('Walrus', 320, 40), ('Cancel', 320, 360)):
                boxes = self.found(seen, label)
                self.assertEqual(len(boxes), 1, (label, scene))
                self.assertTrue(left < boxes[0]['x'] + boxes[0]['w'] // 2 < left + 240, (label, scene, boxes))
                self.assertTrue(top < boxes[0]['y'] + boxes[0]['h'] // 2 < top + 80, (label, scene, boxes))

    def test_a_copy_the_ocr_missed_is_still_noticed(self):
        for scene in self.SCENES:
            seen = self.read(*scene)
            boxes = self.found(seen, 'Twice')
            self.assertTrue(boxes, scene)
            seen['words'] = [w for w in seen['words'] if not (w['text'].lower() == 'twice' and w['x'] > 300)]   # OCR "missed" one
            self.assertEqual(screen.lookalikes(seen, boxes[0]), 1, scene)

    def test_a_single_label_has_no_lookalikes(self):
        for scene in self.SCENES:
            seen = self.read(*scene)
            for label in ('Zebra', 'Walrus', 'Cancel'):
                self.assertEqual(screen.lookalikes(seen, self.found(seen, label)[0]), 0, (label, scene))

    def test_part_of_a_longer_word_is_not_a_copy(self):
        seen = self.read('white', 'black', '#eeeeee', 34, buttons=(('Save', 40, 40), ('Saved', 320, 40)))
        self.assertEqual(screen.lookalikes(seen, self.found(seen, 'Save')[0]), 0)

    def test_blobs_and_lookalikes_map_back_on_a_scaled_display(self):
        seen = self.read('#1e1e2e', '#dddddd', '#303040', 14, factor=2)
        self.assertEqual(seen['factor'], 2)
        box = self.found(seen, 'Walrus')[0]
        self.assertTrue(320 < box['x'] + box['w'] // 2 < 560, box)
        twice = self.found(seen, 'Twice')[0]
        seen['words'] = [w for w in seen['words'] if not (w['text'].lower() == 'twice' and w['x'] > 300)]
        self.assertEqual(screen.lookalikes(seen, twice), 1)

    def test_stops_reading_once_the_label_is_clearly_found(self):
        counted = []
        real = screen._tesseract
        with patch.object(screen, '_tesseract', side_effect=lambda *a, **k: counted.append(1) or real(*a, **k)):
            self.read('white', 'black', '#eeeeee', 34)
            everything = len(counted)
            counted.clear()
            real_ocr = screen.ocr_window
            with patch.object(screen, 'ocr_window', side_effect=lambda window, sparse: real_ocr(window, sparse=sparse, wanted='Zebra')):
                self.read('white', 'black', '#eeeeee', 34)
        self.assertEqual(everything, 4)
        self.assertEqual(len(counted), 1)

    def test_blobs_read_small_dim_text_by_themselves(self):
        seen = self.read('#1e1e2e', '#9a9aa8', '#303040', 14)
        words = {w['text'].lower() for w in screen.read_blobs(seen, 'Twice') if w['conf'] >= 50}
        self.assertLessEqual({'zebra', 'twice', 'cancel'}, words)


class MergeTests(unittest.TestCase):
    def test_overlapping_readings_are_one_place(self):
        words = [word('Cancel', 100, conf=70.0), word('Cancel', 112, conf=90.0), word('Cance1', 104, conf=60.0), word('Cancel', 400)]
        boxes = screen.find_words(words, 'Cancel')
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0]['conf'], 90.0)

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
