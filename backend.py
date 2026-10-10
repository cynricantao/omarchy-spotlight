#!/usr/bin/env python3
"""Native Spotlight backend. JSON only; no shell execution or query history."""
import ast
import configparser
from contextlib import contextmanager
import fcntl
import json
import math
import operator
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import sys
import subprocess
import tempfile
import time
from urllib.parse import urlencode
import safe_storage

MAX_ITEMS = 24
PRUNED_DIRS = {'node_modules', 'venv', 'env', '__pycache__', 'cache', 'caches',
               'build', 'dist', 'target', 'vendor', 'deps', 'site-packages'}


def item(kind, title, subtitle, value, icon='', identifier=None):
    return {'id': identifier or kind + ':' + value, 'kind': kind, 'title': title,
            'subtitle': subtitle, 'icon': icon, 'value': value}


def quick_actions():
    return [item('action', 'Open home folder', 'File manager', 'home', 'user-home'),
            item('action', 'Desktop settings', 'Open Omarchy setup', 'settings', 'preferences-system'),
            item('action', 'Take a screenshot', 'Select a region and copy', 'screenshot', 'camera-photo')]


FUNCTIONS = {name: getattr(math, name) for name in
             ('sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'log', 'log10',
              'exp', 'floor', 'ceil', 'degrees', 'radians')}
FUNCTIONS.update(abs=abs, round=round)
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
             ast.Mod: operator.mod, ast.Pow: operator.pow}


