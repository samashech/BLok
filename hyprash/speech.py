"""Reuse the user's Voxtype daemon/model with a per-recording output override."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import threading
import tomllib

class VoxtypeSession:
    def __init__(self):
        self.lock = threading.RLock()
        self.directory = None
        self.path = None
        self.owned = False
        config_path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'voxtype/config.toml'
        config = tomllib.loads(config_path.read_text())
        self.model = str(config.get('whisper', {}).get('model', 'base.en'))
        self.engine = config.get('engine', 'whisper')
        if self.engine == 'soniox' or config.get('whisper', {}).get('mode', 'local') == 'remote':
            raise RuntimeError('Hyprash requires local Voxtype recognition; this configuration uses a remote service.')
        state = config.get('state_file', 'auto')
        self.state_path = (Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'voxtype/state'
                           if state == 'auto' else Path(state).expanduser())

    def run(self, *args):
        result = subprocess.run(['voxtype', *args], capture_output=True, text=True, timeout=8)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:240] or 'Voxtype command failed')
        return result.stdout

    def state(self):
        try:
            return self.state_path.read_text().strip()
        except FileNotFoundError:
            return 'stopped'

    def start(self):
        status = json.loads(self.run('status', '--format', 'json', '--extended'))
        if status.get('class') != 'idle':
            raise RuntimeError('Voxtype is busy or stopped. Finish your F9 dictation first, or start Voxtype.')
        self.model = status.get('model', self.model)
        self.directory = tempfile.TemporaryDirectory(prefix='hyprash-voice-', dir=os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
        self.path = Path(self.directory.name)/'transcript.txt'
        try:
            self.run('record', 'start', '--file='+str(self.path), '--no-auto-submit', '--no-smart-auto-submit', '--no-osd')
            self.owned = True
            for _ in range(30):
                if self.state() == 'recording':
                    return
                time.sleep(.05)
            raise RuntimeError('Voxtype did not start recording')
        except Exception:
            self.cancel()
            raise

    def finish(self):
        if self.owned and self.state() == 'recording':
            self.run('record', 'stop')

    def cancel(self):
        with self.lock:
            if self.owned:
                self.run('record', 'cancel')
                for _ in range(60):
                    if self.state() in ('idle', 'stopped'):
                        self.owned = False
                        return
                    time.sleep(.05)
                raise RuntimeError('Voxtype has not confirmed cancellation')

    def close(self):
        with self.lock:
            self.cancel()
            if self.directory:
                self.directory.cleanup()
                self.directory = None
