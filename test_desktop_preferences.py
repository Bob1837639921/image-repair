import json
import tempfile
import unittest
from pathlib import Path
from desktop_preferences import DesktopPreferences


class DesktopPreferencesTests(unittest.TestCase):
    def test_first_close_asks_then_remembered_choice_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            store=DesktopPreferences(folder)
            self.assertEqual(store.read()['close_action'],'ask')
            store.update(close_action='tray')
            DesktopPreferences(folder).update(width=1360,height=900,maximized=True)
            self.assertEqual(DesktopPreferences(folder).read()['close_action'],'tray')

    def test_settings_can_restore_prompt_without_losing_window_size(self):
        with tempfile.TemporaryDirectory() as folder:
            store=DesktopPreferences(folder)
            store.update(width=1200,close_action='exit')
            store.update(close_action='ask')
            self.assertEqual(store.read()['width'],1200)
            self.assertEqual(store.read()['close_action'],'ask')

    def test_invalid_choice_never_replaces_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store=DesktopPreferences(folder);store.update(close_action='tray')
            with self.assertRaises(ValueError):store.update(close_action='other')
            self.assertEqual(store.read()['close_action'],'tray')

    def test_corrupted_or_old_preferences_fall_back_to_ask(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'desktop-window.json'
            for text in ('{broken','[]',json.dumps(dict(width=1200))):
                path.write_text(text,'utf-8')
                self.assertEqual(DesktopPreferences(folder).read()['close_action'],'ask')

if __name__=='__main__':unittest.main()