def calculate(expression):
    """Interpret a tiny numeric AST; never compile/eval user input."""
    if not expression.strip() or len(expression) > 256:
        raise ValueError('Enter an expression of at most 256 characters')
    tree = ast.parse(expression.strip(), mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 96:
        raise ValueError('Expression is too complex')

    def checked(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError('Result must be finite and at most 1e100')
        return value

    def visit(node, depth=0):
        if depth > 24:
            raise ValueError('Expression is too deeply nested')
        if isinstance(node, ast.Constant):
            return checked(node.value)
        if isinstance(node, ast.Name) and node.id in ('pi', 'e'):
            return getattr(math, node.id)
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            value = visit(node.operand, depth + 1)
            return checked(value if isinstance(node.op, ast.UAdd) else -value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Pow):
                if abs(right) > 1000:
                    raise ValueError('Exponent exceeds 1000')
                if left and abs(left) != 1 and right * math.log10(abs(left)) > 100:
                    raise ValueError('Power result is too large')
            return checked(OPERATORS[type(node.op)](left, right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name not in FUNCTIONS or node.keywords or not 1 <= len(node.args) <= 2:
                raise ValueError('Unsupported function or arguments')
            args = [visit(arg, depth + 1) for arg in node.args]
            if name == 'round' and len(args) == 2:
                if type(args[1]) is not int or abs(args[1]) > 15:
                    raise ValueError('Rounding precision must be an integer from -15 to 15')
            return checked(FUNCTIONS[name](*args))
        raise ValueError('Only numeric expressions and supported math functions are allowed')

    result = checked(visit(tree.body))
    if result == 0:
        return '0'
    return str(result) if type(result) is int else format(result, '.12g')


def apps(search='', limit=MAX_ITEMS):
    """Read desktop metadata only; gio, not this parser, interprets Exec."""
    data_home = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local/share')
    bases = [data_home] + (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')
    desktops = set((os.environ.get('XDG_CURRENT_DESKTOP') or 'Hyprland').split(':'))
    seen, found = set(), []
    words = search.casefold().split()
    for base in bases:
        if not Path(base).is_absolute():
            continue
        directory = Path(base) / 'applications'
        for current, dirs, files in os.walk(directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for name in sorted(files):
                if not name.endswith('.desktop') or name.startswith('.'):
                    continue
                path = Path(current) / name
                desktop_id = str(path.relative_to(directory)).replace('/', '-')
                if desktop_id in seen:
                    continue
                seen.add(desktop_id)  # Hidden overrides mask lower-priority entries.
                try:
                    if path.stat().st_size > 131072:
                        continue
                    parser = configparser.ConfigParser(interpolation=None, strict=False)
                    parser.optionxform = str
                    parser.read_string(path.read_text(encoding='utf-8'))
                    entry = parser['Desktop Entry']
                    if entry.get('Type') != 'Application' or not entry.get('Name'):
                        continue
                    if any(entry.get(key, '').lower() == 'true' for key in ('Hidden', 'NoDisplay')):
                        continue
                    only = set(filter(None, entry.get('OnlyShowIn', '').split(';')))
                    excluded = set(filter(None, entry.get('NotShowIn', '').split(';')))
                    if (only and not desktops & only) or desktops & excluded:
                        continue
                    if entry.get('TryExec') and not shutil.which(entry['TryExec']):
                        continue
                    if not entry.get('Exec') and entry.get('DBusActivatable', '').lower() != 'true':
                        continue
                    title = entry['Name']
                    haystack = ' '.join(entry.get(key, '') for key in
                                        ('Name', 'GenericName', 'Comment', 'Keywords')).casefold()
                    if not all(word in haystack for word in words):
                        continue
                    found.append(item('app', title, entry.get('Comment') or 'Application',
                                      str(path), entry.get('Icon', 'application-x-executable'),
                                      'app:' + desktop_id))
                except (OSError, UnicodeError, configparser.Error, KeyError):
                    continue
    found.sort(key=lambda x: (x['title'].casefold() != search.casefold(),
                             not x['title'].casefold().startswith(search.casefold()),
                             x['title'].casefold(), x['id']))
    return found[:limit]


def discover_roots(home=None, media_base=None, mountinfo=None):
    """HOME plus actual current mounts below /run/media/<current user>."""
    home = Path.home() if home is None else Path(home)
    media_base = (Path('/run/media') / pwd.getpwuid(os.getuid()).pw_name
                  if media_base is None else Path(media_base))
    if mountinfo is None:
        try:
            mountinfo = Path('/proc/self/mountinfo').read_text()
        except OSError:
            mountinfo = ''
    roots = [home]
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        mount = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4]))
        try:
            relative = mount.relative_to(media_base)
            if not relative.parts or any(p.startswith('.') for p in relative.parts):
                continue
            if any(parent.is_symlink() for parent in (mount, *mount.parents)):
                continue
            if mount.is_dir() and not any(mount.is_relative_to(root) for root in roots):
                roots.append(mount)
        except (OSError, ValueError):
            continue
    return roots


def cache_dir():
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'omarchy-spotlight'


def index_connection():
    directory = safe_storage.require_directory(cache_dir(), private=True)
    path = directory / 'index.sqlite3'
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        safe_storage.validate_fd(descriptor, private=True)
    finally:
        os.close(descriptor)
    connection = sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True, timeout=0.2)
    connection.execute('PRAGMA query_only=ON')
    return connection


def index_metadata():
    connection = index_connection()
    try:
        return {key: json.loads(value) for key, value in connection.execute('SELECT key,value FROM metadata')}
    finally:
        connection.close()


def build_index(roots=None, force=False, max_rows=250000, max_seconds=15):
    """Index names only; atomically publish a private database."""
    roots = discover_roots() if roots is None else [Path(p).absolute() for p in roots]
    directory = safe_storage.require_directory(cache_dir(), create=True, private=True)
    lock_fd = os.open(directory / 'index.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'a') as lock:
        safe_storage.validate_fd(lock.fileno(), private=True)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                retained = index_metadata()
            except (OSError, sqlite3.Error, ValueError):
                retained = {}
            return {'ok': True, 'status': 'busy', 'error': '', **retained}
        try:
            metadata = index_metadata()
            if (not force and 0 <= time.time() - metadata['built_at'] < 900
                    and metadata['roots'] == [str(root) for root in roots]):
                return {'ok': True, 'status': 'fresh', 'error': '', **metadata}
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            pass
        return _build_locked(roots, directory, max_rows, max_seconds)


@contextmanager
def scandir_nofollow(path):
    """Open each directory component without following symlinks, even on races."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    try:
        for component in Path(path).absolute().parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        with os.scandir(descriptor) as entries:
            yield entries
    finally:
        os.close(descriptor)


def _build_locked(roots, directory, max_rows, max_seconds):
    fd, temporary = tempfile.mkstemp(prefix='.index-', suffix='.sqlite3', dir=directory)
    os.close(fd)
    connection = sqlite3.connect(temporary)
    count = 0
    truncated = False
    deadline = time.monotonic() + max_seconds
    try:
        connection.execute('CREATE TABLE files(path TEXT PRIMARY KEY, name TEXT, folded TEXT, is_dir INTEGER)')
        connection.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)')
        stack = [root for root in roots if root.is_dir() and not root.is_symlink()]
        while stack:
            if count >= max_rows or time.monotonic() >= deadline:
                truncated = True
                break
            current = stack.pop()
            try:
                with scandir_nofollow(current) as entries:
                    for entry in entries:
                        if count >= max_rows or time.monotonic() >= deadline:
                            truncated = True
                            break
                        if entry.name.startswith('.') or entry.is_symlink():
                            continue
                        is_dir = entry.is_dir(follow_symlinks=False)
                        if is_dir and entry.name.casefold() in PRUNED_DIRS:
                            continue
                        if not is_dir and not entry.is_file(follow_symlinks=False):
                            continue
                        full_path = str(current / entry.name)
                        cursor = connection.execute('INSERT OR IGNORE INTO files VALUES(?,?,?,?)',
                                                    (full_path, entry.name, entry.name.casefold(), int(is_dir)))
                        count += cursor.rowcount
                        if is_dir:
                            stack.append(Path(full_path))
            except (OSError, UnicodeError):
                continue
            if truncated:
                break
        metadata = {'built_at': time.time(), 'count': count, 'truncated': truncated,
                    'roots': [str(root) for root in roots]}
        connection.executemany('INSERT INTO metadata VALUES(?,?)',
                               [(key, json.dumps(value)) for key, value in metadata.items()])
        connection.commit()
    finally:
        connection.close()
    with open(temporary, 'rb') as published:
        os.fsync(published.fileno())
    os.replace(temporary, directory / 'index.sqlite3')
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {'ok': True, 'status': 'truncated' if truncated else 'indexed', 'error': '', **metadata}


def file_results(search, limit=MAX_ITEMS):
    try:
        connection = index_connection()
        try:
            words = search.casefold().split()
            if len(words) > 16:
                return [], 'Use at most 16 filename search terms'
            where = ' AND '.join('instr(folded, ?) > 0' for _ in words) or '1'
            sql = ('SELECT path,name,is_dir FROM files WHERE ' + where +
                   ' ORDER BY folded != ?, instr(folded, ?) != 1, length(name), folded, path LIMIT ?')
            rows = connection.execute(sql, [*words, search.casefold(), search.casefold(), limit]).fetchall()
            metadata = {key: json.loads(value) for key, value in connection.execute('SELECT key,value FROM metadata')}
        finally:
            connection.close()
        status = 'File index: ' + str(metadata['count']) + ' names'
        if metadata.get('truncated'):
            status += ' · truncated (scan budget reached)'
        if not 0 <= time.time() - metadata['built_at'] < 900:
            status += ' · stale; refreshing on next open'
        return [item('folder' if directory else 'file', name, path, path,
                     'folder' if directory else 'text-x-generic')
                for path, name, directory in rows], status
    except (OSError, sqlite3.Error, ValueError, KeyError):
        return [], 'File index unavailable; open Spotlight to refresh'


def default_agent():
    result = subprocess.run(['omarchy', 'default', 'agent'], capture_output=True,
                            text=True, timeout=3, check=False)
    if result.returncode:
        raise ValueError('Could not read the configured default agent')
    return result.stdout.strip()


def action_argv(selected):
    """Plan activation without launching anything; never honor supplied commands."""
    if not isinstance(selected, dict):
        raise ValueError('Selection must be an object')
    kind, value = selected.get('kind'), selected.get('value')
    if not isinstance(value, str) or not value or len(value) > 8192 or '\x00' in value:
        raise ValueError('Invalid selection value')
    if kind == 'calculator':
        if not re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?', value, re.ASCII):
            raise ValueError('Invalid calculator result')
        number = float(value)
        if not math.isfinite(number) or abs(number) > 1e100:
            raise ValueError('Calculator result is out of range')
        return ['wl-copy']
    if kind in ('file', 'folder'):
        path = Path(value)
        if (not path.is_absolute() or not path.exists()
                or any(p.is_symlink() for p in (path, *path.parents))):
            raise ValueError('File no longer exists or is a symlink')
        connection = index_connection()
        try:
            known = connection.execute('SELECT is_dir FROM files WHERE path=?', (value,)).fetchone()
        finally:
            connection.close()
        if known is None or bool(known[0]) != (kind == 'folder'):
            raise ValueError('File is not in the index')
        return ['xdg-open', value]
    if kind == 'app':
        if any(x['id'] == selected.get('id') and x['value'] == value for x in apps(limit=None)):
            return ['gio', 'launch', value]
        raise ValueError('Application is no longer available or visible')
    if kind == 'ai':
        import ai_settings
        return ai_settings.launch_argv(value, default_agent=default_agent)
    if kind == 'web':
        return ['xdg-open', 'https://duckduckgo.com/?' + urlencode({'q': value})]
    if kind == 'action':
        actions = {'home': ['xdg-open', str(Path.home())],
                   'settings': ['omarchy', 'menu', 'summon', 'setup'],
                   'screenshot': ['omarchy', 'capture', 'screenshot', 'region', 'copy']}
        if value in actions and selected.get('id') == 'action:' + value:
            return actions[value]
        raise ValueError('Unknown desktop action')
    raise ValueError('Unsupported selection kind')


def activate(selected):
    """Acknowledge dispatch, not downstream GUI success. No prompt logging."""
    try:
        argv = action_argv(selected)
        if selected['kind'] == 'calculator':
            completed = subprocess.run(argv, input=selected['value'], text=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=3, check=False)
            if completed.returncode:
                return {'ok': False, 'error': 'Clipboard copy failed'}
        else:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True, cwd=str(Path.home()))
            try:
                if process.wait(timeout=0.15):
                    return {'ok': False, 'error': 'Launcher exited with an error'}
            except subprocess.TimeoutExpired:
                pass  # GUI/terminal owns its independent lifetime.
        return {'ok': True, 'error': ''}
    except ValueError as error:
        return {'ok': False, 'error': str(error)}
    except FileNotFoundError:
        return {'ok': False, 'error': 'Required command or file was not found'}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'Action timed out'}
    except Exception:
        return {'ok': False, 'error': 'Unable to activate this result'}


def query(text):
    result = {'query': text, 'items': [], 'status': 'Ready', 'error': ''}
    original = text
    if len(text) > 8192 or '\x00' in text:
        result['error'] = 'Query is too long or contains an invalid character'
        return result
    text = text.lstrip()
    if text.startswith('file '):
        result['items'], result['status'] = file_results(text[5:])
        return result
    if text.startswith('app '):
        # A dedicated catalog must not inherit the mixed-search result cap.
        result['items'] = apps(text[4:], limit=None)
        result['status'] = f"{len(result['items'])} apps"
        return result
    if text.startswith('?'):
        value = text[2:] if text.startswith('? ') else text[1:]
        result['items'] = [item('ai', 'Ask AI in terminal', value, value, 'utilities-terminal')] if value.strip() else []
        return result
    if text.startswith('web '):
        value = text[4:]
        result['items'] = [item('web', 'Search web', value, value, 'web-browser')] if value.strip() else []
        return result
    if text.startswith('>'):
        words = text[1:].casefold().split()
        result['items'] = [x for x in quick_actions()
                           if all(w in (x['title'] + ' ' + x['subtitle']).casefold() for w in words)]
        return result
    explicit = text.lstrip().startswith('=')
    expression = text.lstrip()[1:].strip() if explicit else text.strip()
    if expression or explicit:
        try:
            value = calculate(expression)
            result['items'] = [item('calculator', value, 'Copy result · ' + expression,
                                    value, 'accessories-calculator')]
            if not explicit:
                result['items'] += [item('ai', 'Ask AI in terminal', original, original, 'utilities-terminal'),
                                    item('web', 'Search web', original, original, 'web-browser')]
            return result
        except (ValueError, SyntaxError, TypeError, ArithmeticError, RecursionError):
            if explicit:
                result['error'] = 'Invalid or out-of-range calculation'
                return result
    if not text.strip():
        result['items'] = quick_actions()
        return result
    matches = apps(text, 10)
    files, result['status'] = file_results(text, MAX_ITEMS - 2 - len(matches))
    # Plain text defaults to AI only on explicit activation, never on typing.
    result['items'] = [item('ai', 'Ask AI in terminal', original, original, 'utilities-terminal')] + matches + files + [
        item('web', 'Search web', original, original, 'web-browser')]
    return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) == 2 and args[0] == 'query':
            result = query(args[1])
        elif len(args) == 2 and args[0] == 'activate':
            try:
                result = activate(json.loads(args[1]))
            except (ValueError, TypeError):
                result = {'ok': False, 'error': 'Invalid selection JSON'}
        elif args in (['index'], ['index', '--force']):
            result = build_index(force='--force' in args)
        else:
            result = {'ok': False, 'error': 'Usage: backend.py query <query> | index [--force] | activate <JSON item>'}
    except Exception:
        if args and args[0] == 'query':
            result = {'query': args[1] if len(args) > 1 else '', 'items': [],
                      'status': 'Unavailable', 'error': 'Unable to complete this query'}
        else:
            result = {'ok': False, 'status': 'error', 'error': 'Unable to complete this operation'}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
