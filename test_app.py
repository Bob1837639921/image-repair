import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from imaging import render, validate, detect, refine_native, suggest_trim, validate_trim, automatic_process, FULL


class GeometryTests(unittest.TestCase):
    def test_already_framed_weak_inset_keeps_full_image(self):
        candidate=dict(points=[[0,0],[.895,0],[1,1],[0,1]],edge_support=[0,0,.6,0])
        with patch('imaging.detect',return_value=[candidate]):
            result=automatic_process('unused.png')
        self.assertEqual(result['points'],FULL)
        self.assertFalse(any(result['trim'].values()))

    def test_curved_pale_fringe_and_ink_guard(self):
        im=Image.new('RGB',(400,1200),'#bc1826');draw=ImageDraw.Draw(im)
        draw.polygon([(0,0),(399,0),(399,2),(200,6),(0,2)],fill='#eeeecc')
        suggestion=suggest_trim(im)['trim']
        self.assertGreater(suggestion['top'],0)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'red.png';im.save(p)
            cropped=render(p,FULL,trim=suggestion)
            self.assertLess(cropped.height,im.height)
            self.assertEqual(cropped.getpixel((200,0)),(188,24,38))
        draw.rectangle((80,0,180,12),fill='black')
        self.assertEqual(suggest_trim(im)['trim']['top'],0)
        self.assertFalse(any(suggest_trim(Image.new('RGB',(400,1200),'#ddddc9'))['trim'].values()))
        with self.assertRaises(ValueError):validate_trim({'left':float('nan')})

    def test_fringe_in_multiple_colours_on_red_and_pale_paper(self):
        for paper in ('#bc1826','#e7debd'):
            for border in ('#e8db55','#4682bb','#dddddd'):
                with self.subTest(paper=paper,border=border):
                    im=Image.new('RGB',(400,1200),paper);draw=ImageDraw.Draw(im)
                    draw.polygon([(0,0),(8,0),(12,600),(8,1199),(0,1199)],fill=border)
                    trim=suggest_trim(im)['trim']
                    self.assertGreater(trim['left'],.02)
                    self.assertEqual(trim['right'],0)
                    self.assertLessEqual(trim['left'],.05)
        im=Image.new('RGB',(400,1200),'#e7debd')
        ImageDraw.Draw(im).rectangle((0,500,10,540),fill='#cc2222')
        self.assertEqual(suggest_trim(im)['trim']['left'],0,'isolated stamp must not become a border')

    def test_native_edge_refinement(self):
        im=Image.new('RGB',(2400,3200),'#9e9c96')
        actual=np.array([[710,130],[1700,150],[1680,3060],[700,3040]],dtype=float)
        ImageDraw.Draw(im).polygon([tuple(p) for p in actual],fill='#ddd7c7')
        coarse=actual+np.array([[-12,-10],[11,-12],[13,12],[-11,10]])
        result=refine_native(im,(coarse/[2399,3199]).tolist())
        refined=np.asarray(result['points'])*[2399,3199]
        self.assertLess(np.mean(np.linalg.norm(refined-actual,axis=1)),5)

    def test_native_uniform_falls_back(self):
        im=Image.new('RGB',(800,1200),'#ddd7c7')
        points=[[.2,.1],[.8,.1],[.8,.9],[.2,.9]]
        self.assertTrue(np.allclose(refine_native(im,points)['points'],points))

    def test_whole_frame_preserves_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.png'; Image.new('RGB',(320,640),'white').save(p)
            self.assertEqual(render(p,FULL).size,(320,640))
            self.assertEqual(render(p,FULL,90).size,(640,320))

    def test_crossing_rejected(self):
        with self.assertRaises(ValueError): validate([[0,0],[1,1],[1,0],[0,1]])

    def test_perspective_detection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.png'; im=Image.new('RGB',(600,800),'#333333')
            ImageDraw.Draw(im).polygon([(140,70),(460,100),(490,730),(110,700)],fill='#e3d6ad')
            im.save(p); result=detect(p)
            self.assertTrue(result)
            self.assertLess(np.mean(np.abs(np.array(result[0]['points'])-np.array([[140/599,70/799],[460/599,100/799],[490/599,730/799],[110/599,700/799]]))),.035)

    def test_import_edit_export(self):
        with tempfile.TemporaryDirectory() as d:
            env={**os.environ,'SCROLL_STUDIO_DATA':d}
            process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('server.py')),'--no-browser','--port','18765'],env=env,stdout=subprocess.DEVNULL)
            try:
                base='http://127.0.0.1:18765'
                for _ in range(60):
                    try:
                        html=urllib.request.urlopen(base).read().decode(); break
                    except Exception: time.sleep(.1)
                else: self.fail('server did not start')
                token=html.split("window.APP_TOKEN='")[1].split("'")[0]
                def post(path,body,raw=False):
                    req=urllib.request.Request(base+'/api/'+path,data=body if raw else json.dumps(body).encode(),headers={'X-App-Token':token},method='POST')
                    return json.load(urllib.request.urlopen(req))
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(urllib.request.Request(base+'/api/export',data=b'{}',method='POST'))
                buf=io.BytesIO(); Image.new('RGB',(300,1800),'#d9cfb4').save(buf,'PNG')
                item=post('import?name=sample.png',buf.getvalue(),True)
                self.assertTrue((Path(d)/'previews'/f"{item['id']}_0_result_v0.jpg").exists())
                post('prepare',{})
                for _ in range(100):
                    prepared=json.load(urllib.request.urlopen(base+'/api/prepare-job'))
                    if not prepared['running']:break
                    time.sleep(.05)
                self.assertEqual(prepared['done'],prepared['total'])
                self.assertFalse(prepared['errors'])
                response=urllib.request.urlopen(base+'/api/image/'+item['id']+'?mode=detail')
                self.assertEqual(response.headers.get_content_type(),'image/png')
                with Image.open(io.BytesIO(response.read())) as detail:
                    self.assertEqual(detail.size,(300,1800))
                    self.assertEqual(detail.getpixel((20,20)),(217,207,180))
                with self.assertRaises(urllib.error.HTTPError):
                    post('repair/preview',{'id':item['id'],'region':[.2,.2,.7,.7]})
                item['confirmed']=True; post('update',item)
                info=json.load(urllib.request.urlopen(base+'/api/repair/info/'+item['id']))
                self.assertEqual(info['size'],[300,1800])
                draft=post('repair/preview',{'id':item['id'],'region':[.2,.2,.7,.7],'method':'local'})
                repaired=post('repair/accept',{'id':item['id'],'draft':draft['draft']})
                self.assertEqual(len(repaired['repair_state']['layers']),1)
                undone=post('repair/undo',{'id':item['id']})
                self.assertEqual(undone['repair_state']['layers'],[])
                post('repair/redo',{'id':item['id']})
                completed=post('repair/complete',{'id':item['id']})
                self.assertTrue(completed['repair_state']['completed'])
                response=urllib.request.urlopen(base+'/api/repair/image/'+item['id']+'?detail=1')
                self.assertEqual(response.headers.get_content_type(),'image/png')
                config=post('repair/config',{'base_url':'http://127.0.0.1:8317/v1','key':'test-secret','model':'proxy-image-model'})
                self.assertTrue(config['configured'])
                self.assertNotIn('test-secret',json.dumps(config))
                self.assertNotIn('key',json.load(urllib.request.urlopen(base+'/api/repair/config')))
                post('export',{'format':'png'})
                for _ in range(100):
                    job=json.load(urllib.request.urlopen(base+'/api/job'))
                    if not job['running']: break
                    time.sleep(.1)
                self.assertFalse(job['running']); self.assertEqual(job['errors'],[])
                output=next(Path(job['folder']).glob('*.png'))
                with Image.open(output) as im: self.assertEqual(im.size,(300,1800))
                self.assertTrue((Path(d)/'project.json').exists())
                buf=io.BytesIO(); source=Image.new('RGB',(600,800),'#333333')
                ImageDraw.Draw(source).polygon([(140,70),(460,100),(490,730),(110,700)],fill='#e3d6ad')
                source.save(buf,'PNG')
                automatic=post('import?name=uncropped.png',buf.getvalue(),True)
                self.assertTrue(automatic['candidates'])
                self.assertEqual(automatic['points'],automatic['candidates'][0]['points'])
                self.assertFalse(automatic['confirmed'])
                self.assertIn('auto_result',automatic)
                self.assertIn('trim',automatic)
                processed=post('process',{'id':automatic['id']})
                self.assertEqual(processed['points'],processed['candidates'][0]['points'])
                self.assertEqual(processed['before_auto']['points'],automatic['points'])
                self.assertIn('needs_review',processed['auto_result'])
                ensured=post('process',{'id':automatic['id'],'only_if_needed':True})
                self.assertEqual(ensured['revision'],processed['revision'])
                self.assertEqual(ensured['points'],processed['points'])
                refined=post('refine',{'id':automatic['id']})
                self.assertEqual(refined['candidates'][1]['points'],processed['points'])
                self.assertEqual(refined['candidates'][0]['method'],'native')
                self.assertFalse(refined['confirmed'])
                suggested=post('trim',{'id':automatic['id']})
                self.assertIn('trim',suggested['item'])
                post('update',{**item,'points':[[.1,.05],[.9,.05],[.9,.95],[.1,.95]],'confirmed':False})
                preserved=post('process',{'id':item['id'],'only_if_needed':True})
                self.assertTrue(np.allclose(preserved['points'],[[.1,.05],[.9,.05],[.9,.95],[.1,.95]]))
                weak=post('process',{'id':item['id']})
                self.assertEqual(weak['points'],preserved['points'])
                self.assertTrue(weak['auto_result']['needs_review'])
                original_backup=weak['before_auto']
                repeated=post('process',{'id':item['id']})
                self.assertEqual(repeated['before_auto'],original_backup)
                item['trim']={'left':.01,'right':.02,'top':.01,'bottom':.02}
                item['confirmed']=True;post('update',item)
                with Image.open(io.BytesIO(urllib.request.urlopen(base+'/api/image/'+item['id']+'?mode=result').read())) as updated_preview:
                    self.assertEqual(updated_preview.size,(259,1552))
                post('export',{'format':'png'})
                for _ in range(100):
                    job=json.load(urllib.request.urlopen(base+'/api/job'))
                    if not job['running']:break
                    time.sleep(.1)
                self.assertFalse(job['errors'])
                with Image.open(next(Path(job['folder']).glob('*.png'))) as trimmed:
                    self.assertEqual(trimmed.size,(291,1746))
            finally:
                process.terminate(); process.wait(timeout=10)


if __name__=='__main__': unittest.main(verbosity=2)
