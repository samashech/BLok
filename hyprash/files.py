"""Home-folder file tools: locate, open, read, append, create, rename, move, copy, trash.

Every path is confined to the user's home directory. Writes never touch hidden
directories, never overwrite an existing file, and deletion goes to the trash.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HOME = Path(os.environ.get('HYPRASH_HOME', Path.home())).resolve()
TEXT_SUFFIXES = {'.txt', '.md', '.markdown', '.org', '.csv', '.log', '.json', '.yaml', '.yml', '.toml',
                 '.ini', '.conf', '.py', '.js', '.ts', '.sh', '.lua', '.html', '.css', '.rst', ''}
KIND_SUFFIXES = {
    'pdf': ['pdf'], 'pdfs': ['pdf'],
    'image': ['png', 'jpg', 'jpeg', 'webp', 'gif'], 'images': ['png', 'jpg', 'jpeg', 'webp', 'gif'],
    'photo': ['png', 'jpg', 'jpeg', 'webp', 'heic'], 'photos': ['png', 'jpg', 'jpeg', 'webp', 'heic'],
    'picture': ['png', 'jpg', 'jpeg', 'webp'], 'screenshot': ['png', 'jpg', 'jpeg', 'webp'],
    'video': ['mp4', 'mkv', 'webm', 'mov', 'avi'], 'movie': ['mp4', 'mkv', 'webm', 'mov', 'avi'],
    'song': ['mp3', 'flac', 'ogg', 'm4a', 'wav'], 'audio': ['mp3', 'flac', 'ogg', 'm4a', 'wav'],
    'document': ['pdf', 'doc', 'docx', 'odt', 'txt', 'md'], 'doc': ['doc', 'docx', 'odt'],
    'spreadsheet': ['xls', 'xlsx', 'ods', 'csv'], 'presentation': ['ppt', 'pptx', 'odp'],
    'zip': ['zip', 'tar', 'gz', 'xz', '7z', 'rar'], 'archive': ['zip', 'tar', 'gz', 'xz', '7z', 'rar'],
    'text': ['txt', 'md'], 'markdown': ['md'], 'python': ['py'], 'script': ['sh', 'py', 'js'],
}
FILLER = {'my', 'the', 'a', 'an', 'file', 'files', 'called', 'named', 'titled', 'that', 'is', 'in', 'of',
          'from', 'this', 'some', 'please', 'one', 'thing', 'stuff', 'for', 'me', 'all', 'with', 'name', 'on'}
RECENT = {'yesterday', 'today', 'latest', 'newest', 'recent', 'last', 'new', 'just', 'downloaded', 'saved', 'took'}
EXCLUDES = ['node_modules', '.git', '__pycache__', '.venv', 'venv', 'site-packages', '.cache', 'Trash',
            'dist', 'build', '.npm', '.cargo', 'go/pkg', 'huggingface', 'snap']


class FileError(RuntimeError):
    pass


def user_dirs() -> dict[str, Path]:
    """Spoken folder names mapped to the XDG folders that exist on this machine."""
    found = {'home': HOME, 'home folder': HOME}
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'user-dirs.dirs'
    try:
        for line in config.read_text().splitlines():
            m = re.fullmatch(r'XDG_([A-Z]+)_DIR="(.+)"', line.strip())
            if m:
                path = Path(m[2].replace('$HOME', str(HOME))).resolve()
                if path != HOME and path.is_dir():
                    found[m[1].lower()] = path
    except OSError:
        pass
    for name in ('Downloads', 'Documents', 'Pictures', 'Music', 'Videos', 'Desktop', 'Projects'):
        if (HOME / name).is_dir():
            found.setdefault(name.lower().rstrip('s') if name == 'Downloads' else name.lower(), HOME / name)
    aliases = {'downloads': 'download', 'document': 'documents', 'picture': 'pictures', 'photos': 'pictures',
               'video': 'videos', 'project': 'projects'}
    for alias, key in aliases.items():
        if key in found:
            found.setdefault(alias, found[key])
    return found


def display(path: Path) -> str:
    try:
        return '~/' + str(path.resolve().relative_to(HOME)) if path.resolve() != HOME else '~'
    except ValueError:
        return str(path)


def inside_home(path: Path, writable=False) -> Path:
    path = path.expanduser()
    resolved = (path if path.is_absolute() else HOME / path).resolve()
    if resolved != HOME and HOME not in resolved.parents:
        raise FileError('Hyprash only works with files inside your home folder.')
    if writable:
        parts = resolved.relative_to(HOME).parts
        if any(part.startswith('.') for part in parts):
            raise FileError('Hyprash does not change hidden files or folders.')
    return resolved


def parse_query(query: str) -> tuple[list[str], list[str], str | None]:
    """Spoken file description → (name words, extensions, 'f'/'d'/None)."""
    q = query.lower().strip(' .?!"\'')
    q = re.sub(r'\s+dot\s+([a-z0-9]{1,5})\b', r'.\1', q)
    kind = None
    if re.search(r'\b(?:folder|folders|directory|directories)\b', q):
        kind = 'd'
        q = re.sub(r'\b(?:folder|folders|directory|directories)\b', ' ', q)
    extensions: list[str] = []
    m = re.search(r'\.([a-z0-9]{1,5})$', q)
    words = []
    for word in re.findall(r"[\w.+-]+", q):
        if word in KIND_SUFFIXES and kind is None:
            extensions += KIND_SUFFIXES[word]
            kind = 'f'
            if word.startswith('screenshot'):
                words.append('screenshot')
        elif word not in FILLER and word not in RECENT:
            words.append(word)
    if m and not extensions:
        kind = 'f'
    return words, extensions, kind


def find(query: str, kind: str | None = None, limit: int = 8, roots: list[Path] | None = None) -> list[Path]:
    """Ranked matches for a spoken description; known folders resolve directly."""
    q = query.lower().strip(' .?!')
    dirs = user_dirs()
    folder = re.sub(r'\s+(?:folder|directory)$', '', re.sub(r'^(?:my|the)\s+', '', q))
    if folder in dirs and kind != 'f':
        return [dirs[folder]]
    if q.startswith(('~/', '/')):
        path = inside_home(Path(q))
        return [path] if path.exists() else []
    words, extensions, spoken_kind = parse_query(query)
    recent = bool(RECENT & set(re.findall(r'\w+', q)))
    kind = kind or spoken_kind
    if not words and not extensions:
        return []
    # A folder named in the description narrows the search ("resume in downloads").
    search_roots = roots or [HOME]
    for i, word in enumerate(words):
        if word in dirs and len(words) > 1 and roots is None:
            search_roots = [dirs[word]]
            words = words[:i] + words[i + 1:]
            break
    pattern = max(words, key=len) if words else '.'
    args = ['fd', '--ignore-case', '--max-results', '400', '--max-depth', '8', '--absolute-path']
    for exclude in EXCLUDES:
        args += ['--exclude', exclude]
    if kind:
        args += ['--type', kind]
    for ext in extensions:
        args += ['--extension', ext]
    args += ['--fixed-strings', pattern.split('.')[0] if '.' in pattern and not extensions else pattern]
    args += [str(r) for r in search_roots]
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=6).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise FileError('File search failed: ' + str(error)) from error
    scored = []
    for line in out.splitlines():
        path = Path(line.rstrip('/'))
        name = path.name.lower()
        stem = path.stem.lower() if path.is_file() else name
        rel = str(path).lower()
        if not all(w in rel for w in words):
            continue
        score = sum(3 for w in words if w in name) + (6 if stem == ' '.join(words) or stem.replace('_', ' ').replace('-', ' ') == ' '.join(words) else 0)
        score -= len(path.parts) * 0.1
        try:
            age = (time.time() - path.stat().st_mtime) / 86400
            # "latest"/"yesterday" make recency the main ranking signal.
            score += max(0.0, 1.0 - age / 365) + (max(0.0, 10.0 - age) if recent else 0.0)
        except OSError:
            continue
        scored.append((score, path))
    scored.sort(key=lambda item: -item[0])
    return [path for _, path in scored[:limit]]


def clear_winner(paths: list[Path], query: str) -> Path | None:
    """One result, or one whose name equals the spoken description."""
    if len(paths) == 1:
        return paths[0]
    if paths and RECENT & set(re.findall(r'\w+', query.lower())):
        return max(paths, key=lambda p: p.stat().st_mtime)
    words, _, _ = parse_query(query)
    spoken = ' '.join(words)
    exact = [p for p in paths if re.sub(r'[_-]+', ' ', (p.stem if p.is_file() else p.name).lower()) == spoken
             or p.name.lower() == spoken]
    exact.sort(key=lambda p: len(p.parts))
    if len(exact) == 1 or (len(exact) > 1 and len(exact[0].parts) < len(exact[1].parts)):
        return exact[0]
    return None


def open_path(path: Path) -> str:
    path = inside_home(path)
    if not path.exists():
        raise FileError(display(path) + ' does not exist.')
    subprocess.Popen(['xdg-open', str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return 'Opened ' + display(path)


def list_folder(path: Path, limit: int = 12) -> str:
    path = inside_home(path)
    entries = sorted((p for p in path.iterdir() if not p.name.startswith('.')),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    names = [p.name + ('/' if p.is_dir() else '') for p in entries[:limit]]
    more = f' (+{len(entries) - limit} more)' if len(entries) > limit else ''
    return f'{display(path)}: ' + (', '.join(names) if names else 'empty') + more


def read_text(path: Path, limit: int = 1200) -> str:
    path = inside_home(path)
    if path.is_dir():
        return list_folder(path)
    if path.suffix.lower() == '.pdf':
        try:
            out = subprocess.run(['pdftotext', '-l', '2', str(path), '-'], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise FileError('Could not read that PDF: ' + str(error)) from error
        text = out
    elif path.suffix.lower() in TEXT_SUFFIXES:
        if path.stat().st_size > 2_000_000:
            raise FileError('That file is too large to read aloud. Say "open" instead.')
        text = path.read_text(errors='replace')
    else:
        raise FileError(f'{display(path)} is not a text file. Say "open {path.name}" instead.')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit] + ('…' if len(text) > limit else '') if text else '(empty file)'


def append_text(path: Path, text: str) -> str:
    path = inside_home(path, writable=True)
    if not path.is_file():
        raise FileError(display(path) + ' is not a file.')
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise FileError('Hyprash only adds text to plain text files (.txt, .md, …).')
    existing = path.read_bytes()
    prefix = b'' if not existing or existing.endswith(b'\n') else b'\n'
    with path.open('ab') as handle:
        handle.write(prefix + text.encode() + b'\n')
    if text not in path.read_text(errors='replace'):
        raise FileError('The text was not saved.')
    return f'Added "{text}" to {display(path)}'


def create_file(name: str, folder: Path | None = None, content: str = '') -> Path:
    name = name.strip(' ."\'')
    if not name or '/' in name or name in ('.', '..'):
        raise FileError('Use a simple file name without slashes.')
    if not Path(name).suffix:
        name += '.txt'
    folder = folder or user_dirs().get('documents', HOME)
    path = inside_home(folder / name, writable=True)
    if path.exists():
        raise FileError(display(path) + ' already exists. Choose another name.')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + ('\n' if content else ''))
    return path


def rename(path: Path, new_name: str) -> str:
    path = inside_home(path, writable=True)
    new_name = new_name.strip(' ."\'')
    if not new_name or '/' in new_name:
        raise FileError('Use a simple new name without slashes.')
    if path.is_file() and not Path(new_name).suffix:
        new_name += path.suffix
    target = inside_home(path.with_name(new_name), writable=True)
    if target.exists():
        raise FileError(display(target) + ' already exists. Nothing was renamed.')
    path.rename(target)
    return f'Renamed {display(path)} to {target.name}'


def move(path: Path, folder: Path, copy: bool = False) -> str:
    path = inside_home(path, writable=not copy)
    folder = inside_home(folder, writable=True)
    if not folder.is_dir():
        raise FileError(display(folder) + ' is not a folder.')
    target = folder / path.name
    if target.exists():
        raise FileError(display(target) + ' already exists. Nothing was ' + ('copied.' if copy else 'moved.'))
    if copy:
        (shutil.copytree if path.is_dir() else shutil.copy2)(path, target)
    else:
        shutil.move(str(path), str(target))
    return ('Copied ' if copy else 'Moved ') + f'{path.name} to {display(folder)}'


def trash(path: Path) -> str:
    path = inside_home(path, writable=True)
    if path == HOME or path in user_dirs().values():
        raise FileError('Hyprash will not trash your main folders.')
    result = subprocess.run(['gio', 'trash', str(path)], capture_output=True, text=True, timeout=10)
    if result.returncode or path.exists():
        raise FileError('Could not move it to the trash: ' + (result.stderr.strip()[:150] or 'unknown error'))
    return f'Moved {display(path)} to the trash'
