import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from blok import mcp, mcp_bridge
from blok.backend import Backend


class ProtocolTests(unittest.TestCase):
    def talk(self, *messages, forward=None):
        out = io.StringIO()
        server = mcp.Server(stdin=io.StringIO('\n'.join(json.dumps(m) for m in messages) + '\n'), stdout=out)
        with patch.object(mcp, 'forward', forward or (lambda name, args, client: (True, f'{client} ran {name} {args}'))):
            server.serve()
            time.sleep(0.2)             # tool calls answer from their own threads
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_handshake_and_tools(self):
        replies = self.talk({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                             'params': {'protocolVersion': '2025-03-26', 'clientInfo': {'name': 'Claude Code'}}},
                            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        self.assertEqual(len(replies), 2)                       # the notification gets no reply
        self.assertEqual(replies[0]['result']['protocolVersion'], '2025-03-26')
        tools = {t['name']: t for t in replies[1]['result']['tools']}
        self.assertEqual(set(tools), set(mcp_bridge.TOOLS))
        self.assertIn('approval card', tools['file_append']['description'])
        self.assertTrue(tools['windows_list']['annotations']['readOnlyHint'])

    def test_call_is_forwarded_with_the_client_name(self):
        replies = self.talk({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'Claude Code'}}},
                            {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'volume', 'arguments': {'op': 'up'}}})
        result = next(r for r in replies if r['id'] == 7)['result']
        self.assertEqual(result, {'content': [{'type': 'text', 'text': "Claude Code ran volume {'op': 'up'}"}], 'isError': False})

    def test_errors(self):
        replies = self.talk({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'rm_rf'}},
                            {'jsonrpc': '2.0', 'id': 2, 'method': 'resources/list'})
        self.assertEqual([r['error']['code'] for r in replies], [-32602, -32601])

    def test_blok_not_running(self):
        with patch.object(mcp, 'SOCKET', Path('/nonexistent/blok.sock')):
            ok, text = mcp.forward('volume', {'op': 'up'}, 'x')
        self.assertFalse(ok)
        self.assertIn('not running', text)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        sock = Path(self.temp.name) / 'blok.sock'
        for module in (mcp, mcp_bridge):
            p = patch.object(module, 'SOCKET', sock); p.start(); self.addCleanup(p.stop)
        self.backend = Backend()
        p = patch('builtins.print'); p.start(); self.addCleanup(p.stop)   # real emit (captures results), no output
        self.bridge = mcp_bridge.Bridge(self.backend)
        self.bridge.start()
        self.addCleanup(self.bridge.stop)

    def test_safe_tool_runs_without_approval(self):
        self.backend.request_approval = Mock()
        with patch('blok.system.volume', return_value='Volume 55%') as volume:
            ok, text = mcp.forward('volume', {'op': 'up'}, 'Claude Code')
        self.assertEqual((ok, text), (True, 'Volume 55%'))
        volume.assert_called_once_with('up', None)
        self.backend.request_approval.assert_not_called()

    def test_writes_wait_for_the_user_and_rejection_does_nothing(self):
        self.backend.request_approval = Mock(return_value=False)
        with patch('blok.files.append_text') as append:
            ok, text = mcp.forward('file_append', {'query': 'todo', 'text': 'buy milk'}, 'Claude Code')
        self.assertFalse(ok)
        self.assertIn('rejected', text)
        append.assert_not_called()
        self.assertEqual(self.backend.request_approval.call_args[0][0], 'Claude Code wants to add "buy milk" to todo?')

    def test_approved_call_is_not_asked_twice(self):
        self.backend.request_approval = Mock(return_value=True)
        with patch.object(Backend, 'resolve_path', return_value=Path('/home/x/report.pdf')), \
             patch('blok.files.trash', return_value='Moved ~/report.pdf to the trash'):
            ok, text = mcp.forward('blok_command', {'text': 'delete report.pdf'}, 'Claude Code')
        self.assertTrue(ok, text)
        self.assertEqual(self.backend.request_approval.call_count, 1)   # the command card only
        self.assertIn('trash', text)


if __name__ == '__main__':
    unittest.main()
