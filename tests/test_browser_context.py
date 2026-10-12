import unittest
from unittest.mock import Mock, patch

from hyprash.backend import Backend
from hyprash.commands import Action


class BrowserContextTests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend()
        self.backend.emit=Mock()

    def test_search_stores_only_current_tab_metadata(self):
        result={'message':'Searched google for games','verified':True,'tabId':7,
                'url':'https://www.google.com/search?q=games',
                'context':{'tabId':7,'url':'https://www.google.com/search?q=games','site':'google','query':'games'}}
        with patch('hyprash.browser.request',return_value=result):
            self.backend.browser_task({'action':'search','site':'google','query':'games'})
        self.assertEqual(self.backend.browser_context['tabId'],7)
        self.assertEqual(self.backend.browser_context['query'],'games')
        self.assertNotIn('controls',self.backend.browser_context)

    def test_followup_rechecks_tab_and_url_before_result_action(self):
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('hyprash.backend.time.monotonic',return_value=1), patch('hyprash.browser.request',side_effect=[
            {'message':'Observed','verified':True,'tabId':7,'url':'https://www.google.com/search?q=games'},
            {'message':'Opened Games','verified':True,'tabId':7,'url':'https://example.com'}]) as request:
            self.assertEqual(self.backend.browser_task({'action':'result','index':1}),'Opened Games')
        self.assertEqual(request.call_args_list[0].args[0],{'action':'inspect'})
        sent=request.call_args_list[1].args[0]
        self.assertEqual(sent['context']['tabId'],7)
        self.assertEqual(sent['context']['url'],'https://www.google.com/search?q=games')
        self.assertIsNone(self.backend.browser_context)

    def test_tab_or_navigation_change_clears_context_without_result_action(self):
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('hyprash.backend.time.monotonic',return_value=1), patch('hyprash.browser.request',return_value={
            'message':'Observed','verified':True,'tabId':8,'url':'https://www.google.com/search?q=games'}) as request:
            with self.assertRaisesRegex(RuntimeError,'no longer current'):
                self.backend.browser_task({'action':'result','index':1})
        request.assert_called_once()
        self.assertIsNone(self.backend.browser_context)

    def test_expired_context_never_inspects_or_navigates(self):
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('hyprash.backend.time.monotonic',return_value=301), patch('hyprash.browser.request') as request:
            with self.assertRaisesRegex(RuntimeError,'No current search results'):
                self.backend.browser_task({'action':'result','index':1})
        request.assert_not_called()
        self.assertIsNone(self.backend.browser_context)

    def test_followup_is_rejected_before_laya_when_no_context_exists(self):
        self.backend.start_decisions=Mock()
        self.backend.submit_decision('open the first result')
        self.backend.start_decisions.assert_not_called()
        self.assertTrue(any('No current search results' in call.kwargs.get('message','')
                            for call in self.backend.emit.call_args_list))


if __name__ == '__main__':
    unittest.main()
