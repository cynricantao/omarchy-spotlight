"""Stdlib-only backend tests. Fixtures stay in TMPDIR; no real launches."""
import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SCRATCH = Path(os.environ.get('TMPDIR', tempfile.gettempdir()))
SCRATCH.mkdir(parents=True, exist_ok=True)


def load_backend():
    spec = importlib.util.spec_from_file_location('spotlight_backend', HERE / 'backend.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackendTests(unittest.TestCase):
    def fixture(self):
        return Path(tempfile.mkdtemp(prefix='spotlight-test-', dir=SCRATCH))

    def test_empty_query_json_contract_and_curated_defaults(self):
        self.assertTrue((HERE / 'backend.py').exists(), 'backend CLI is not implemented')
        result = subprocess.run([sys.executable, '-B', str(HERE / 'backend.py'), 'query', ''],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(set(value), {'query', 'items', 'status', 'error'})
        self.assertEqual(value['query'], '')
        self.assertEqual(value['error'], '')
        self.assertGreater(len(value['items']), 0)
        self.assertLessEqual(len(value['items']), 24)
        for item in value['items']:
            self.assertEqual(set(item), {'id', 'kind', 'title', 'subtitle', 'icon', 'value'})
            self.assertTrue(all(isinstance(x, str) for x in item.values()))
        self.assertEqual(value['items'][0]['kind'], 'action')

    def test_calculator_evaluates_only_bounded_numeric_expressions(self):
        b = load_backend()
        cases = {'2 + 3 * (4 - 1)': '11', 'sqrt(81) + abs(-2)': '11',
                 'round(pi, 3)': '3.142', '2**8 + 9//2 % 3': '257',
                 'sin(pi/2)': '1', 'log(e)': '1', '0.1 + 0.2': '0.3'}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                result = b.query('= ' + expression)
                self.assertEqual(result['error'], '')
                self.assertEqual(result['items'][0]['kind'], 'calculator')
                self.assertEqual(result['items'][0]['value'], expected)
        for expression in ['__import__("os")', '(1).__class__', '[1][0]',
                           'True + 1', '1/0', '1e999', '2**1000000000',
                           '9**9**9', 'sqrt(-1)', '1+' * 300, 'round(1, 99999)',
                           '"text"', '2 << 4', 'sum([1,2])']:
            with self.subTest(rejected=expression):
                result = b.query('= ' + expression)
                self.assertEqual(result['items'], [])
                self.assertTrue(result['error'])
        self.assertEqual(b.query('3*7')['items'][0]['value'], '21')

    def test_web_and_action_routing_never_interpret_shell_text(self):
        from urllib.parse import parse_qs, urlsplit
        b = load_backend()
        payload = 'quotes " café & $(touch NEVER) ? #'
        result = b.query('web ' + payload)
        self.assertEqual([x['kind'] for x in result['items']], ['web'])
        selected = result['items'][0]
        self.assertEqual(selected['value'], payload)
        self.assertTrue(hasattr(b, 'action_argv'), 'safe activation planner missing')
        argv = b.action_argv(selected)
        self.assertEqual(argv[0], 'xdg-open')
        url = urlsplit(argv[1])
        self.assertEqual(url.scheme, 'https')
        self.assertEqual(url.netloc, 'duckduckgo.com')
        self.assertEqual(parse_qs(url.query)['q'], [payload])
        for action in b.quick_actions():
            if action['kind'] == 'menu':
                with self.assertRaises(ValueError):
                    b.action_argv(action)
                continue
            self.assertEqual(action['kind'], 'action')
            argv = b.action_argv(action)
            self.assertNotIn(argv[0], ['sh', 'bash', 'sudo', 'rm', 'reboot'])
        with self.assertRaises(ValueError):
            b.action_argv({'kind': 'action', 'value': 'rm -rf /', 'id': 'action:home'})
        with self.assertRaises(ValueError):
            b.action_argv({'kind': 'shell', 'value': payload})

    def test_ai_uses_configured_agent_without_bypassing_approval(self):
        b = load_backend()
        prompt = '--yolo "why?" $(touch NEVER) café\nkeep trailing spaces  '
        selected = b.query('? ' + prompt)['items'][0]
        self.assertEqual(selected['kind'], 'ai')
        self.assertEqual(selected['value'], prompt)
        self.assertTrue(hasattr(b, 'default_agent'), 'default agent lookup missing')
        import ai_settings
        with patch.object(ai_settings, 'config_path', return_value=self.fixture()/'missing-settings.json'), patch.object(ai_settings.shutil, 'which', return_value='/bin/true'), patch.object(b, 'default_agent', return_value='hermes'):
            argv = b.action_argv(selected)
        self.assertEqual(argv, ['omarchy-launch-tui', '--app-id=org.omarchy.agent',
                               'env', '-u', 'HERMES_SESSION_SOURCE', 'hermes', 'chat',
                               '--tui', '--query=' + prompt])
        with patch.object(ai_settings, 'config_path', return_value=self.fixture()/'missing-settings.json'), patch.object(b, 'default_agent', return_value='unknown-agent'):
            with self.assertRaisesRegex(ValueError, 'supported'):
                b.action_argv(selected)
        plain = b.query('why is the sky blue?')
        self.assertEqual(plain['items'][0]['kind'], 'ai')
        self.assertEqual(plain['items'][-1]['kind'], 'web')
        self.assertEqual(plain['items'][0]['value'], 'why is the sky blue?')

    def test_app_discovery_respects_xdg_overrides_and_visibility(self):
        b = load_backend()
        root = self.fixture()
        user, system = root / 'user', root / 'system'
        for base in (user, system):
            (base / 'applications').mkdir(parents=True)
        def desktop(base, name, fields):
            path = base / 'applications' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('[Desktop Entry]\nType=Application\nExec=/bin/true\n' + fields)
            return path
        hidden = desktop(system, 'hidden.desktop', 'Name=Hidden Foo\n')
        desktop(user, 'hidden.desktop', 'Hidden=true\n')
        desktop(system, 'private.desktop', 'Name=Private Foo\nNoDisplay=true\n')
        desktop(system, 'other.desktop', 'Name=Other Foo\nOnlyShowIn=GNOME;\n')
        desktop(system, 'missing.desktop', 'Name=Missing Foo\nTryExec=spotlight-nonexistent-xyz\n')
        desktop(system, 'editor.desktop', 'Name=Old Foo\n')
        editor = desktop(user, 'editor.desktop', 'Name=New Café Foo\nKeywords=Writing;Text;\nIcon=text-editor\n')
        desktop(system, 'nested/tool.desktop', 'Name=Nested Tool\nNotShowIn=GNOME;\n')
        env = {'XDG_DATA_HOME': str(user), 'XDG_DATA_DIRS': str(system), 'XDG_CURRENT_DESKTOP': 'Hyprland'}
        with patch.dict(os.environ, env):
            matches = b.query('app foo')['items']
            self.assertEqual([x['title'] for x in matches], ['New Café Foo'])
            self.assertEqual(matches[0]['value'], str(editor))
            self.assertEqual(b.action_argv(matches[0]), ['gio', 'launch', str(editor)])
            self.assertEqual(b.query('app writing')['items'][0]['value'], str(editor))
            self.assertEqual(len(b.query('app ')['items']), 2)
            self.assertEqual(b.query('café')['items'][1]['kind'], 'app')
            with self.assertRaises(ValueError):
                b.action_argv({'id': 'app:hidden.desktop', 'kind': 'app', 'value': str(hidden)})

    def test_filename_index_is_private_name_only_and_searchable(self):
        import sqlite3
        b = load_backend()
        self.assertTrue(hasattr(b, 'build_index'), 'filename index missing')
        fixture = self.fixture()
        home, cache = fixture / 'home', fixture / 'cache'
        home.mkdir()
        documents = home / 'Documents'
        documents.mkdir()
        names = ['annual "report" café.txt', 'annual notes.txt', '100%_done.txt']
        for name in names:
            (documents / name).write_text('CONTENTS_MUST_NOT_BE_INDEXED')
        for name in ['.hidden', 'node_modules', 'build', 'venv', 'cache', '__pycache__']:
            (home / name).mkdir()
            (home / name / 'annual private.txt').write_text('private')
        (home / '.secret-file').write_text('private')
        (home / 'linked-dir').symlink_to(documents, target_is_directory=True)
        (home / 'linked-file').symlink_to(documents / names[0])
        with patch.object(b, 'cache_dir', return_value=cache):
            built = b.build_index(roots=[home], force=True)
            self.assertTrue(built['ok'], built)
            self.assertFalse(built['truncated'])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o700)
            db = cache / 'index.sqlite3'
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)
            found = b.query('file annual café')['items']
            self.assertEqual([x['value'] for x in found], [str(documents / names[0])])
            self.assertEqual(b.action_argv(found[0]), ['xdg-open', str(documents / names[0])])
            self.assertEqual(b.query('file 100%_')['items'][0]['title'], '100%_done.txt')
            self.assertEqual(b.query('file Documents')['items'][0]['kind'], 'folder')
            self.assertEqual(b.query('file CONTENTS_MUST_NOT_BE_INDEXED')['items'], [])
            self.assertEqual(b.query('file private')['items'], [])
            self.assertEqual(b.query('file linked')['items'], [])
            self.assertEqual(b.query('annual café')['items'][1]['kind'], 'file')
            with closing(sqlite3.connect(db)) as connection:
                rows = connection.execute('SELECT path FROM files').fetchall()
            self.assertEqual(len(rows), 4)

    def test_index_budgets_publish_honest_truncation_and_limit_results(self):
        b = load_backend()
        root = self.fixture()
        home, cache = root / 'home', root / 'cache'
        home.mkdir()
        for n in range(40):
            (home / ('match-%02d.txt' % n)).touch()
        with patch.object(b, 'cache_dir', return_value=cache):
            self.assertIn('max_rows', __import__('inspect').signature(b.build_index).parameters,
                          'scan budgets missing')
            limited = b.build_index(roots=[home], force=True, max_rows=5)
            self.assertEqual(limited['count'], 5)
            self.assertTrue(limited['truncated'])
            self.assertIn('truncated', b.query('file match')['status'].lower())
            timed = b.build_index(roots=[home], force=True, max_seconds=0)
            self.assertEqual(timed['count'], 0)
            self.assertTrue(timed['truncated'])
            complete = b.build_index(roots=[home], force=True)
            self.assertEqual(complete['count'], 40)
            self.assertFalse(complete['truncated'])
            self.assertEqual(len(b.query('file match')['items']), 24)
            mixed = b.query('match')['items']
            self.assertEqual(len(mixed), 24)
            self.assertEqual(mixed[0]['kind'], 'ai')
            self.assertEqual(mixed[-1]['kind'], 'web')


    def test_index_refresh_is_atomic_fresh_and_nonblocking_locked(self):
        import fcntl
        b = load_backend()
        root = self.fixture()
        home, cache = root / 'home', root / 'cache'
        home.mkdir()
        (home / 'first.txt').touch()
        with patch.object(b, 'cache_dir', return_value=cache):
            b.build_index(roots=[home], force=True)
            db = cache / 'index.sqlite3'
            inode = db.stat().st_ino
            (home / 'second.txt').touch()
            fresh = b.build_index(roots=[home])
            self.assertEqual(fresh['status'], 'fresh')
            self.assertEqual(db.stat().st_ino, inode)
            with closing(b.index_connection()) as old_reader:
                self.assertEqual(old_reader.execute('SELECT count(*) FROM files').fetchone()[0], 1)
                b.build_index(roots=[home], force=True)
                self.assertNotEqual(db.stat().st_ino, inode)
                self.assertEqual(old_reader.execute('SELECT count(*) FROM files').fetchone()[0], 1)
            with (cache / 'index.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(b.os, 'scandir', side_effect=AssertionError('must not scan while locked')):
                    busy = b.build_index(roots=[home], force=True)
                self.assertEqual(busy['status'], 'busy')
                self.assertEqual(len(b.query('file ')['items']), 2)
            self.assertEqual((cache / 'index.lock').stat().st_mode & 0o777, 0o600)
            with patch.object(b.time, 'time', return_value=fresh['built_at'] + 901):
                refreshed = b.build_index(roots=[home])
            self.assertEqual(refreshed['status'], 'indexed')

    def test_roots_include_only_home_and_current_visible_media_mounts(self):
        b = load_backend()
        self.assertTrue(hasattr(b, 'discover_roots'), 'mounted-root discovery missing')
        fixture = self.fixture()
        home, media = fixture / 'home', fixture / 'media'
        home.mkdir()
        media.mkdir()
        mounted, unmounted, hidden = media / 'Photos Drive', media / 'unmounted', media / '.hidden'
        for directory in (mounted, unmounted, hidden):
            directory.mkdir()
        (media / 'link').symlink_to(mounted, target_is_directory=True)
        escaped = str(mounted).replace(' ', r'\040')
        mountinfo = '\n'.join([
            '30 1 8:1 / ' + escaped + ' rw - ext4 /dev/test rw',
            '31 1 8:2 / ' + str(hidden) + ' rw - ext4 /dev/test rw',
            '32 1 8:3 / ' + str(media / 'link') + ' rw - ext4 /dev/test rw',
            '33 1 8:4 / /other/mount rw - ext4 /dev/test rw'])
        roots = b.discover_roots(home=home, media_base=media, mountinfo=mountinfo)
        self.assertEqual(roots, [home, mounted])
        with patch.object(b, 'cache_dir', return_value=fixture / 'cache'), \
             patch.object(b, 'discover_roots', return_value=roots):
            (mounted / 'holiday.jpg').touch()
            b.build_index(force=True)
            self.assertEqual(b.query('file holiday')['items'][0]['value'], str(mounted / 'holiday.jpg'))

    def test_activation_dispatches_only_validated_argv_and_returns_errors(self):
        b = load_backend()
        self.assertTrue(hasattr(b, 'activate'), 'activation dispatch missing')
        with patch.object(b.subprocess, 'Popen') as spawn, patch.object(b.subprocess, 'run') as run:
            spawn.return_value.wait.return_value = 0
            run.return_value.returncode = 0
            web = b.query('web hello; not a command')['items'][0]
            self.assertEqual(b.activate(web), {'ok': True, 'error': ''})
            args, kwargs = spawn.call_args
            self.assertEqual(args[0], b.action_argv(web))
            self.assertFalse(kwargs.get('shell', False))
            self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
            self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
            calc = b.query('= 21*2')['items'][0]
            self.assertEqual(b.action_argv(calc), ['wl-copy'])
            self.assertEqual(b.activate(calc), {'ok': True, 'error': ''})
            self.assertEqual(run.call_args.args[0], ['wl-copy'])
            self.assertEqual(run.call_args.kwargs['input'], '42')
            self.assertFalse(run.call_args.kwargs.get('shell', False))
            spawn.side_effect = FileNotFoundError('missing command')
            self.assertFalse(b.activate(web)['ok'])
            before = spawn.call_count
            for bad in [None, [], {}, {'kind': 'shell', 'value': 'touch NEVER'},
                        {'kind': 'calculator', 'value': '$(touch NEVER)'},
                        {'kind': 'action', 'id': 'action:home', 'value': 'home; touch NEVER'},
                        {'kind': 'file', 'value': '/does/not/exist/spotlight-test'}]:
                self.assertFalse(b.activate(bad)['ok'])
                self.assertTrue(b.activate(bad)['error'])
            self.assertEqual(spawn.call_count, before)
        completed = subprocess.run([sys.executable, '-B', str(HERE / 'backend.py'),
                                    'activate', '{broken json'], capture_output=True, text=True)
        self.assertFalse(json.loads(completed.stdout)['ok'])
        self.assertEqual(completed.stderr, '')

    def test_cli_index_dispatch_and_errors_are_single_json(self):
        from contextlib import redirect_stdout
        from io import StringIO
        b = load_backend()
        root = self.fixture()
        home, cache = root / 'home', root / 'cache'
        home.mkdir()
        (home / 'cli-file.txt').touch()
        with patch.object(b, 'cache_dir', return_value=cache), \
             patch.object(b, 'discover_roots', return_value=[home]):
            output = StringIO()
            with redirect_stdout(output):
                b.main(['index', '--force'])
            result = json.loads(output.getvalue())
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['count'], 1)
            output = StringIO()
            with redirect_stdout(output):
                b.main(['index'])
            self.assertEqual(json.loads(output.getvalue())['status'], 'fresh')
            with patch.object(b, 'build_index', side_effect=PermissionError('private path')):
                output = StringIO()
                with redirect_stdout(output):
                    b.main(['index', '--force'])
                self.assertFalse(json.loads(output.getvalue())['ok'])
            with patch.object(b, 'apps', side_effect=PermissionError('private path')):
                output = StringIO()
                with redirect_stdout(output):
                    b.main(['query', 'app '])
                result = json.loads(output.getvalue())
                self.assertEqual(result['query'], 'app ')
                self.assertEqual(result['items'], [])
                self.assertTrue(result['error'])
                self.assertNotIn('private path', output.getvalue())

    def test_query_keeps_original_text_and_plain_calculation_fallbacks(self):
        b = load_backend()
        original = '   ?  preserve "quotes" ?  '
        result = b.query(original)
        self.assertEqual(result['query'], original)
        self.assertEqual(result['items'][0]['kind'], 'ai')
        self.assertEqual(result['items'][0]['value'], ' preserve "quotes" ?  ')
        calculated = b.query('  3*7  ')
        self.assertEqual(calculated['query'], '  3*7  ')
        self.assertEqual([x['kind'] for x in calculated['items']], ['calculator', 'ai', 'web'])
        self.assertEqual(len(b.query(' = 3*7')['items']), 1)
        for text in ['web ', '? ', 'app ', 'file ', '> ', '']:
            result = b.query(text)
            self.assertFalse(any(x['kind'] == 'help' for x in result['items']))
        for text in ['x' * 8193, 'bad\x00query']:
            result = b.query(text)
            self.assertEqual(result['query'], text)
            self.assertEqual(result['items'], [])
            self.assertTrue(result['error'])

    def test_file_activation_rejects_symlinked_parents_and_stale_paths(self):
        b = load_backend()
        root = self.fixture()
        home, cache = root / 'home', root / 'cache'
        documents = home / 'Documents'
        documents.mkdir(parents=True)
        file = documents / 'keep.txt'
        file.touch()
        with patch.object(b, 'cache_dir', return_value=cache):
            b.build_index(roots=[home], force=True)
            selected = b.query('file keep')['items'][0]
            moved = home / 'Archived'
            documents.rename(moved)
            self.assertFalse(b.activate(selected)['ok'])
            documents.symlink_to(moved, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                b.action_argv(selected)
            b.build_index(roots=[home], force=True)
            self.assertFalse(any(x['value'].startswith(str(documents) + '/')
                                 for x in b.query('file keep')['items']))

    def test_settings_navigation_is_native_not_a_stock_menu_fallback(self):
        b = load_backend()
        choice = next(x for x in b.quick_actions() if x['value'] == 'root')
        self.assertEqual(choice['kind'], 'menu')
        with self.assertRaises(ValueError):
            b.action_argv(choice)
        with self.assertRaises(ValueError):
            b.action_argv({'kind': 'action', 'id': 'action:settings', 'value': 'settings'})
        home = b.quick_actions()[0]
        self.assertEqual(b.action_argv(dict(home, command='rm -rf /', args=['shutdown'])),
                         b.action_argv(home))

    def test_index_never_follows_symlinked_root_ancestors(self):
        b = load_backend()
        root = self.fixture()
        real = root / 'real' / 'sub'
        real.mkdir(parents=True)
        (real / 'secret-name.txt').touch()
        (root / 'link').symlink_to(real.parent, target_is_directory=True)
        with patch.object(b, 'cache_dir', return_value=root / 'cache'):
            built = b.build_index(roots=[root / 'link' / 'sub'], force=True)
            self.assertEqual(built['count'], 0)
            self.assertEqual(b.query('file secret')['items'], [])

    def test_queries_are_offline_read_only_and_do_not_start_indexing(self):
        import socket
        b = load_backend()
        root = self.fixture()
        cache = root / 'missing-cache'
        with patch.object(b, 'cache_dir', return_value=cache), \
             patch.object(b, 'build_index', side_effect=AssertionError('query must not index')), \
             patch.object(b.subprocess, 'Popen', side_effect=AssertionError('query must not launch')), \
             patch.object(b.subprocess, 'run', side_effect=AssertionError('query must not spawn')), \
             patch.object(socket, 'create_connection', side_effect=AssertionError('query must not network')):
            # Menu discovery separately evaluates trusted local visibility guards;
            # it is covered by test_omarchy_menu, not this spawn-free search gate.
            for text in ['', 'hello', 'file hello', 'app ', '? what?', 'web search', '= 2+2']:
                self.assertEqual(b.query(text)['error'], '')
            self.assertFalse(cache.exists())
        home = root / 'home'
        home.mkdir()
        (home / 'literal.txt').touch()
        with patch.object(b, 'cache_dir', return_value=cache):
            b.build_index(roots=[home], force=True)
            db = cache / 'index.sqlite3'
            before = db.read_bytes()
            for text in ['file literal', "file ' OR 1=1 --", 'literal', 'file %']:
                b.query(text)
            self.assertEqual(db.read_bytes(), before)
            with closing(b.index_connection()) as connection:
                with self.assertRaises(b.sqlite3.OperationalError):
                    connection.execute('CREATE TABLE forbidden(value TEXT)')

    def test_busy_index_reports_retained_count_and_failed_publish_keeps_old_index(self):
        import fcntl
        b = load_backend()
        root = self.fixture()
        home, cache = root / 'home', root / 'cache'
        home.mkdir()
        (home / 'safe.txt').touch()
        with patch.object(b, 'cache_dir', return_value=cache):
            b.build_index(roots=[home], force=True)
            with (cache / 'index.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(b.build_index(roots=[home], force=True)['count'], 1)
            before = (cache / 'index.sqlite3').read_bytes()
            (home / 'new.txt').touch()
            with patch.object(b.os, 'replace', side_effect=OSError('simulated failed publish')):
                with self.assertRaises(OSError):
                    b.build_index(roots=[home], force=True)
            self.assertEqual((cache / 'index.sqlite3').read_bytes(), before)
            self.assertEqual(b.query('file safe')['items'][0]['title'], 'safe.txt')
            self.assertEqual(b.query('file new')['items'], [])
            self.assertEqual(b.build_index(roots=[home], force=True)['count'], 2)

    def test_filename_search_does_not_silently_ignore_extra_terms(self):
        b = load_backend()
        root = self.fixture()
        home = root / 'home'
        home.mkdir()
        words = ['term%d' % number for number in range(16)]
        (home / (' '.join(words) + '.txt')).touch()
        with patch.object(b, 'cache_dir', return_value=root / 'cache'):
            b.build_index(roots=[home], force=True)
            result = b.query('file ' + ' '.join(words + ['absent']))
            self.assertEqual(result['items'], [])
            self.assertIn('16', result['status'])

    def test_general_text_defaults_to_ai_without_hiding_local_matches(self):
        b = load_backend()
        fixture = self.fixture()
        data, home = fixture / 'data', fixture / 'home'
        applications = data / 'applications'
        applications.mkdir(parents=True)
        home.mkdir()
        (applications / 'project.desktop').write_text('[Desktop Entry]\nType=Application\nName=Project\nExec=/bin/true\n')
        (home / 'Project notes.txt').touch()
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(data), 'XDG_DATA_DIRS': str(fixture / 'empty')}), patch.object(b, 'cache_dir', return_value=fixture / 'cache'):
            b.build_index(roots=[home], force=True)
            result = b.query('Project')
            self.assertEqual([x['kind'] for x in result['items']], ['ai', 'app', 'file', 'web'])
            self.assertEqual(result['items'][0]['value'], 'Project')
            self.assertEqual(b.query('app Project')['items'][0]['kind'], 'app')
            self.assertEqual(b.query('file Project')['items'][0]['kind'], 'file')
            self.assertEqual(b.query('web Project')['items'][0]['kind'], 'web')
            self.assertEqual(b.query('42 * 2')['items'][0]['kind'], 'calculator')

    def test_ai_action_delegates_to_configurable_cli_planner(self):
        from types import SimpleNamespace
        b = load_backend()
        prompt = '--help "quoted" $(not-a-command) café'
        received = []
        def plan(value, default_agent=None):
            received.append((value, default_agent))
            return ['test-terminal', 'test-ai-cli', '--', value]
        with patch.dict(sys.modules, {'ai_settings': SimpleNamespace(launch_argv=plan)}):
            argv = b.action_argv({'kind': 'ai', 'value': prompt})
        self.assertEqual(argv, ['test-terminal', 'test-ai-cli', '--', prompt])
        self.assertEqual(received, [(prompt, b.default_agent)])

    def test_apps_category_returns_entire_catalog_and_match_count(self):
        b = load_backend()
        fixture = self.fixture()
        data = fixture / 'data'
        applications = data / 'applications'
        applications.mkdir(parents=True)
        expected = set()
        for number in range(67):
            path = applications / f'fixture-{number:02}.desktop'
            path.write_text(f'[Desktop Entry]\nType=Application\nName=Fixture {number:02}\nExec=/bin/true\n')
            expected.add(str(path))
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(data), 'XDG_DATA_DIRS': str(fixture / 'empty')}):
            for query in ('app ', 'app Fixture'):
                result = b.query(query)
                self.assertEqual(len(result['items']), 67, 'Apps must not inherit the mixed-search result cap')
                self.assertEqual({x['value'] for x in result['items']}, expected)
                self.assertEqual(result['status'], '67 apps')
            self.assertEqual(len(b.query('app Fixture 66')['items']), 1)
            self.assertEqual(b.query('app absent')['status'], '0 apps')


if __name__ == '__main__':
    unittest.main()
