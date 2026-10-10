"""Read-only home-view tests; no indexing, network, or action dispatch."""
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import os

HERE = Path(__file__).parent

class OverviewTests(unittest.TestCase):
    def test_overview_contains_only_real_apps_and_indexed_folders(self):
        self.assertTrue((HERE / 'overview.py').exists(), 'home overview is not implemented')
        spec = importlib.util.spec_from_file_location('overview', HERE / 'overview.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        b = module.backend
        fixture = Path(tempfile.mkdtemp(prefix='spotlight-home-', dir=os.environ.get('TMPDIR', tempfile.gettempdir())))
        home, data = fixture/'home', fixture/'data'
        (data/'applications').mkdir(parents=True)
        for name in ('Documents', 'Downloads', 'Projects'):
            (home/name).mkdir(parents=True)
        for filename,name in [('v.desktop','Vivaldi'),('h.desktop','Hermes'),('h2.desktop','Hermes'),('f.desktop','Files')]:
            (data/'applications'/filename).write_text('[Desktop Entry]\nType=Application\nName='+name+'\nExec=/bin/true\nIcon=application-x-executable\n')
        with patch.dict(os.environ, {'XDG_DATA_HOME':str(data), 'XDG_DATA_DIRS':str(fixture/'absent')}), patch.object(b,'cache_dir',return_value=fixture/'cache'):
            b.build_index(roots=[home], force=True)
            with patch.object(b,'build_index',side_effect=AssertionError('overview must not index')), patch.object(b.subprocess,'run',side_effect=AssertionError('no processes')):
                result = module.overview(home=home)
            self.assertEqual(result['query'],'')
            self.assertFalse(result['error'])
            self.assertEqual(result['items'][0]['value'],'home')
            apps=[x for x in result['items'] if x['kind']=='app']
            self.assertEqual({x['title'] for x in apps},{'Vivaldi','Hermes','Files'})
            self.assertEqual(len(apps),3)
            folders=[x for x in result['items'] if x['kind']=='folder']
            self.assertEqual({x['value'] for x in folders},{str(home/n) for n in ('Documents','Downloads','Projects')})
            self.assertTrue(all(Path(x['value']).exists() for x in apps+folders))
            self.assertFalse(any('ago' in x['subtitle'] for x in result['items']))

if __name__=='__main__': unittest.main()
