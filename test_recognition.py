import io
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from PIL import Image
from recognition import RecognitionService,read_artwork,validate_result,detail_boxes,merge_author_readings,recognition_options,match_roster
from repairing import crop_signature


def reading(**changes):
    result=dict(calligrapher='测试书写者',title='春晓',text_author='孟浩然',inscription='测试书写者书',body_excerpt='春眠不觉晓',author_status='clear',title_status='clear',author_evidence='落款末行姓名清楚',title_evidence='正文为春晓诗句',notes='',candidates=[],signature_region=[0,.6,.3,1])
    result.update(changes);return result


class RecognitionTests(unittest.TestCase):
    def service(self,reader):
        item=dict(id='one',file='unchanged.png',name='会员_013_原编号.png',points=[[0,0],[1,0],[1,1],[0,1]],rotation=0,settings={},trim={},revision=3)
        items=[item];saved=[]
        service=RecognitionService(lambda key:deepcopy(next(i for i in items if i['id']==key)),lambda _:Image.new('RGB',(120,360),'ivory'),lambda:('secret','http://test.invalid/v1','gpt-6.1-sol'),threading.RLock(),lambda:saved.append(True),items,reader)
        return service,item,saved

    def wait(self,service):
        for _ in range(200):
            if not service.job['running']:return
            time.sleep(.005)
        self.fail('recognition job did not finish')

    def test_uncertain_names_remain_candidates(self):
        value=validate_result(reading(author_status='uncertain'))
        self.assertEqual(value['calligrapher'],'');self.assertEqual(value['candidates'][0]['value'],'测试书写者')
        self.assertEqual(value['text_author'],'孟浩然')
        self.assertEqual(validate_result(reading(signature_region=[0,float('nan'),1,1]))['signature_region'],None)

    def test_request_uses_multiscale_images_and_text_not_image_generation(self):
        result=dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(reading(),ensure_ascii=False))])])
        with patch('recognition.urllib.request.urlopen',side_effect=lambda *a,**kw:io.BytesIO(json.dumps(result).encode())) as mock:
            with Image.new('RGB',(100,800),'ivory') as image:value=read_artwork(image,('secret','http://test.invalid/v1','gpt-6.1-sol'))
        self.assertEqual(mock.call_count,2)
        request=mock.call_args_list[0].args[0];body=json.loads(request.data)
        verification=json.loads(mock.call_args_list[1].args[0].data)
        self.assertNotIn("测试书写者",json.dumps(verification,ensure_ascii=False))
        self.assertTrue(request.full_url.endswith('/responses'));self.assertNotIn('tools',body)
        self.assertEqual(sum(p['type']=='input_image' for p in body['input'][0]['content']),5)
        self.assertEqual(value['calligrapher'],'测试书写者');self.assertFalse(body['store'])
        self.assertNotIn('会员_013',json.dumps(body,ensure_ascii=False))

    def test_roster_match_never_rewrites_reading(self):
        original=validate_result(reading(calligrapher='娄梅芳'))
        exact=match_roster(original,['娄梅芳','娄梅芬'])
        self.assertEqual(exact['roster_match']['status'],'exact')
        fuzzy=match_roster(original,['娄梅芬'])
        self.assertEqual(fuzzy['calligrapher'],'娄梅芳')
        self.assertEqual(fuzzy['roster_match']['status'],'review')
        self.assertEqual(fuzzy['roster_match']['names'],['娄梅芬'])
        self.assertEqual(match_roster(original,['王先生'])['roster_match']['status'],'unmatched')

    def test_options_validate_coordinates_and_names(self):
        self.assertEqual(recognition_options({'authors':[' 张三 ','张三']})['authors'],['张三'])
        for box in ([0,0,0,1],[0,0,2,1],[0,False,1,1],[0,0,float('nan'),1]):
            with self.assertRaises(ValueError):recognition_options({'region':box})
        with self.assertRaises(ValueError):recognition_options({'authors':['a']*501})

    def test_manual_signature_overrides_detection_without_sending_roster(self):
        first=validate_result(reading(signature_region=None))
        with patch('recognition.request_reading',side_effect=[first,validate_result(reading())]) as request:
            with Image.new('RGB',(500,1000)) as image:
                value=read_artwork(image,('secret','http://test.invalid','gpt-6.1-sol'),options={'region':[.1,.2,.4,.8],'authors':['私有名单姓名']})
        self.assertEqual(request.call_count,2)
        self.assertEqual(value['signature_region'],[.1,.2,.4,.8])
        self.assertNotIn('私有名单姓名',str(request.call_args_list))

    def test_author_conflict_preserves_both_candidates_and_title(self):
        first=validate_result(reading(calligrapher='娄梅芳'))
        second=validate_result(reading(calligrapher='葉恆芳'))
        result=merge_author_readings(first,second)
        self.assertEqual(result['calligrapher'],'')
        self.assertEqual(result['author_status'],'uncertain')
        self.assertEqual({c['value'] for c in result['candidates']},{'娄梅芳','葉恆芳'})
        self.assertEqual(result['title'],'春晓')
        self.assertEqual(result['signature_region'],first['signature_region'])

    def test_unclear_closeup_does_not_confirm_first_guess(self):
        result=merge_author_readings(validate_result(reading()),validate_result(reading(calligrapher='',author_status='unknown')))
        self.assertEqual(result['calligrapher'],'')
        self.assertEqual(result['author_status'],'uncertain')

    def test_verification_failure_preserves_work_and_marks_author_uncertain(self):
        payload=json.dumps({'output_text':json.dumps(reading())}).encode()
        with patch('recognition.urllib.request.urlopen',side_effect=[io.BytesIO(payload),OSError('offline')]):
            with Image.new('RGB',(100,800)) as image:result=read_artwork(image,('secret','http://test.invalid','gpt-6.1-sol'))
        self.assertEqual(result['title'],'春晓')
        self.assertEqual(result['calligrapher'],'')
        self.assertIn('复核未完成',result['notes'])

    def test_preview_never_changes_original_identity_and_adoption_is_explicit(self):
        service,item,saved=self.service(lambda *_:validate_result(reading()))
        before=deepcopy(item);signature=crop_signature(item)
        service.start('one',signature);self.wait(service)
        self.assertNotIn('artwork_metadata',item)
        self.assertEqual(item['name'],before['name']);self.assertEqual(item['points'],before['points'])
        candidate=item['recognition_candidate']
        service.adopt('one',candidate['token'],signature,dict(calligrapher='人工核对姓名',title='春晓',text_author='孟浩然'))
        self.assertEqual(item['artwork_metadata']['calligrapher'],'人工核对姓名')
        self.assertEqual(item['file'],before['file']);self.assertEqual(item['revision'],before['revision'])
        self.assertEqual(len(saved),2)

    def test_crop_change_rejects_inflight_result_and_duplicate_start(self):
        entered=threading.Event();release=threading.Event()
        def reader(*_):entered.set();release.wait(2);return validate_result(reading())
        service,item,_=self.service(reader);signature=crop_signature(item)
        service.start('one',signature);self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(ValueError):service.start('one',signature)
            item['rotation']=90
        finally:release.set()
        self.wait(service)
        self.assertNotIn('recognition_candidate',item);self.assertEqual(service.job['phase'],'error')

    def test_old_result_cannot_be_adopted_after_crop_changes(self):
        service,item,_=self.service(lambda *_:validate_result(reading()))
        signature=crop_signature(item);service.start('one',signature);self.wait(service)
        token=item['recognition_candidate']['token'];item['rotation']=90
        with self.assertRaises(ValueError):service.adopt('one',token,signature,dict(title='春晓'))
        self.assertNotIn('artwork_metadata',item);self.assertTrue(service.status('one')['stale'])

    def test_invalid_response_is_not_silently_treated_as_success(self):
        with patch('recognition.urllib.request.urlopen',return_value=io.BytesIO(b'{"output":[]}')):
            with Image.new('RGB',(20,40)) as image:
                with self.assertRaisesRegex(ValueError,'未返回识读文字'):read_artwork(image,('secret','http://test.invalid','gpt-6.1-sol'))

    def test_detail_tiles_cover_entire_work_in_both_orientations(self):
        for size in ((400,4000),(4000,400),(400,400)):
            boxes=detail_boxes(size)
            for x,y in ((0,0),(.5,.5),(1,1),(.03,.95),(.96,.04)):
                self.assertTrue(any(a<=x<=c and b<=y<=d for a,b,c,d in boxes))

    def test_live_api_reads_details_then_saves_only_reviewed_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'SCROLL_STUDIO_DATA':folder}):
                spec=importlib.util.spec_from_file_location('recognition_api_test',Path(__file__).with_name('server.py'))
                app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
            app.RECOGNITION.reader=lambda *_:validate_result(reading())
            app.RECOGNITION.connection=lambda:('test-key','http://test.invalid','gpt-6.1-sol')
            http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            url=f'http://127.0.0.1:{http.server_port}'
            def post(path,body):
                request=urllib.request.Request(url+'/api/'+path,data=json.dumps(body).encode(),headers={'X-App-Token':app.TOKEN},method='POST')
                return json.load(urllib.request.urlopen(request))
            try:
                with self.assertRaises(OSError):app.ThreadingHTTPServer(('127.0.0.1',http.server_port),app.Handler)
                image=io.BytesIO();Image.new('RGB',(100,500),'ivory').save(image,'PNG')
                item=app.import_image('original.png',image.getvalue());signature=crop_signature(item)
                with urllib.request.urlopen(url+'/api/recognition/image/'+item['id']+'?part=2&signature='+signature) as response:
                    self.assertEqual(response.headers['Content-Type'],'image/jpeg')
                    with Image.open(io.BytesIO(response.read())) as detail:self.assertLess(detail.height,500)
                with urllib.request.urlopen(url+'/api/recognition/image/'+item['id']+'?part=overview&detail=1&signature='+signature) as response:
                    self.assertEqual(response.headers['Content-Type'],'image/png')
                    with Image.open(io.BytesIO(response.read())) as detail:self.assertEqual(detail.size,(100,500))
                post('settings/authors',dict(source='Word作者表.docx',authors=['名单作者']))
                roster=json.load(urllib.request.urlopen(url+'/api/settings/authors'))
                self.assertEqual(roster['authors'],['名单作者'])
                post('recognition/start',dict(id=item['id'],signature=signature,options={'authors':['过时浏览器名单']}));self.wait(app.RECOGNITION)
                self.assertEqual(app.find(item['id'])['recognition_candidate']['options']['authors'],['名单作者'])
                status=json.load(urllib.request.urlopen(url+'/api/recognition/status/'+item['id']))
                result=post('recognition/adopt',dict(id=item['id'],signature=signature,token=status['candidate']['token'],fields=dict(title='春晓')))
                self.assertEqual(result['name'],'original.png');self.assertEqual(result['artwork_metadata']['title'],'春晓')
                self.assertEqual((Path(folder)/'originals'/item['file']).read_bytes(),image.getvalue())
            finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main()
