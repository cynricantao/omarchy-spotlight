"""Backend/menu boundary tests with no installed menu, guard execution or launches."""
import contextlib
import io
import json
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch
import backend


class MenuIntegrationTests(unittest.TestCase):
    def test_actions_query_uses_complete_native_menu_not_legacy_curated_list(self):
        response = {'query': '> screenshot', 'menu': 'root', 'items': [], 'breadcrumbs': [], 'error': '', 'status': 'Ready'}
        menu = SimpleNamespace(menu_query=Mock(return_value=response))
        with patch.dict(sys.modules, {'omarchy_menu': menu}):
            self.assertIs(backend.query('> screenshot'), response)
        menu.menu_query.assert_called_once_with('> screenshot', 'root')

    def test_cli_routes_nested_menu_and_preserves_original_query(self):
        text = '> quotes " café $(never)  '
        response = {'query': text, 'menu': 'trigger.capture', 'items': [], 'error': '', 'status': 'Ready', 'breadcrumbs': []}
        menu = SimpleNamespace(menu_query=Mock(return_value=response))
        output = io.StringIO()
        with patch.dict(sys.modules, {'omarchy_menu': menu}), contextlib.redirect_stdout(output):
            self.assertEqual(backend.main(['menu-query', text, 'trigger.capture']), 0)
        self.assertEqual(json.loads(output.getvalue()), response)
        menu.menu_query.assert_called_once_with(text, 'trigger.capture')

    def test_activation_revalidates_the_native_selection_in_menu_module(self):
        entry = {'id': 'omarchy:learn.arch', 'kind': 'menu-action', 'value': 'learn.arch', 'actionToken': 'bound-token'}
        menu = SimpleNamespace(action_argv=Mock(return_value=['bash', '-c', 'trusted-from-disk']))
        with patch.dict(sys.modules, {'omarchy_menu': menu}):
            self.assertEqual(backend.action_argv(entry), ['bash', '-c', 'trusted-from-disk'])
        menu.action_argv.assert_called_once_with(entry)

    def test_navigation_selection_cannot_be_executed_by_backend(self):
        with self.assertRaises(ValueError):
            backend.action_argv({'id': 'omarchy:system', 'kind': 'menu', 'value': 'system'})


if __name__ == '__main__':
    unittest.main()
