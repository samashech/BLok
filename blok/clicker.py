"""Click where BLoK points, for apps and pages it can't reach any other way.

Hyprland can move the pointer but has no click dispatcher, so this uses ydotool. BLoK
runs its own ydotoold on a private socket with the keyboard side off: it can only
click, and it ends with BLoK, so no system service is left behind.
"""
import atexit
import ctypes
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

INSTALL_HINT = 'Clicking there needs ydotool. Install it with: sudo pacman -S ydotool'
_daemon = None


def available() -> bool:
    return bool(shutil.which('ydotool') and shutil.which('ydotoold'))


def _socket_path() -> Path:
    return Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'blok-ydotool.sock'


def _answers(path: Path) -> bool:
    """ydotool reports success even with no daemon, so check that one is really listening."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as probe:
            probe.connect(str(path))
        return True
    except OSError:
        return False


def _end_with_parent():
    ctypes.CDLL(None).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG: never outlive BLoK, even after a crash


def _start_daemon() -> Path:
    global _daemon
    path = _socket_path()
    if _daemon is not None and _daemon.poll() is None and _answers(path):
        return path
    stop()
    path.unlink(missing_ok=True)
    _daemon = subprocess.Popen(['ydotoold', f'--socket-path={path}', '--socket-perm=0600', '--keyboard-off'],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               preexec_fn=_end_with_parent)
    atexit.register(stop)
    for _ in range(30):
        if _daemon.poll() is not None:
            break
        if _answers(path):
            return path
        time.sleep(0.1)
    reason = _daemon.stderr.read().decode(errors='replace').strip()[:160] if _daemon.poll() is not None else 'it did not start'
    stop()
    raise RuntimeError(f'Could not start ydotoold: {reason or "it stopped"}. It needs access to /dev/uinput.')


def click():
    """Left-click at the pointer."""
    if not available():
        raise RuntimeError(INSTALL_HINT)
    path = _start_daemon()
    result = subprocess.run(['ydotool', 'click', '0xC0'], env={**os.environ, 'YDOTOOL_SOCKET': str(path)},
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError('The click failed: ' + (result.stderr.strip()[:160] or 'ydotool error'))


def stop():
    global _daemon
    process, _daemon = _daemon, None
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if process:
        _socket_path().unlink(missing_ok=True)
