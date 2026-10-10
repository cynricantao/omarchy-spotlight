"""Public-release safety regressions; only isolated local fixtures are used."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import backend
import ai_settings


class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', tempfile.gettempdir()), prefix='spotlight-release-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        (self.home/'document.txt').touch()

    def test_index_refuses_insecure_cache_without_chmod(self):
        cache = self.root/'cache'
        cache.mkdir(mode=0o755)
        cache.chmod(0o755)
        with patch.object(backend,'cache_dir',return_value=cache):
            with self.assertRaises((ValueError,OSError)):
                backend.build_index(roots=[self.home],force=True)
        self.assertEqual(cache.stat().st_mode & 0o777,0o755)
        self.assertFalse((cache/'index.sqlite3').exists())

    def test_index_refuses_symlinked_cache_ancestor(self):
        real = self.root/'real'
        real.mkdir()
        alias = self.root/'alias'
        alias.symlink_to(real, target_is_directory=True)
        with patch.object(backend,'cache_dir',return_value=alias/'cache'):
            with self.assertRaises((ValueError,OSError)):
                backend.build_index(roots=[self.home],force=True)
        self.assertFalse((real/'cache').exists())

    def test_index_read_does_not_follow_database_symlink(self):
        cache=self.root/'cache';cache.mkdir(mode=0o700)
        target=self.root/'other.sqlite3';target.write_bytes(b'not a database')
        (cache/'index.sqlite3').symlink_to(target)
        with patch.object(backend,'cache_dir',return_value=cache):
            with self.assertRaises((ValueError,OSError)):
                backend.index_connection()
        self.assertEqual(target.read_bytes(),b'not a database')

    def test_ai_settings_refuse_symlinked_parent(self):
        real=self.root/'real';real.mkdir()
        alias=self.root/'alias';alias.symlink_to(real,target_is_directory=True)
        with patch.object(ai_settings,'config_path',return_value=alias/'settings.json'), patch.object(ai_settings,'_default_agent',return_value='codex'), patch.object(ai_settings.shutil,'which',return_value='/bin/true'):
            result=ai_settings.save({'provider':'codex'})
            self.assertFalse(result['ok'])
        self.assertFalse((real/'settings.json').exists())

    def test_ai_settings_refuse_group_writable_file(self):
        path=self.root/'settings.json'
        path.write_text('{"version":1,"provider":"codex","custom_argv":[]}')
        path.chmod(0o666)
        with patch.object(ai_settings,'config_path',return_value=path):
            with self.assertRaises(ValueError):
                ai_settings.launch_argv('hello')
        self.assertEqual(path.stat().st_mode & 0o777,0o666)

    def test_custom_template_rejects_env_wrapped_shell_evaluation(self):
        with self.assertRaises(ValueError):
            ai_settings._validate_custom(['env','bash','-c','{prompt}'])

if __name__=='__main__': unittest.main()
