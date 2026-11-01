"""The running BLoK app's side of MCP: a private socket that runs tool calls.

`blok mcp` (blok/mcp.py) talks MCP to an AI client and forwards each tool call
here, so AI-driven actions use exactly the same code, safety checks and
on-screen approval cards as voice commands. The AI client cannot approve
anything; only the user can, by voice, keyboard or click.
"""
import json
import os
from pathlib import Path
import socket
import threading

SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'blok.sock'

# Tool name → (BLoK action builder, needs the user's approval, short description for the card)
# Approval: anything that changes things, or hands your data (files, pages, screen) to the AI.
TOOLS = {
    'blok_command': ('command', True, 'run "{text}"'),
    'blok_status': ('status', False, ''),
    'windows_list': ('windows', False, ''),
    'window_focus': ('tool:window:focus', False, ''),
    'windows_arrange': ('tool:arrange', False, ''),
    'layouts_list': ('tool:layout_list', False, ''),
    'layout_save': ('tool:layout_save', False, ''),
    'layout_restore': ('tool:layout_restore', True, 'restore the "{name}" layout'),
    'focus_mode': ('tool:focus', False, ''),
    'files_find': ('tool:file_find', False, ''),
    'file_read': ('tool:file_read', True, 'read {query}'),
    'file_append': ('tool:file_append', True, 'add "{text}" to {query}'),
    'file_create': ('tool:file_create', True, 'create the file {name}'),
    'browser_open': ('url', False, ''),
    'web_search': ('search', False, ''),
    'page_read': ('tool:screen:page', True, 'read the page in front of you'),
    'screen_read': ('tool:screen:ocr', True, 'read the window in front of you'),
    'page_click': ('ui_click', True, 'click "{target}"'),
    'type_text': ('tool:type', True, 'type "{text}"'),
    'volume': ('tool:volume', False, ''),
    'brightness': ('tool:brightness', False, ''),
    'media': ('tool:media', False, ''),
    'say': ('say', False, ''),
}


class Bridge:
    """Socket server inside the backend. One thread per connection; calls may wait on approval."""

    def __init__(self, backend):
        self.backend = backend
        self.server = None

    def start(self):
        SOCKET.unlink(missing_ok=True)
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(str(SOCKET))
        os.chmod(SOCKET, 0o600)
        self.server.listen(4)
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self):
        if self.server:
            self.server.close()
            SOCKET.unlink(missing_ok=True)

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        with conn:
            try:
                request = json.loads(conn.makefile('rb').readline(1 << 20))
                result = {'ok': True, 'text': self.call(request.get('tool', ''), request.get('args') or {}, request.get('client', 'An AI app'))}
            except Exception as error:   # report every failure to the AI client as text
                result = {'ok': False, 'text': str(error)}
            try:
                conn.sendall(json.dumps(result).encode() + b'\n')
            except OSError:
                pass

    def call(self, name: str, args: dict, client: str) -> str:
        from blok import choreo, screen
        from blok.commands import Action
        backend = self.backend
        if name not in TOOLS:
            raise RuntimeError(f'Unknown tool {name}')
        kind, needs_approval, card = TOOLS[name]
        context = backend.worker_context
        context.generation = backend.generation   # "stop" cancels AI-driven plans like voice ones
        if needs_approval:
            backend.confirm(f'{client} wants to {card.format(**{k: str(v)[:80] for k, v in args.items()})}?',
                            action='mcp', value=name)
        context.pre_approved = needs_approval   # don't ask twice inside the same call
        try:
            if kind == 'status':
                active = choreo.active_workspace()
                window = screen.active_window()
                return json.dumps({'window': window.get('title'), 'app': window.get('class'),
                                   'workspace': active.get('name'), 'site': backend.context.active_site,
                                   'url': backend.context.active_url})
            if kind == 'windows':
                return json.dumps([{'app': c.get('class'), 'title': c.get('title'), 'workspace': c['workspace'].get('name')}
                                   for c in choreo.clients()])
            if kind == 'command':
                return backend.run_spoken(str(args.get('text', '')))
            if kind == 'say':
                text = str(args.get('text', ''))[:500]
                backend.speaker.say(text)
                return 'Said it.'
            if kind == 'url':
                url = str(args.get('url', ''))
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                return backend.run_action(Action('url', url))
            if kind == 'search':
                site = str(args.get('site') or 'google').lower()
                task = {'action': 'search', 'site': site if site in ('google', 'youtube', 'spotify') else 'google',
                        'query': str(args.get('query', ''))}
                return backend.run_action(Action('web_task', json.dumps(task)))
            if kind == 'ui_click':
                return backend.run_action(Action('ui_control', json.dumps({'action': 'click', 'target': str(args.get('target', ''))})))
            if kind.startswith('tool:screen:'):
                in_browser = kind.endswith('page')
                if in_browser and not backend.browser_in_front():
                    raise RuntimeError('No browser page is in front.')
                seen = screen.read_screen(in_browser, hide_overlay=backend.hide_overlay)
                return (seen.get('title', '') + '\n\n' + (seen.get('selection') or seen.get('text', '')))[:30000]
            tool = kind.split(':', 1)[1]
            if tool == 'window:focus':
                return backend.run_tool({'tool': 'window', 'op': 'focus', 'app': args.get('app', '')})
            if tool == 'file_read':
                from blok import files
                return files.read_text(backend.resolve_path(str(args.get('query', ''))), limit=30000)
            return backend.run_tool({'tool': tool, **args})
        finally:
            context.pre_approved = False
