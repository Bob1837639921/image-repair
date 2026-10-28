import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from storage_settings import StorageSettings


class StorageSettingsTests(unittest.TestCase):
    def fixture(self,folder,activate=lambda path:None,busy=lambda:False,**kwargs):
        root=Path(folder)/'app';root.mkdir();source=Path(folder)/'old-data';source.mkdir()
        (source/'originals').mkdir();(source/'originals'/'图.png').write_bytes(bytes(range(256))*32)
        (source/'repairs').mkdir();(source/'repairs'/'drafts.json').write_text('{}','utf-8')
        (source/'project.json').write_text('[{"id":"one"}]','utf-8')
        (root/'data-location.txt').write_text(str(source),'utf-8')
        return StorageSettings(root,source,activate,busy,**kwargs),root,source,Path(folder)/'new-data'

    def completed(self,manager):
        deadline=time.monotonic()+5
        while manager.status()['running'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(manager.status()['running'],'migration did not finish')
        return manager.status()

    def test_verified_migration_keeps_backup_and_persists_location(self):
        with tempfile.TemporaryDirectory() as folder:
            activated=[];manager,root,source,target=self.fixture(folder,activated.append)
            with manager.request():manager.start(str(target))
            state=self.completed(manager)
            self.assertEqual(state['phase'],'complete');self.assertEqual(state['done'],3)
            self.assertEqual(state['path'],str(target));self.assertEqual(activated,[target])
            self.assertEqual((root/'data-location.txt').read_text('utf-8').strip(),str(target))
            for path in source.rglob('*'):
                if path.is_file():self.assertEqual(path.read_bytes(),(target/path.relative_to(source)).read_bytes())
            self.assertTrue(source.exists(),'original folder is a retained backup')

    def test_busy_migration_rejects_edits_until_copy_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            manager,root,source,target=self.fixture(folder);entered=threading.Event();release=threading.Event()
            import shutil
            original=shutil.copyfileobj
            def blocked(reader,writer):entered.set();release.wait(3);original(reader,writer)
            with patch('storage_settings.shutil.copyfileobj',side_effect=blocked):
                with manager.request():manager.start(str(target))
                self.assertTrue(entered.wait(2))
                with self.assertRaises(ValueError):
                    with manager.request():pass
                self.assertEqual(manager.status()['path'],str(source))
                release.set();self.completed(manager)
            with manager.request():pass

    def test_failed_copy_keeps_original_configuration_and_data(self):
        with tempfile.TemporaryDirectory() as folder:
            activated=[];manager,root,source,target=self.fixture(folder,activated.append)
            with patch('storage_settings.shutil.copyfileobj',side_effect=OSError('no disk space')):
                manager.start(str(target));state=self.completed(manager)
            self.assertEqual(state['phase'],'error');self.assertEqual(state['path'],str(source))
            self.assertEqual(activated,[]);self.assertEqual((root/'data-location.txt').read_text('utf-8'),str(source))
            self.assertTrue((source/'originals'/'图.png').exists())

    def test_configuration_failure_rolls_back_live_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            activated=[];manager,root,source,target=self.fixture(folder,activated.append)
            with patch('storage_settings.os.replace',side_effect=OSError('read only config')):
                manager.start(str(target));state=self.completed(manager)
            self.assertEqual(state['phase'],'error');self.assertEqual(activated,[target,source])
            self.assertEqual(manager.current,source);self.assertEqual((root/'data-location.txt').read_text('utf-8'),str(source))

    def test_dangerous_or_occupied_destinations_and_active_tasks_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manager,root,source,target=self.fixture(folder)
            for invalid in ('','relative',str(source/'child'),str(source.parent),str(source.anchor),str(root)):
                with self.assertRaises(ValueError):manager.start(invalid)
            self.assertTrue(manager.start(str(source))['unchanged'])
            manager.busy=lambda:True
            with self.assertRaises(ValueError):manager.start(str(target))
            manager.busy=lambda:False
            with manager.request(),manager.request():
                with self.assertRaises(ValueError):manager.start(str(target))
            manager.environment_override=True
            self.assertFalse(manager.status()['can_change'])
            with self.assertRaises(ValueError):manager.start(str(target))


if __name__=='__main__':unittest.main()
