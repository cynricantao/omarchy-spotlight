"""Supplemental QML wiring checks; rendered acceptance is a separate gate."""
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


class MenuUiTests(unittest.TestCase):
    def test_native_navigation_uses_menu_context_and_no_stock_menu_fallback(self):
        source = (HERE / 'Spotlight.qml').read_text()
        for declaration in ('function enterMenu(', 'function backMenu(', 'property string menuId:',
                            'Logic.acceptMenuResponse(', '"menu-query"', 'function browse('):
            self.assertTrue(declaration in source, f'Missing native menu integration: {declaration}')
        self.assertIn('menuBreadcrumbs', source)
        self.assertIn('entry.kind === "menu-apps"', source)
        self.assertNotIn('omarchy-menu summon', source)

    def test_confirmation_defaults_to_cancel_and_does_not_execute(self):
        component = HERE / 'MenuConfirmation.qml'
        self.assertTrue(component.is_file(), 'Disruptive actions need a native confirmation surface')
        source = component.read_text()
        self.assertIn('cancelButton.forceActiveFocus()', source)
        self.assertIn('signal approved()', source)
        self.assertIn('signal dismissed()', source)
        self.assertIn('Text.PlainText', source)
        self.assertNotIn('execDetached', source)
        self.assertNotIn('Process {', source)
        parent = (HERE / 'Spotlight.qml').read_text()
        self.assertIn('Logic.confirmedSelection(', parent)
        self.assertIn('entry.requiresConfirmation === true', parent)
        self.assertIn('confirmationPending', parent)

    def test_source_glyphs_and_checked_state_render_without_rich_text(self):
        source = (HERE / 'ResultCard.qml').read_text()
        self.assertIn('iconKind === "glyph"', source)
        self.assertIn('entry.iconFont', source)
        self.assertIn('entry.checked', source)
        self.assertIn('entry.kind === "menu"', source)
        self.assertIn('Text.PlainText', source)


if __name__ == '__main__':
    unittest.main()
