"""Keep the speakers out of the microphone, so BLoK only hears people in the room.

BLoK records the mic, never system audio, but a video on the speakers reaches the
mic through the air and sounds like someone talking. PipeWire's WebRTC echo
canceller removes it, using what the speakers are playing as its reference.

It runs as BLoK's own small PipeWire client and ends with BLoK: no system audio
setting changes, and your default mic and speakers stay as they are. If it can't
start, BLoK uses the plain mic. BLOK_ECHO_CANCEL=0 turns it off.
"""
import atexit
import ctypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

SOURCE = 'blok.aec.source'
_process = None

CONFIG = """context.properties = { log.level = 1 }
context.spa-libs = { audio.convert.* = audioconvert/libspa-audioconvert  support.* = support/libspa-support }
context.modules = [
  { name = libpipewire-module-protocol-native }
  { name = libpipewire-module-client-node }
  { name = libpipewire-module-adapter }
  { name = libpipewire-module-echo-cancel
    args = {
      library.name = aec/libspa-aec-webrtc
      monitor.mode = true
      audio.channels = 1
      audio.position = [ MONO ]
      aec.args = { webrtc.gain_control = false  webrtc.noise_suppression = true  webrtc.extended_filter = true }
      capture.props = { node.name = "blok.aec.capture"  target.object = "%s"  node.dont-reconnect = true  node.passive = true }
      sink.props = { node.passive = true }
      source.props = { node.name = "%s"  node.description = "BLoK microphone (speakers removed)"  priority.session = 0  priority.driver = 0 }
    }
  }
]
"""


def active() -> bool:
    return _process is not None and _process.poll() is None


def _end_with_parent():
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG: never outlive BLoK, even after a crash


def _source_exists() -> bool:
    try:
        return f'node.name = "{SOURCE}"' in subprocess.run(['pw-cli', 'ls', 'Node'], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return False


def start(microphone: str) -> bool:
    """Start filtering this mic. Returns False (and the plain mic gets used) if that isn't possible."""
    global _process
    if active():
        return True
    if os.environ.get('BLOK_ECHO_CANCEL') == '0' or not microphone or not shutil.which('pipewire') or not shutil.which('pw-cli'):
        return False
    config = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'blok-echo.conf'
    config.write_text(CONFIG % (microphone, SOURCE))
    _process = subprocess.Popen(['pipewire', '-c', str(config)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, preexec_fn=_end_with_parent)
    atexit.register(stop)
    for _ in range(30):
        if not active():
            break
        if _source_exists():
            return True
        time.sleep(0.1)
    stop()
    return False


def stop():
    global _process
    process, _process = _process, None
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
