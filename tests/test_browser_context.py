import unittest
from unittest.mock import Mock, patch

from blok.backend import Backend
from blok.commands import Action


class BrowserContextTests(unittest.TestCase):
    def setUp(self):
        self.backend=Backend()
        self.backend.emit=Mock()

    def test_search_stores_only_current_tab_metadata(self):
        result={'message':'Searched google for games','verified':True,'tabId':7,
                'url':'https://www.google.com/search?q=games',
                'context':{'tabId':7,'url':'https://www.google.com/search?q=games','site':'google','query':'games'}}
        with patch('blok.browser.request',return_value=result):
            self.backend.browser_task({'action':'search','site':'google','query':'games'})
        self.assertEqual(self.backend.browser_context['tabId'],7)
        self.assertEqual(self.backend.browser_context['query'],'games')
        self.assertNotIn('controls',self.backend.browser_context)

    def test_followup_rechecks_tab_and_url_before_result_action(self):
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('blok.backend.time.monotonic',return_value=1), patch('blok.browser.request',side_effect=[
            {'message':'Observed','verified':True,'tabId':7,'url':'https://www.google.com/search?q=games'},
            {'message':'Opened Games','verified':True,'tabId':7,'url':'https://example.com'}]) as request:
            self.assertEqual(self.backend.browser_task({'action':'result','index':1}),'Opened Games')
        self.assertEqual(request.call_args_list[0].args[0],{'action':'inspect'})
        sent=request.call_args_list[1].args[0]
        self.assertEqual(sent['context']['tabId'],7)
        self.assertEqual(sent['context']['url'],'https://www.google.com/search?q=games')
        self.assertIsNone(self.backend.browser_context)

    def test_results_on_the_tab_in_front_are_used_whoever_searched(self):
        # BLoK searched in tab 7, but you are now on tab 8 with your own YouTube search.
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('blok.browser.request',side_effect=[
            {'message':'Observed','verified':True,'tabId':8,'url':'https://www.youtube.com/results?search_query=bbs&sp=EgI'},
            {'message':'Opened a video','verified':True,'tabId':8,'url':'https://www.youtube.com/watch?v=x'}]) as request:
            self.assertEqual(self.backend.browser_task({'action':'result','index':1}),'Opened a video')
        sent=request.call_args_list[1].args[0]['context']
        self.assertEqual((sent['tabId'],sent['site'],sent['query']),(8,'youtube','bbs'))

    def test_tab_without_results_is_refused_without_a_result_action(self):
        self.backend.browser_context={'tabId':7,'url':'https://www.google.com/search?q=games',
                                      'site':'google','query':'games','created_at':0}
        with patch('blok.browser.request',return_value={
            'message':'Observed','verified':True,'tabId':8,'url':'https://github.com/'}) as request:
            with self.assertRaisesRegex(RuntimeError,'No current search results'):
                self.backend.browser_task({'action':'result','index':1})
        request.assert_called_once()
        self.assertIsNone(self.backend.browser_context)

    def test_old_results_still_on_screen_can_be_chosen(self):
        with patch('blok.browser.request',return_value={'tabId':7,'url':'https://www.google.com/search?q=games&sxsrf=x'}):
            self.assertEqual(self.backend.require_browser_context()['query'],'games')

    def test_results_page_recognises_only_real_results(self):
        from blok.backend import results_page
        self.assertEqual(results_page('https://www.google.com/search?q=games&ei=y#ip=1'),('google','games'))
        self.assertEqual(results_page('https://www.youtube.com/results?search_query=bbs'),('youtube','bbs'))
        for url in ('https://www.google.com/','https://www.youtube.com/watch?v=x','https://github.com/search?q=x','brave://newtab/','',None):
            self.assertIsNone(results_page(url),url)

    def test_page_with_no_search_box_falls_back_to_google(self):
        from blok.browser import BrowserTaskError
        with patch('blok.browser.request',side_effect=[
            BrowserTaskError('This page has no search box I can find.'),
            {'message':'Searched google for games','verified':True,'tabId':9,'url':'https://www.google.com/search?q=games'}]) as request:
            message=self.backend.browser_task({'action':'site_search','query':'games','fallback':'google'})
        self.assertEqual(message,'This page has no search box. Searched google for games')
        self.assertEqual(request.call_args_list[1].args[0],{'action':'search','site':'google','query':'games'})

    def test_other_site_search_failures_are_reported_not_repeated(self):
        from blok.browser import BrowserTaskError
        with patch('blok.browser.request',side_effect=BrowserTaskError('Cancelled')) as request:
            with self.assertRaisesRegex(RuntimeError,'Cancelled'):
                self.backend.browser_task({'action':'site_search','query':'games','fallback':'google'})
        request.assert_called_once()

    def test_followup_is_rejected_before_laya_when_no_context_exists(self):
        self.backend.start_decisions=Mock()
        with patch('blok.browser.request',side_effect=RuntimeError('no browser')):
            self.backend.submit_decision('open the first result')
        self.backend.start_decisions.assert_not_called()
        self.assertTrue(any('No current search results' in call.kwargs.get('message','')
                            for call in self.backend.emit.call_args_list))




if __name__ == '__main__':
    unittest.main()
