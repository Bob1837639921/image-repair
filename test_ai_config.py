import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from ai_config import save_connection,load_connection
from repairing import RepairService


@unittest.skipUnless(os.name=='nt','Windows DPAPI tests')
class ConnectionPersistenceTests(unittest.TestCase):
    def test_dpapi_roundtrip_no_plaintext_and_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ai-connection.json'
            save_connection(path,'http://127.0.0.1:8317/v1','image-model','test-only-secret-123')
            self.assertNotIn('test-only-secret-123',path.read_text('utf-8'))
            self.assertEqual(load_connection(path)['key'],'test-only-secret-123')
            save_connection(path,'http://127.0.0.1:8317/v1','image-model','')
            self.assertEqual(load_connection(path)['key'],'')

    def test_service_restart_reads_connection_and_keeps_key_private(self):
        with tempfile.TemporaryDirectory() as directory:
            def service():return RepairService(Path(directory),lambda x:None,lambda x:None,threading.RLock(),lambda:None,[])
            first=service();first.post('config',dict(base_url='http://127.0.0.1:8317/v1',model='custom-image-model',key='private-test-key'))
            second=service();self.assertEqual(second.key,'private-test-key');self.assertEqual(second.model,'custom-image-model')
            self.assertTrue(second.config()['persisted']);self.assertNotIn('private-test-key',json.dumps(second.config()))
            second.post('config',dict(model='another-image-model'))
            self.assertEqual(service().key,'private-test-key','empty UI field must keep the stored key')
            broken=Path(directory)/'ai-connection.json';broken.write_text('{invalid','utf-8')
            self.assertTrue(service().config()['warning']);self.assertEqual(broken.read_text('utf-8'),'{invalid')


if __name__=='__main__':unittest.main()
