import json
import unittest
from unittest.mock import Mock, patch

from blok import browser, mcp_bridge, snapshot
from blok.backend import Backend


def control(name, role='button', section='', in_view=True, disabled=False, state=(), n=0):
    return {'ref': f'e{n}', 'role': role, 'name': name, 'section': section, 'in_view': in_view, 'disabled': disabled,
            'state': list(state), 'control': {'id': f'control-{n}', 'fingerprint': name}}


def page(*names):
    return [control(name, n=i) if isinstance(name, str) else {**name, 'ref': f'e{i}'} for i, name in enumerate(names)]


class ResolveTests(unittest.TestCase):
    def picks(self, said, controls, **kw):
        found = snapshot.resolve(said, controls, **kw)
        return found and found['name']

    def test_exact_and_partial_names(self):
        controls = page('Sign in', 'Pricing', 'Download for Linux')
        self.assertEqual(self.picks('sign in', controls), 'Sign in')
        self.assertEqual(self.picks('the sign in button', controls), 'Sign in')
        self.assertEqual(self.picks('download', controls), 'Download for Linux')

    def test_misheard_words_still_match(self):
        controls = page('Subscribe', 'Settings', 'Add to cart', 'Pricing', 'Sign in')
        for said, meant in (('subscrib', 'Subscribe'), ('setting', 'Settings'), ('add to card', 'Add to cart'),
                            ('prizing', 'Pricing'), ('signin', 'Sign in')):
            self.assertEqual(self.picks(said, controls), meant, said)

    def test_nothing_close_is_none(self):
        self.assertIsNone(snapshot.resolve('launch the rocket', page('Sign in', 'Pricing')))
        self.assertIsNone(snapshot.resolve('save', page('Sign in')))

    def test_a_short_word_does_not_match_inside_a_long_name_by_accident(self):
        self.assertIsNone(snapshot.resolve('cat', page('Category', 'Catalog of everything')))

    def test_half_of_what_you_said_missing_is_not_a_match(self):
        # Found on Wikipedia: this used to pick a link named "downloaded".
        self.assertIsNone(snapshot.resolve('download pdf', page('downloaded', 'Pricing')))
        self.assertEqual(self.picks('add to card', page('Add to cart')), 'Add to cart')

    def test_tabs_are_often_links(self):
        # Found on GitHub: the Code tab is a link, next to a "Code" dropdown button.
        controls = [control('Code', 'link', 'Repository', n=1), control('Code', 'button', 'main', n=2)]
        self.assertEqual(snapshot.resolve('the code tab', controls)['ref'], 'e1')

    def test_ordinal_counts_partial_names(self):
        # Found on Hacker News: "comments", "12 comments", "40 comments".
        controls = page('comments', '12 comments', '40 comments', 'Pricing')
        self.assertEqual(self.picks('second comments', controls), '12 comments')

    def test_role_word_prefers_that_role(self):
        controls = [control('Search', 'textbox', n=1), control('Search', 'button', n=2)]
        self.assertEqual(snapshot.resolve('search button', controls)['ref'], 'e2')
        self.assertEqual(snapshot.resolve('search field', controls)['ref'], 'e1')

    def test_prefers_the_one_on_screen(self):
        controls = [control('Save', in_view=False, n=1), control('Save', n=2)]
        self.assertEqual(snapshot.resolve('save', controls)['ref'], 'e2')

    def test_navigation_prefers_links_then_topmost(self):
        controls = [control('Pricing', 'button', n=1), control('Pricing', 'link', n=2), control('Pricing', 'link', n=3)]
        self.assertEqual(snapshot.resolve('pricing', controls, navigate=True)['ref'], 'e2')

    def test_ordinals(self):
        controls = [control('Add to cart', n=i) for i in range(1, 4)]
        self.assertEqual(snapshot.resolve('second add to cart', controls)['ref'], 'e2')
        self.assertEqual(snapshot.resolve('the last add to cart button', controls)['ref'], 'e3')
        with self.assertRaisesRegex(RuntimeError, 'only 3'):
            snapshot.resolve('fifth add to cart', controls)

    def test_section_tells_them_apart(self):
        controls = [control('Save', section='header', n=1), control('Save', section='footer', n=2)]
        self.assertEqual(snapshot.resolve('save in the footer', controls)['ref'], 'e2')
        with self.assertRaisesRegex(snapshot.Ambiguous, 'in the header.*in the footer'):
            snapshot.resolve('save', controls)

    def test_in_can_be_part_of_the_name(self):
        self.assertEqual(self.picks('log in to github', page('Log in to GitHub', 'Pricing')), 'Log in to GitHub')

    def test_never_guesses_between_lookalikes(self):
        with self.assertRaisesRegex(snapshot.Ambiguous, 'Which one'):
            snapshot.resolve('save', page('Save draft', 'Save copy'))
        with self.assertRaisesRegex(snapshot.Ambiguous, 'second Save'):
            snapshot.resolve('save', page('Save', 'Save'))

    def test_disabled_is_never_chosen_and_says_why(self):
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            snapshot.resolve('save', [control('Save', disabled=True)])
        self.assertEqual(snapshot.resolve('save', [control('Save', disabled=True, n=1), control('Save', n=2)])['ref'], 'e2')

    def test_compact_text(self):
        text = snapshot.compact({'title': 'Shop', 'url': 'https://x.test/', 'total': 9, 'truncated': True, 'controls': [
            control('Buy', section='main', state=['focused'], n=1), control('Help', 'link', in_view=False, n=2)]})
        self.assertEqual(text.splitlines(), ['Shop — https://x.test/', 'e1 button "Buy" @main [focused]',
                                             'e2 link "Help" [offscreen]', '… and 7 more offscreen'])


class ClickTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.laya = None
        self.sent = []
        self.controls = page('Save', 'Pricing', 'Delete repository')
        self.effects = {}

    def request(self, payload, **_):
        self.sent.append(payload)
        if payload['action'] == 'snapshot':
            return {'controls': self.controls, 'page': 'p', 'truncated': getattr(self, 'truncated', False), 'title': 'T', 'url': 'u'}
        if payload['action'] == 'click_observed':
            return {'message': 'Clicked it · result not verified', 'verified': bool(self.effects), 'effects': self.effects, 'tabId': 7}
        return {'message': 'Clicked by label', 'verified': False}

    def click(self, target, **task):
        with patch.object(browser, 'ping', return_value={'version': 'phase12-v1'}), patch.object(browser, 'request', side_effect=self.request):
            return self.backend.browser_task({'action': 'click', 'target': target, **task})

    def test_clicks_the_observed_control_by_reference(self):
        self.assertEqual(self.click('save'), 'Clicked it · result not verified')
        self.assertEqual(self.sent[-1], {'action': 'click_observed', 'control': self.controls[0]['control'], 'page': 'p'})

    def test_reports_and_follows_what_the_click_caused(self):
        self.effects = {'new_tab': {'tabId': 9, 'url': 'https://example.com/a'}}
        self.assertEqual(self.click('save'), 'Clicked it · opened a new tab')
        self.assertEqual((self.backend.context.active_tab_id, self.backend.context.active_site), (9, 'example.com'))
        self.effects = {'navigated': 'https://github.com/'}
        self.assertEqual(self.click('save'), 'Clicked it · the page changed')
        self.assertEqual((self.backend.context.active_tab_id, self.backend.context.active_site), (7, 'github'))
        self.effects = {'download': 'game.zip'}
        self.assertEqual(self.click('save'), 'Clicked it · downloading game.zip')

    def test_risky_control_reached_by_a_harmless_word_asks_first(self):
        self.backend.request_approval = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, 'Delete repository'):
            self.click('repository')
        self.assertFalse(any(p['action'] == 'click_observed' for p in self.sent))

    def test_risky_word_you_said_is_not_asked_twice(self):
        self.backend.request_approval = Mock(return_value=False)
        self.click('delete repository')       # the plan's approval step covered this
        self.backend.request_approval.assert_not_called()

    def test_no_match_offers_the_closest(self):
        with self.assertRaisesRegex(RuntimeError, r'No visible control named launch.*Closest'):
            self.click('launch')

    def test_laya_suggestion_must_be_confirmed(self):
        self.backend.laya = Mock(pick=Mock(return_value=('Pricing', 0.9)))
        self.backend.request_approval = Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError, 'Pricing'):
            self.click('how much does it cost')
        self.assertFalse(any(p['action'] == 'click_observed' for p in self.sent))
        self.backend.request_approval = Mock(return_value=True)
        self.click('how much does it cost')
        self.assertEqual(self.sent[-1]['control'], self.controls[1]['control'])

    def test_a_long_page_still_tries_the_exact_label(self):
        self.truncated = True
        self.assertEqual(self.click('launch'), 'Clicked by label')

    def test_color_and_old_extension_use_the_old_path(self):
        self.assertEqual(self.click('save', color='blue'), 'Clicked by label')
        with patch.object(browser, 'ping', return_value={'version': 'phase11-v1'}), patch.object(browser, 'request', side_effect=self.request):
            self.assertEqual(self.backend.browser_task({'action': 'click', 'target': 'save'}), 'Clicked by label')


class McpTests(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.backend.emit = Mock()
        self.backend.request_approval = Mock(return_value=True)
        self.bridge = mcp_bridge.Bridge(self.backend)
        self.controls = page('Save', 'Delete repository')

    def request(self, payload, **_):
        if payload['action'] == 'snapshot':
            return {'controls': self.controls, 'page': 'p', 'title': 'T', 'url': 'u'}
        return {'message': 'Clicked it', 'verified': True, 'effects': {}, 'tabId': 7}

    def call(self, name, args):
        with patch.object(browser, 'ping', return_value={'version': 'phase12-v1'}), patch.object(browser, 'request', side_effect=self.request) as request, \
             patch.object(Backend, 'browser_in_front', return_value=True):
            self.requests = request
            return self.bridge.call(name, args, 'Client')

    def test_snapshot_needs_approval_and_is_compact_text(self):
        text = self.call('page_snapshot', {})
        self.assertIn('e0 button "Save"', text)
        self.assertIn('see the buttons', self.backend.request_approval.call_args.args[0])

    def test_click_by_ref_shows_the_real_name_on_the_card(self):
        self.assertEqual(self.call('page_click', {'ref': 'e1', 'target': 'something harmless'}), 'Clicked it')
        self.assertIn('Delete repository', self.backend.request_approval.call_args.args[0])
        self.assertEqual(self.requests.call_args.args[0]['control'], self.controls[1]['control'])

    def test_stale_or_missing_ref_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'new page_snapshot'):
            self.call('page_click', {'ref': 'e99'})
        with self.assertRaisesRegex(RuntimeError, 'ref or a target'):
            self.call('page_click', {})
        self.backend.request_approval.assert_not_called()


if __name__ == '__main__':
    unittest.main()
