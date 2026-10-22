import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from imaging import FULL,DEFAULTS
from repairing import RepairService,crop_signature
from repair_batch import RepairBatch


class BatchTests(unittest.TestCase):
    def setup_service(self,root):
        source=root/'source.png';Image.new('RGB',(100,200),'#d8cfb4').save(source)
        items=[dict(id=str(n),name=f'work-{n}',file='source.png',points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0) for n in range(3)]
        for item in items:item['repair_marks']=dict(signature=crop_signature(item),regions=[dict(id='m1',region=[.2,.2,.6,.6],kind='crease')])
        service=RepairService(root,lambda key:json.loads(json.dumps(next(i for i in items if i['id']==key))),lambda i:source,threading.RLock(),lambda:None,items)
        service.key='test-only';return service,items

    def wait_done(self,batch):
        for _ in range(100):
            if not batch.status()['running']:return
            time.sleep(.02)
        self.fail('queue did not finish')

    def test_multiple_results_persist_review_and_never_auto_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service,items=self.setup_service(root);batch=RepairBatch(root,service)
            with patch('repairing.ai_repair',side_effect=lambda image,*args:image.copy()) as ai:
                batch.start(['0','1'],2);self.wait_done(batch)
                self.assertEqual(ai.call_count,2)
            self.assertTrue(all(e['status']=='ready' for e in batch.status()['entries']))
            self.assertTrue(all('repair_state' not in item for item in items))
            second,_=self.setup_service(root);second.items=items;restored=RepairBatch(root,second)
            self.assertEqual(len(second.drafts),2)
            entry=restored.status()['entries'][0];self.assertEqual(entry['status'],'ready')
            with Image.open(second.folder/second.drafts[entry['draft']]['file']) as image:self.assertEqual(image.size,(100,200))
            second.post('accept',dict(id=entry['id'],draft=entry['draft']))
            self.assertEqual(restored.status()['entries'][0]['status'],'reviewed')
            self.assertNotIn(entry['id'],[e['id'] for e in restored.candidates()])

    def test_cancel_and_stale_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service,items=self.setup_service(root);batch=RepairBatch(root,service);entered=threading.Event();release=threading.Event()
            def fake(image,*args):entered.set();release.wait(3);return image.copy()
            with patch('repairing.ai_repair',side_effect=fake) as ai:
                batch.start(['0','1','2'],1);self.assertTrue(entered.wait(2));batch.cancel();release.set();self.wait_done(batch)
                self.assertEqual(ai.call_count,1)
            self.assertEqual([e['status'] for e in batch.status()['entries']],['ready','cancelled','cancelled'])
            items[0]['trim']={'left':.01}
            self.assertEqual(batch.status()['entries'][0]['status'],'stale')

    def test_errors_isolated_and_restart_does_not_repeat_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service,items=self.setup_service(root);batch=RepairBatch(root,service)
            with patch('repairing.ai_repair',side_effect=[ValueError('bad image'),Image.new('RGB',(100,200),'#d8cfb4')]):batch.start(['0','1'],1);self.wait_done(batch)
            self.assertEqual([e['status'] for e in batch.status()['entries']],['failed','ready'])
            batch.job['entries'][0]['status']='running';batch.job['running']=True;batch.persist()
            restored=RepairBatch(root,service);self.assertFalse(restored.status()['running']);self.assertEqual(restored.status()['entries'][0]['status'],'interrupted')


if __name__=='__main__':unittest.main()
