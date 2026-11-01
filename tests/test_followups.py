import json
import unittest
from unittest.mock import patch, Mock

from blok import browser
from blok.backend import Backend
from blok.nlu import ConversationContext, resolve_intent, site_of


class SiteDetectionTests(unittest.TestCase):
    def test_hostnames_not_substrings(self):
        self.assertEqual(site_of('https://www.netflix.com/browse'), 'netflix')  # contains "x"
        self.assertEqual(site_of('https://store.steampowered.com/app/1'), 'steam')
        self.assertEqual(site_of('https://mail.google.com/mail/u/0'), 'gmail')
        self.assertEqual(site_of('https://blog.example.org/post'), 'blog.example.org')


class FollowUpTests(unittest.TestCase):
    def on(self, url):
        context = ConversationContext()
        context.update_tab(7, url=url)
        return context

    def task(self, text, context=None):
        intent = resolve_intent(text, context)
        return intent.action_kind, (json.loads(intent.action_value) if intent.action_value.startswith('{') else intent.action_value)

    def test_youtube_then_get_me_a_video(self):
        kind, task = self.task('get me a bbs or pewdiepie video', self.on('https://www.youtube.com/'))
        self.assertEqual(task, {'action': 'play', 'site': 'youtube', 'query': 'bbs or pewdiepie', 'target_tab_id': 7})
        self.assertEqual(self.task('play pewdiepie', self.on('https://www.youtube.com/'))[1]['site'], 'youtube')
        self.assertEqual(self.task('play pewdiepie')[1]['site'], 'spotify')

    def test_steam_then_search(self):
        steam = self.on('https://store.steampowered.com/')
        self.assertEqual(self.task('search for phantom blade', steam),
                         ('url', 'https://store.steampowered.com/search/?term=phantom+blade'))
        self.assertEqual(self.task('search steam for phantom blade')[1], 'https://store.steampowered.com/search/?term=phantom+blade')
        self.assertEqual(self.task('search for weather')[1]['site'], 'google')

    def test_click_that_button_points(self):
        self.assertEqual(self.task('click that button')[1]['pointer'], True)
        self.assertEqual(self.task('hit this')[1]['pointer'], True)
        self.assertEqual(self.task('click the subscribe button')[1], {'action': 'click', 'target': 'subscribe button'})

    def test_search_this_site(self):
        self.assertEqual(self.task('search this site for pricing')[1], {'action': 'site_search', 'query': 'pricing'})


class BackendFollowUpTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()

    def test_page_probe_sets_site_from_focused_browser(self):
        with patch.object(browser, 'run', return_value=json.dumps({'class': 'brave-origin'})), \
             patch.object(browser, 'request', return_value={'tabId': 3, 'url': 'https://store.steampowered.com/app/9'}):
            self.backend.refresh_page_context()
        self.assertEqual((self.backend.context.active_site, self.backend.context.active_tab_id), ('steam', 3))

    def test_page_probe_falls_back_to_old_extension_and_clears_for_other_apps(self):
        def request(payload, **_):
            if payload['action'] == 'active':
                raise RuntimeError('Unsupported action')
            return {'tabId': 4, 'observation': {'url': 'https://www.youtube.com/'}}
        with patch.object(browser, 'run', return_value=json.dumps({'class': 'brave-origin'})), patch.object(browser, 'request', side_effect=request):
            self.backend.refresh_page_context()
        self.assertEqual(self.backend.context.active_site, 'youtube')
        with patch.object(browser, 'run', return_value=json.dumps({'class': 'foot'})):
            self.backend.refresh_page_context()
        self.assertIsNone(self.backend.context.active_site)

    def test_pointer_click_confirms_risky_labels(self):
        calls = []
        def request(payload, **_):
            calls.append(payload['action'])
            return {'name': 'Delete account', 'control': {'id': 'c1'}, 'page': 'p'} if payload['action'] == 'pointer' else {'verified': False}
        self.backend.request_approval = Mock(return_value=False)
        with patch.object(browser, 'ping', return_value={'version': 'phase8-v1'}), patch.object(browser, 'request', side_effect=request):
            with self.assertRaises(RuntimeError):
                self.backend.click_pointer()
        self.assertEqual(calls, ['pointer'])  # rejected: never clicked

    def test_pointer_click_needs_new_extension(self):
        with patch.object(browser, 'ping', return_value={'version': 'phase6-v1'}):
            with self.assertRaisesRegex(RuntimeError, 'Reload'):
                self.backend.click_pointer()


if __name__ == '__main__':
    unittest.main()
