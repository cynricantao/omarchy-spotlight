"""Focused menu tests: private sources and injected read-only subprocesses."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


class SourceTests(unittest.TestCase):
    def test_jsonc_extension_tree_search_and_native_navigation(self):
        self.assertIsNotNone(importlib.util.find_spec('omarchy_menu'), 'menu module is missing')
        menu = importlib.import_module('omarchy_menu')
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
            default = Path(directory) / 'default.jsonc'
            extension = Path(directory) / 'extension.jsonc'
            default.write_text(r'''{
              // Keep URL slashes and escaped quotes intact.
              "apps": {"label":"Apps", "provider":"apps"},
              "learn": {"label":"Learn", "aliases":["manual"]},
              "learn.docs": {"label":"Docs", "description":"https://host/a/*b*/", "action":"printf '%s' \"https://host/a//b\\\"\""},
              "learn.gone": {"label":"Gone", "action":"true"},
              "shortcut": {"label":"Shortcut", "target":"manual"},
            }''', encoding='utf-8')
            extension.write_text('''{"items": {
              "learn": {"label":"Help"}, /* inline comment */
              "learn.docs": {"icon":"X", "iconFont":"omarchy"},
              "learn.gone": null,
              "learn.extra": {"label":"Extra", "action":"true", "aliases":"guide"},
            }}''', encoding='utf-8')
            engine = menu.MenuEngine(default, extension)
            root = engine.menu_query('>   ')
            self.assertEqual(root['query'], '>   ')
            self.assertEqual(root['menu'], 'root')
            self.assertEqual(root['status'], 'ready')
            self.assertEqual([r['title'] for r in root['items']], ['Apps', 'Help', 'Shortcut'])
            self.assertEqual(root['items'][0]['kind'], 'menu-apps')
            self.assertEqual(root['items'][2]['value'], 'learn')
            nested = engine.menu_query('>', 'manual')
            self.assertEqual(nested['menu'], 'manual')
            self.assertEqual(nested['breadcrumbs'], [{'id':'root','label':'Go'}, {'id':'learn','label':'Help'}])
            self.assertEqual([r['title'] for r in nested['items']], ['Docs', 'Extra'])
            docs = nested['items'][0]
            self.assertEqual(docs['id'], 'omarchy:learn.docs')
            self.assertEqual(docs['value'], 'learn.docs')
            self.assertEqual(docs['kind'], 'menu-action')
            self.assertEqual(docs['subtitle'], 'https://host/a/*b*/')
            self.assertEqual((docs['iconKind'], docs['icon'], docs['iconFont']), ('glyph', 'X', 'omarchy'))
            search = engine.menu_query('>  Help guide  ')
            self.assertEqual(search['query'], '>  Help guide  ')
            self.assertEqual([r['value'] for r in search['items']], ['learn.extra'])
            self.assertEqual(search['items'][0]['subtitle'], 'Help')
            self.assertEqual(engine.menu_query('> gone')['items'], [])


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.menu = importlib.import_module('omarchy_menu')
        self.directory = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.directory.cleanup)
        self.default = Path(self.directory.name) / 'default.jsonc'
        self.extension = Path(self.directory.name) / 'extension.jsonc'
        self.calls = []

    def engine(self, items, runner=None):
        self.default.write_text(json.dumps(items), encoding='utf-8')
        return self.menu.MenuEngine(self.default, self.extension, runner=runner)

    def reading_runner(self, argv, timeout):
        self.calls.append((argv, timeout))
        return self.menu.run_readonly(argv, timeout=timeout)

    def test_repeated_trusted_reader_is_cached_once_within_guard_batch(self):
        reader = Path(self.directory.name) / 'omarchy-default-agent'
        counter = Path(self.directory.name) / 'reads'
        reader.write_text('#!/bin/bash\nprintf x >> ' + str(counter) + '\nprintf "%s" hermes\n', encoding='utf-8')
        reader.chmod(0o700)
        from unittest.mock import patch
        with patch.dict(os.environ, {'PATH':str(reader.parent) + ':' + os.environ['PATH']}):
            engine = self.engine({'defaults': {},
                                  'defaults.a': {'action':'NEVER', 'checked':'[[ "$(omarchy-default-agent)" == hermes ]]'},
                                  'defaults.b': {'action':'NEVER', 'checked':'[[ "$(omarchy-default-agent)" == codex ]]'}})
            response = engine.menu_query('>', 'defaults')
        self.assertEqual(response['status'], 'ready', response['error'])
        self.assertEqual([row['checked'] for row in response['items']], [True, False])
        self.assertEqual(counter.read_text(), 'x', 'reader process repeated for sibling guards')

    def test_runner_bounds_time_closes_pipes_and_ignores_bash_env(self):
        import subprocess
        import time
        from unittest.mock import patch
        malicious = Path(self.directory.name) / 'bash-env'
        malicious.write_text('exit 91', encoding='utf-8')
        with patch.dict(os.environ, {'BASH_ENV':str(malicious)}):
            self.assertEqual(self.menu.run_readonly(['bash', '-c', 'true']).returncode, 0)
        before = len(list(Path('/proc/self/fd').iterdir()))
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.menu.run_readonly(['bash', '-c', 'sleep 10'], timeout=0.05)
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)

    def test_partial_guard_failure_preserves_unguarded_rows_but_never_activates_failed_guard(self):
        engine = self.engine({'plain': {'action':'NEVER'}, 'guarded': {'when':'exit 2', 'action':'NEVER'}})
        response = engine.menu_query('>')
        self.assertEqual([r['value'] for r in response['items']], ['plain'])
        self.assertEqual(response['status'], 'partial')
        self.assertTrue(response['error'])

    def test_malformed_sources_fail_closed_without_running_any_command(self):
        bad_sources = ['{"ok": {"action": "true"}, "bad": {"action": []}}',
                       '{"bad": {"label": 42}}', '{"bad": {"aliases": [1]}}',
                       '{"bad": {"when": true}}', '{"bad": {"parent": []}}',
                       '{"bad": {"provider": {}}}', '{"bad": {"_argv": ["INJECT"]}}',
                       '{"bad id": {"action": "true"}}', '{"bad": {"action":"x", "target":"root"}}',
                       '{"root": {"action":"x"}}', '{"bad": {"target":"no-such-menu"}}',
                       '{"a": {"target":"b"}, "b": {"target":"a"}}',
                       '{"a": {"parent":"b"}, "b": {"parent":"a"}}',
                       '{"a": {}, "a": {}}', '{"items": []}', '[]', '{', '{/* unfinished']
        def forbidden(argv, timeout):
            self.fail('Malformed source ran a subprocess')
        for source in bad_sources:
            with self.subTest(source=source):
                self.default.write_text(source, encoding='utf-8')
                response = self.menu.MenuEngine(self.default, runner=forbidden).menu_query('>')
                self.assertEqual(response['status'], 'error')
                self.assertEqual(response['items'], [])
                self.assertTrue(response['error'])
        self.default.write_text('{"safe": {"action":"NEVER"}}', encoding='utf-8')
        self.extension.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.menu.MenuEngine(self.default, self.extension).menu_query('>')['status'], 'error')

    def test_null_parent_deletes_subtree_and_null_field_clears_inherited_action(self):
        engine = self.engine({'keep': {'action':'NEVER'}, 'delete': {},
                              'delete.child': {'action':'NEVER'}, 'elsewhere': {'parent':'delete', 'action':'NEVER'}})
        self.extension.write_text(json.dumps({'delete':None, 'keep':{'action':None, 'provider':'apps'}}))
        response = engine.menu_query('>')
        self.assertEqual([r['value'] for r in response['items']], ['keep'])
        self.assertEqual(response['items'][0]['kind'], 'menu-apps')

    def test_full_descendant_results_are_uncapped_and_nested_scope_is_exact(self):
        items = {'learn': {'label':'Learn'}, 'setup': {'label':'Setup'}}
        items.update({'learn.item' + str(i): {'label':'Match ' + str(i), 'action':'NEVER'} for i in range(137)})
        items.update({'setup.item' + str(i): {'label':'Match ' + str(i), 'action':'NEVER'} for i in range(83)})
        engine = self.engine(items)
        global_rows = engine.menu_query('> Match')['items']
        nested = engine.menu_query('> Match', 'learn')['items']
        self.assertEqual(len(global_rows), 220)
        self.assertEqual(len(nested), 137)
        self.assertEqual(len({r['id'] for r in global_rows}), 220)
        self.assertTrue(all(r['value'].startswith('learn.') for r in nested))

    def test_installed_definition_all_ten_sections_and_every_static_entry(self):
        import re
        import subprocess
        installed = Path('/usr/share/omarchy/default/omarchy/omarchy-menu.jsonc')
        if not installed.exists():
            self.skipTest('Installed Omarchy source not present')
        def snapshot(argv, timeout):
            if argv[:2] == ['bash', '-c']:
                matches = re.findall(r"printf '(OMARCHY_GUARD_[a-f0-9]+):(\d+):%s", argv[2])
                return subprocess.CompletedProcess(argv, 0, ''.join(token + ':' + index + ':0\n' for token, index in matches), '')
            outputs = {('omarchy-font-list',):'Fixture Font\n', ('omarchy-font-current',):'Fixture Font\n'}
            return subprocess.CompletedProcess(argv, 0, outputs[tuple(argv)], '')
        engine = self.menu.MenuEngine(installed, runner=snapshot)
        entries = self.menu.load_menu(installed)
        root = engine.menu_query('>')
        self.assertEqual(root['status'], 'ready', root['error'])
        self.assertEqual([r['value'] for r in root['items']],
                         ['apps','learn','trigger','style','setup','install','remove','update','about','system'])
        collected = {}
        for identifier, entry in entries.items():
            if not entry.get('action') and not entry.get('target') and entry.get('provider') != 'apps':
                response = engine.menu_query('>', identifier)
                self.assertEqual(response['status'], 'ready', response['error'])
                collected.update({r['id']:r for r in response['items'] if '.__provider__' not in r['value']})
        self.assertEqual(set(collected), {'omarchy:' + i for i in entries if i != 'root'})

    def test_public_api_uses_official_path_and_preserves_exact_echo(self):
        from unittest.mock import patch
        engine = self.engine({'apps': {'provider':'apps'}})
        root = Path(self.directory.name) / 'installed'
        path = root / 'default/omarchy/omarchy-menu.jsonc'
        path.parent.mkdir(parents=True)
        path.write_text(self.default.read_text(), encoding='utf-8')
        with patch.dict(os.environ, {'OMARCHY_PATH':str(root)}), patch.object(Path, 'home', return_value=Path(self.directory.name)):
            response = self.menu.menu_query(' >   ', 'root')
            self.assertEqual(response['query'], ' >   ')
            self.assertEqual(response['menu'], 'root')
            self.assertEqual(response['items'][0]['kind'], 'menu-apps')
        with patch.dict(os.environ, {'OMARCHY_PATH':'relative-path'}):
            self.assertEqual(self.menu.menu_query('>')['status'], 'error')

    def test_font_provider_preserves_literal_values_checked_and_safe_argv(self):
        import subprocess
        values = ['Fira Code', 'Fira-Code', 'Odd $(touch NOPE); "Font"']
        def provider(argv, timeout):
            self.calls.append(argv)
            output = '\n'.join(values) + '\n' if argv == ['omarchy-font-list'] else values[2] + '\n'
            return subprocess.CompletedProcess(argv, 0, output, '')
        engine = self.engine({'style': {}, 'style.font': {'label':'Font', 'provider':'fonts'}}, provider)
        response = engine.menu_query('>', 'style.font')
        self.assertEqual(response['status'], 'ready')
        self.assertEqual([r['title'] for r in response['items']], values)
        self.assertEqual(len({r['id'] for r in response['items']}), len(values))
        self.assertEqual([r['checked'] for r in response['items']], [False, False, True])
        self.assertEqual(self.calls, [['omarchy-font-list'], ['omarchy-font-current']])
        row = {**response['items'][2], 'confirmed':True}
        self.assertEqual(engine.action_argv(row), ['omarchy-font-set', values[2]])
        search = engine.menu_query('> Odd')
        self.assertEqual([r['title'] for r in search['items']], [values[2]])
        self.assertEqual(search['items'][0]['subtitle'], 'style › Font')

    def test_power_profile_provider_uses_literal_native_arguments(self):
        import subprocess
        def provider(argv, timeout):
            outputs = {('omarchy-powerprofiles-list',): 'power-saver\nbalanced\nperformance\n',
                       ('powerprofilesctl', 'get'): 'balanced\n'}
            return subprocess.CompletedProcess(argv, 0, outputs[tuple(argv)], '')
        engine = self.engine({'setup': {}, 'setup.power': {'provider':'power-profiles'}}, provider)
        response = engine.menu_query('>', 'setup.power')
        self.assertEqual(len(response['items']), 3)
        row = next(r for r in response['items'] if r['checked'])
        self.assertEqual(engine.action_argv({**row, 'confirmed':True}),
                         ['omarchy-powerprofiles-set', 'autodetect', 'balanced'])

    def test_provider_failure_and_unsupported_provider_are_visibly_unavailable(self):
        import subprocess
        def missing(argv, timeout):
            raise FileNotFoundError('fixture missing binary')
        engine = self.engine({'fonts': {'provider':'fonts'}, 'custom': {'provider':'unknown'}}, missing)
        for identifier in ('fonts', 'custom'):
            response = engine.menu_query('>', identifier)
            self.assertEqual(response['items'], [])
            self.assertEqual(response['status'], 'unavailable')
            self.assertTrue(response['error'])
        root = engine.menu_query('>')
        unknown = next(r for r in root['items'] if r['value'] == 'custom')
        self.assertFalse(unknown['available'])
        self.assertIn('unavailable', unknown['subtitle'].lower())
        def bad_current(argv, timeout):
            return subprocess.CompletedProcess(argv, 2, '', 'fixture error')
        engine.runner = bad_current
        self.assertEqual(engine.menu_query('>', 'fonts')['status'], 'unavailable')

    def test_provider_stale_removed_font_cannot_be_activated(self):
        import subprocess
        values = ['One', 'Two']
        def provider(argv, timeout):
            return subprocess.CompletedProcess(argv, 0, '\n'.join(values) if argv == ['omarchy-font-list'] else 'One', '')
        engine = self.engine({'fonts': {'provider':'fonts'}}, provider)
        response = engine.menu_query('>', 'fonts')
        self.assertEqual(len(response['items']), 2)
        row = {**response['items'][1], 'confirmed':True}
        values.pop()
        with self.assertRaises(ValueError):
            engine.action_argv(row)

    def test_activation_reconstructs_exact_source_shell_after_bound_confirmation(self):
        action = 'theme=$(omarchy-theme-switcher); [[ -n $theme ]] && omarchy-theme-set "$theme"'
        engine = self.engine({'style': {}, 'style.theme': {'label':'Theme', 'action':action}})
        row = engine.menu_query('>', 'style')['items'][0]
        self.assertTrue(row['requiresConfirmation'])
        self.assertTrue(row.get('actionToken'), 'missing action binding')
        self.assertTrue(hasattr(engine, 'action_argv'), 'activation planner missing')
        for confirmed in (None, False, 'true', 1):
            with self.subTest(confirmed=confirmed):
                with self.assertRaises(ValueError):
                    engine.action_argv({**row, 'confirmed':confirmed, 'requiresConfirmation':False})
        self.assertEqual(engine.action_argv({**row, 'confirmed':True}), ['bash', '-c', action])

    def test_activation_rejects_payload_tampering_submenus_and_unknown_ids(self):
        engine = self.engine({'remove': {}, 'remove.package': {'action':'TRUSTED NEVER RUN'}})
        row = {**engine.menu_query('>', 'remove')['items'][0], 'confirmed':True}
        self.assertTrue(hasattr(engine, 'action_argv'), 'activation planner missing')
        for changes in ({'id':'omarchy:unknown'}, {'value':'unknown'}, {'kind':'menu'},
                        {'actionToken':'fake'}, {'action':'INJECT'}, {'argv':['INJECT']},
                        {'command':'INJECT'}, {'id':'omarchy:REMOVE.package'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    engine.action_argv({**row, **changes})
        with self.assertRaises(ValueError):
            engine.action_argv(engine.menu_query('>')['items'][0])

    def test_confirmation_cannot_survive_source_change_or_new_unavailability(self):
        items = {'setup': {}, 'setup.custom': {'action':'SOURCE A', 'when':'true'}}
        engine = self.engine(items)
        row = {**engine.menu_query('>', 'setup')['items'][0], 'confirmed':True}
        self.assertTrue(hasattr(engine, 'action_argv'), 'activation planner missing')
        items['setup.custom']['action'] = 'SOURCE B'
        self.default.write_text(json.dumps(items), encoding='utf-8')
        with self.assertRaises(ValueError):
            engine.action_argv(row)
        items['setup.custom']['action'] = 'SOURCE A'
        items['setup.custom']['when'] = 'false'
        self.default.write_text(json.dumps(items), encoding='utf-8')
        with self.assertRaises(ValueError):
            engine.action_argv(row)

    def test_activation_checks_current_guard_state_and_post_guard_source(self):
        flag = Path(self.directory.name) / 'available'
        flag.touch()
        items = {'custom': {'action':'NEVER RUN', 'when':'[[ -f ' + str(flag) + ' ]]'}}
        engine = self.engine(items)
        row = {**engine.menu_query('>')['items'][0], 'confirmed':True}
        self.assertTrue(hasattr(engine, 'action_argv'), 'activation planner missing')
        flag.unlink()
        with self.assertRaises(ValueError):
            engine.action_argv(row)
        flag.touch()
        def mutate_during_guard(argv, timeout):
            result = self.menu.run_readonly(argv, timeout)
            items['custom']['action'] = 'CHANGED DURING GUARD'
            self.default.write_text(json.dumps(items), encoding='utf-8')
            return result
        engine.runner = mutate_during_guard
        with self.assertRaises(ValueError):
            engine.action_argv(row)

    def test_every_risky_or_custom_leaf_demands_explicit_confirmation(self):
        identifiers = ['remove.package', 'style.about.default', 'setup.reset', 'system.suspend',
                       'system.hibernate', 'system.logout', 'system.reboot', 'system.shutdown',
                       'install.package', 'update.omarchy', 'setup.security.sshd',
                       'setup.network.dns', 'setup.direct-boot', 'update.firmware',
                       'update.channel.edge', 'custom.safe-looking']
        items = {}
        for identifier in identifiers:
            pieces = identifier.split('.')
            for i in range(1, len(pieces)):
                items.setdefault('.'.join(pieces[:i]), {})
            items[identifier] = {'action':'NEVER EXECUTE'}
        engine = self.engine(items)
        rows = engine.menu_query('> NEVER')['items']
        # Search source IDs, not action programs.
        self.assertEqual(rows, [])
        for identifier in identifiers:
            row = next(r for r in engine.menu_query('> ' + identifier)['items'] if r['value'] == identifier)
            self.assertTrue(row['requiresConfirmation'])
            self.assertTrue(row['confirmationReason'])

    def test_guards_are_batched_hidden_and_checked_without_query_code(self):
        engine = self.engine({
            'setup': {'label':'Setup'},
            'setup.yes': {'label':'Yes', 'action':'NEVER RUN ACTION', 'when':'true', 'checked':'true'},
            'setup.no': {'label':'No', 'action':'NEVER RUN ACTION', 'when':'false'},
            'setup.unchecked': {'label':'Unchecked', 'action':'NEVER RUN ACTION', 'checked':'false'},
        }, self.reading_runner)
        response = engine.menu_query('>', 'setup')
        self.assertEqual(response['status'], 'ready')
        self.assertEqual([row['value'] for row in response['items']], ['setup.yes', 'setup.unchecked'])
        self.assertEqual([row['checked'] for row in response['items']], [True, False])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0][:2], ['bash', '-c'])
        self.assertGreater(self.calls[0][1], 0)
        self.assertLessEqual(self.calls[0][1], 8)
        engine.menu_query('> $(touch NOT_ALLOWED); echo exploit')
        self.assertNotIn('NOT_ALLOWED', self.calls[-1][0][2])
        self.assertNotIn('NEVER RUN ACTION', self.calls[-1][0][2])

    def test_cached_checkmark_reader_for_hidden_row_is_never_initialized(self):
        def reader(argv, timeout):
            script = 'omarchy-default-browser() { return 2; }\n' + argv[2]
            return self.menu.run_readonly(['bash', '-c', script], timeout)
        engine = self.engine({'available': {'when':'true', 'action':'NEVER'},
                              'hidden': {'when':'false', 'action':'NEVER',
                                         'checked':'[[ "$(omarchy-default-browser)" == x ]]'}}, reader)
        response = engine.menu_query('>')
        self.assertEqual(response['status'], 'ready', response['error'])
        self.assertEqual([row['value'] for row in response['items']], ['available'])

    def test_hidden_ancestor_skips_child_checkmark_reader(self):
        engine = self.engine({'available': {'when':'true', 'action':'NEVER'},
                              'hidden': {'when':'false'},
                              'hidden.child': {'action':'NEVER', 'checked':'not_a_real_reader_123'}})
        response = engine.menu_query('>')
        self.assertEqual(response['status'], 'ready', response['error'])
        self.assertEqual([row['value'] for row in response['items']], ['available'])

    def test_false_guard_diagnostics_and_hidden_checked_reader_do_not_poison_siblings(self):
        engine = self.engine({'setup': {},
                              'setup.available': {'when':'true', 'action':'NEVER'},
                              'setup.hidden': {'when':'printf "expected absence" >&2; false',
                                               'checked':'not_a_real_reader_123', 'action':'NEVER'}})
        response = engine.menu_query('>', 'setup')
        self.assertEqual(response['status'], 'ready', response['error'])
        self.assertEqual([row['value'] for row in response['items']], ['setup.available'])

    def test_optional_stock_flatpak_absence_is_false_not_a_menu_wide_failure(self):
        from unittest.mock import patch
        import shutil
        bash_dir = Path(self.directory.name) / 'bin'
        bash_dir.mkdir()
        bash = shutil.which('bash')
        self.assertIsNotNone(bash)
        (bash_dir / 'bash').symlink_to(bash or '/nonexistent-bash')
        engine = self.engine({'install': {},
                              'install.app': {'when':'! flatpak info missing.app', 'action':'NEVER'},
                              'remove': {}, 'remove.app': {'when':'flatpak info missing.app', 'action':'NEVER'}})
        with patch.dict(os.environ, {'PATH':str(bash_dir)}):
            response = engine.menu_query('>')
        self.assertEqual(response['status'], 'ready', response['error'])
        self.assertEqual([row['value'] for row in response['items']], ['install'])

    def test_guard_failure_is_explicit_and_fail_closed(self):
        import subprocess
        for condition in ('exit 2', 'not_a_real_guard_command_123', '[[ broken syntax'):
            with self.subTest(condition=condition):
                response = self.engine({'guarded': {'when':condition, 'action':'NEVER'}}).menu_query('>')
                self.assertEqual(response['items'], [])
                self.assertTrue(response['error'])
                self.assertNotEqual(response['status'], 'ready')
        def timeout(argv, timeout):
            raise subprocess.TimeoutExpired(argv, timeout)
        response = self.engine({'guarded': {'when':'true', 'action':'NEVER'}}, timeout).menu_query('>')
        self.assertEqual(response['items'], [])
        self.assertIn('guard', response['error'].lower())

    def test_hidden_ancestor_hides_descendants_and_empty_submenus(self):
        response = self.engine({
            'hidden': {'when':'false'}, 'hidden.child': {'action':'NEVER'},
            'empty': {}, 'visible': {'action':'NEVER'},
        }).menu_query('> child')
        self.assertEqual(response['items'], [])
        root = self.menu.MenuEngine(self.default).menu_query('>')
        self.assertEqual([row['value'] for row in root['items']], ['visible'])

    def test_guard_marker_incompleteness_cannot_allow_guarded_row(self):
        import subprocess
        def malformed(argv, timeout):
            return subprocess.CompletedProcess(argv, 0, 'fake:0:0\nfake:0:0\n', '')
        response = self.engine({'guarded': {'when':'true', 'action':'NEVER'}}, malformed).menu_query('>')
        self.assertEqual(response['items'], [])
        self.assertTrue(response['error'])


if __name__ == '__main__':
    unittest.main()
