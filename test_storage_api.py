"""Exercise a live server's folder switch using disposable data only."""
import importlib.util
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from storage_settings import StorageSettings


class StorageAPITests(unittest.TestCase):
    def test_live_switch_keeps_pending_repairs_and_exports_to_new_location(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'old';app=root/'app';app.mkdir();target=root/'new'
            with patch.dict(os.environ,{'SCROLL_STUDIO_DATA':str(source)}):
                spec=importlib.util.spec_from_file_location('storage_test_server',Path(__file__).with_name('server.py'))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.STORAGE=StorageSettings(app,source,module.activate_storage,lambda:module.JOB['running'] or module.PREPARE['running'] or module.BATCH.job['running'])
            http=module.ThreadingHTTPServer(('127.0.0.1',0),module.Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{http.server_address[1]}'
            def get(path):return json.load(urllib.request.urlopen(base+'/api/'+path))
            def post(path,body):
                request=urllib.request.Request(base+'/api/'+path,data=json.dumps(body).encode(),headers={'X-App-Token':module.TOKEN},method='POST')
                return json.load(urllib.request.urlopen(request))
            try:
                buffer=io.BytesIO();Image.new('RGB',(100,200),'#d8cfb4').save(buffer,'PNG');original=buffer.getvalue()
                request=urllib.request.Request(base+'/api/import?name=sample.png',data=original,headers={'X-App-Token':module.TOKEN},method='POST')
                item=json.load(urllib.request.urlopen(request));item['confirmed']=True;post('update',item)
                info=get('repair/info/'+item['id'])
                marks=[dict(id='one',kind='crease',level='strong',region=[.2,.2,.8,.6])]
                post('repair/marks',dict(id=item['id'],signature=info['signature'],regions=marks))
                preview=post('repair/preview',dict(id=item['id'],regions=marks))
                post('settings/storage',dict(path=str(target)))
                for _ in range(200):
                    storage=get('settings/storage')
                    if not storage['running']:break
                    time.sleep(.01)
                self.assertEqual(storage['phase'],'complete');self.assertEqual(module.DATA,target)
                self.assertEqual((target/'originals'/item['file']).read_bytes(),original)
                self.assertTrue((source/'originals'/item['file']).exists())
                self.assertEqual((app/'data-location.txt').read_text('utf-8').strip(),str(target))
                self.assertEqual(get('repair/pending/'+item['id'])['draft'],preview['draft'])
                adopted=post('repair/accept',dict(id=item['id'],draft=preview['draft']))
                self.assertEqual(len(adopted['repair_state']['layers']),1)
                post('repair/complete',dict(id=item['id']))
                post('export',dict(format='png',stage='repair'))
                for _ in range(200):
                    job=get('job')
                    if not job['running']:break
                    time.sleep(.01)
                self.assertFalse(job['errors']);self.assertTrue(Path(job['folder']).is_relative_to(target/'exports'))
                self.assertEqual(len(list(Path(job['folder']).glob('*.png'))),1)
            finally:http.shutdown();http.server_close();thread.join(2)


if __name__=='__main__':unittest.main()
