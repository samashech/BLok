"""`blok mcp`: an MCP server (stdio, JSON-RPC 2.0) that lets AI apps use BLoK.

Add it to Claude Code with `claude mcp add blok -- blok mcp`, or to any MCP
client as the command `blok mcp`. Each tool call is forwarded to the running
BLoK app, which applies the same safety rules as voice: actions that change
things or hand your data to the AI show an approval card on your screen, and
only you can approve them.
"""
import json
import socket
import sys
import threading

from blok.mcp_bridge import SOCKET

PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
APPROVAL = ' Shows an approval card on the user\'s screen first; only the user can approve.'


def _tool(name, description, properties=None, required=(), read_only=False, destructive=False, approval=False):
    return {'name': name, 'description': description + (APPROVAL if approval else ''),
            'inputSchema': {'type': 'object', 'properties': properties or {}, 'required': list(required)},
            'annotations': {'readOnlyHint': read_only, 'destructiveHint': destructive, 'openWorldHint': False}}


S = lambda description: {'type': 'string', 'description': description}
TOOLS = [
    _tool('blok_command', 'Give BLoK a plain-English (or Hinglish) desktop command, exactly as a person would say it, '
          'e.g. "open youtube and search for lofi", "code on the left, browser on the right". Returns what BLoK did.',
          {'text': S('The command')}, ['text'], approval=True),
    _tool('blok_status', 'What is in front of the user: focused app, window title, workspace, and the current site/URL.', read_only=True),
    _tool('windows_list', 'List open windows with app, title and workspace.', read_only=True),
    _tool('window_focus', 'Bring an open app to the front.', {'app': S('App name, e.g. "terminal", "code", "spotify"')}, ['app']),
    _tool('windows_arrange', 'Put two open apps side by side on a free workspace.',
          {'left': S('App on the left'), 'right': S('App on the right')}, ['left', 'right']),
    _tool('layouts_list', 'List saved window layouts.', read_only=True),
    _tool('layout_save', 'Save the current windows as a named layout.', {'name': S('Layout name')}, ['name']),
    _tool('layout_restore', 'Restore a saved layout, reopening closed apps.', {'name': S('Layout name')}, ['name'], approval=True),
    _tool('focus_mode', 'Turn focus mode on (silence notifications, hide chat apps) or off.',
          {'on': {'type': 'boolean'}, 'minutes': {'type': 'integer', 'description': 'Optional timer'}}, ['on']),
    _tool('files_find', 'Find files in the user\'s home folder by a description, e.g. "resume pdf". Returns matching paths.',
          {'query': S('What to look for')}, ['query'], read_only=True),
    _tool('file_read', 'Read a text or PDF file from the user\'s home folder.', {'query': S('Path or description')}, ['query'],
          read_only=True, approval=True),
    _tool('file_append', 'Add a line of text to a text file in the home folder.',
          {'query': S('Path or description of the file'), 'text': S('Text to add')}, ['query', 'text'], approval=True),
    _tool('file_create', 'Create a new text file (never overwrites).',
          {'name': S('File name'), 'content': S('Initial text'), 'folder': S('Folder, e.g. "documents"')}, ['name'], approval=True),
    _tool('browser_open', 'Open a website in the user\'s browser.', {'url': S('URL or domain')}, ['url']),
    _tool('web_search', 'Search Google, YouTube or Spotify in the user\'s browser.',
          {'query': S('Search text'), 'site': {'type': 'string', 'enum': ['google', 'youtube', 'spotify']}}, ['query']),
    _tool('page_read', 'Read the main text (or selection) of the browser page in front of the user.', read_only=True, approval=True),
    _tool('screen_read', 'Read the text of the focused window with OCR.', read_only=True, approval=True),
    _tool('page_click', 'Click a button or link by its visible label on the page or app in front.',
          {'target': S('Visible label, optionally with a color: "blue Download"')}, ['target'], approval=True),
    _tool('type_text', 'Type text into the focused field.', {'text': S('Text to type')}, ['text'], approval=True),
    _tool('volume', 'Change the volume.', {'op': {'type': 'string', 'enum': ['up', 'down', 'mute', 'set']},
                                           'level': {'type': 'integer', 'minimum': 0, 'maximum': 100}}, ['op']),
    _tool('brightness', 'Change screen brightness.', {'op': {'type': 'string', 'enum': ['up', 'down', 'set']},
                                                      'level': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, ['op']),
    _tool('media', 'Control music/video playback.', {'op': {'type': 'string', 'enum': ['toggle', 'next', 'previous']}}, ['op']),
    _tool('say', 'Say something out loud to the user with BLoK\'s voice.', {'text': S('Up to 500 characters')}, ['text']),
]


def forward(name: str, args: dict, client: str, timeout: float = 180) -> tuple[bool, str]:
    """Send one tool call to the running BLoK app and wait (approvals can take a while)."""
    try:
        with socket.socket(socket.AF_UNIX) as conn:
            conn.settimeout(timeout)
            conn.connect(str(SOCKET))
            conn.sendall(json.dumps({'tool': name, 'args': args, 'client': client}).encode() + b'\n')
            reply = json.loads(conn.makefile('rb').readline(1 << 22))
        return bool(reply.get('ok')), str(reply.get('text', ''))
    except (OSError, ValueError):
        return False, 'BLoK is not running. Ask the user to start it (run `blok`), then try again.'


class Server:
    def __init__(self, stdin=sys.stdin, stdout=sys.stdout):
        self.stdin, self.stdout = stdin, stdout
        self.lock = threading.Lock()
        self.client = 'An AI app'

    def send(self, message: dict):
        with self.lock:
            self.stdout.write(json.dumps(message) + '\n')
            self.stdout.flush()

    def reply(self, ident, result=None, error=None):
        message = {'jsonrpc': '2.0', 'id': ident}
        message.update({'error': error} if error else {'result': result})
        self.send(message)

    def handle(self, message: dict):
        method, ident, params = message.get('method'), message.get('id'), message.get('params') or {}
        if method == 'initialize':
            info = params.get('clientInfo') or {}
            self.client = info.get('name') or self.client
            wanted = params.get('protocolVersion')
            self.reply(ident, {'protocolVersion': wanted if wanted in PROTOCOLS else PROTOCOLS[0],
                               'capabilities': {'tools': {'listChanged': False}},
                               'serverInfo': {'name': 'blok', 'title': 'BLoK', 'version': '0.10'},
                               'instructions': 'BLoK controls the user\'s Hyprland desktop. Prefer blok_command for '
                                               'anything a person could say. Approval cards appear on the user\'s screen; '
                                               'wait for them rather than retrying.'})
        elif method == 'ping':
            self.reply(ident, {})
        elif method == 'tools/list':
            self.reply(ident, {'tools': TOOLS})
        elif method == 'tools/call':
            name, args = params.get('name', ''), params.get('arguments') or {}
            if name not in {t['name'] for t in TOOLS}:
                self.reply(ident, error={'code': -32602, 'message': f'Unknown tool: {name}'})
                return
            # Calls may wait on an approval card, so each runs in its own thread.
            def run():
                ok, text = forward(name, args, self.client)
                self.reply(ident, {'content': [{'type': 'text', 'text': text}], 'isError': not ok})
            threading.Thread(target=run, daemon=True).start()
        elif ident is not None and method:
            self.reply(ident, error={'code': -32601, 'message': f'Method not found: {method}'})
        # Notifications (no id), e.g. notifications/initialized, need no reply.

    def serve(self):
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self.send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}})
                continue
            self.handle(message)


if __name__ == '__main__':
    Server().serve()
