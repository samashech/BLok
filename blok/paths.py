"""Where BLoK keeps things. By default everything lives in the checkout; a packaged
install (code in /opt/blok) sets BLOK_HOME so models, the Python environment and
your data live in ~/.local/share/blok instead."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get('BLOK_HOME') or ROOT).expanduser()
MODELS = HOME / 'models'
DATA = Path(os.environ.get('BLOK_DATA') or HOME / 'data').expanduser()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'blok'
