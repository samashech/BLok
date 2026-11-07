from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent


class BrowserHostTests(unittest.TestCase):
    def test_host_allows_every_action_blok_sends(self):
        # The native host has its own list. An action missing from it fails only in the real browser.
        host = (ROOT / 'scripts/browser_host.py').read_text()
        allowed = set(re.findall(r"'(\w+)'", re.search(r"not in \{([^}]*)\}:raise ValueError\('Unsupported action'\)", host)[1]))
        sent = set()
        for path in (ROOT / 'blok').glob('*.py'):
            sent |= set(re.findall(r"""['"]action['"]\s*:\s*['"](\w+)['"]""", path.read_text()))
        web_only = {'click', 'fill', 'search', 'navigate', 'play', 'result', 'next_track', 'new_tab', 'sequence'}
        browser_sent = {a for a in sent if a in allowed or a in web_only or a == 'snapshot'}
        self.assertEqual(browser_sent - allowed, set())
        self.assertIn('snapshot', allowed)

    def test_host_allows_every_action_the_extension_handles(self):
        host = (ROOT / 'scripts/browser_host.py').read_text()
        allowed = set(re.findall(r"'(\w+)'", re.search(r"not in \{([^}]*)\}:raise ValueError\('Unsupported action'\)", host)[1]))
        extension = (ROOT / 'browser-extension/background.js').read_text()
        handled = set(re.findall(r"(?:task|req)\.action==='(\w+)'", extension))
        self.assertEqual(handled - allowed, set())


if __name__ == '__main__':
    unittest.main()
