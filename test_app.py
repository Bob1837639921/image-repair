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
from imaging import render, validate, detect, refine_native, suggest_trim, validate_trim, automatic_process, same_colour_sheet, FULL


class GeometryTests(unittest.TestCase):
    def test_faint_seal_just_outside_edge_is_kept(self):
        from imaging import protect_crossing_marks
        im=Image.new('RGB',(600,1000),'#deddd2')
        draw=ImageDraw.Draw(im)
        draw.rectangle((150,20,465,980),fill='#e6e4d8')
        draw.rectangle((445,75,455,102),outline='#b9948c',width=2)
        result=protect_crossing_marks(im,[[150/599,.02],[440/599,.02],[440/599,.98],[150/599,.98]])
        self.assertGreater(result['points'][1][0]*599,455)

    def test_reviewed_reference_is_applied_only_to_matching_source(self):
        import server
        points=[[.2,.1],[.8,.1],[.8,.9],[.2,.9]]
        for rotation in (0,90):
            old=dict(id='reference-test',file='sample.png',name='sample.png',width=600,height=800,points=FULL,rotation=rotation,confirmed=False,revision=0,crop_reference=dict(points=points,rotation=0,source_file='sample.png'))
            target=dict(old)
            fallback=dict(points=FULL,trim=validate_trim(),candidates=[],auto_result={})
            with patch.object(server,'find',return_value=dict(old)),patch.object(server,'source',return_value='unused.png'),patch.object(server,'automatic_process',return_value=fallback) as process,patch.object(server,'ITEMS',[target]),patch.object(server,'save'):
                result=server.process_item(old['id'])
            if rotation==0:
                self.assertTrue(np.allclose(result['points'],points))
                self.assertFalse(any(result['trim'].values()))
                process.assert_not_called()
            else:process.assert_called_once()

    def test_fringe_cannot_remove_small_seal_or_faint_stroke(self):
        for ink in ('#b64a36','#68614f'):
            im=Image.new('RGB',(600,1600),'#e7debd')
            draw=ImageDraw.Draw(im)
            draw.rectangle((0,0,12,1599),fill='#eeeeee')
            draw.rectangle((5,700,17,714),fill=ink)
            self.assertEqual(suggest_trim(im)['trim']['left'],0)

    def test_explicit_crop_applies_reviewable_new_corners(self):
        import server
        old=dict(id='crop-test',name='sample.png',width=600,height=800,points=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]],trim={},rotation=0,confirmed=False,revision=0)
        points=[[.25,.08],[.75,.1],[.78,.94],[.23,.92]]
        detected=dict(points=points,trim=validate_trim(),candidates=[dict(points=points)],auto_result=dict(needs_review=True,note='部分纸边不清晰'))
        target=dict(old)
        with patch.object(server,'find',return_value=dict(old)), patch.object(server,'source',return_value='unused.png'), patch.object(server,'automatic_process',return_value=detected) as process, patch.object(server,'ITEMS',[target]), patch.object(server,'save'):
            result=server.process_item('crop-test')
        process.assert_called_once_with('unused.png',0,None)
        self.assertEqual(result['points'],points)
        self.assertTrue(result['auto_result']['needs_review'])
        self.assertEqual(result['before_auto']['points'],old['points'])

    def test_dense_ink_and_lighting_do_not_select_brocade(self):
        h,w=1100,825
        lab=np.empty((h,w,3),dtype=np.uint8)
        yy,xx=np.indices((h,w))
        lab[:]=[175,128,128]
        lab[:,:,0]=np.where(((xx//12+yy//20)%2)==0,170,205)
        lab[30:1070,220:610]=[210,128,128]
        lab[50:1050,285:540,0]=np.linspace(210,170,1000)[:,None]
        lab[50:1050,285:540,1:]=[126,151]
        import cv2
        image=Image.fromarray(cv2.cvtColor(lab,cv2.COLOR_LAB2RGB))
        draw=ImageDraw.Draw(image)
        for x in range(300,530,35):
            for y in range(65,1040,22):
                draw.line([(x,y),(x+13,y+8),(x+4,y+15),(x+15,y+18)],fill='#242424',width=3)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'dense.png';image.save(path)
            points=np.asarray(detect(path)[0]['points'])*[w-1,h-1]
        expected=np.array([[285,50],[539,50],[539,1049],[285,1049]])
        self.assertLess(np.max(np.linalg.norm(points-expected,axis=1)),12)

    def test_already_framed_weak_inset_keeps_full_image(self):
        candidate=dict(points=[[0,0],[.895,0],[1,1],[0,1]],edge_support=[0,0,.6,0])
        with patch('imaging.detect',return_value=[candidate]),patch('imaging.same_colour_sheet',return_value=None):
            result=automatic_process('unused.png')
        self.assertEqual(result['points'],FULL)
        self.assertFalse(any(result['trim'].values()))

    def test_same_colour_fallback_rejects_rules_and_protects_outer_ink(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'paper.png'
            # Two printed rules on a finished sheet are not paper boundaries.
            im=Image.new('RGB',(1000,750),'#bbc3c8');draw=ImageDraw.Draw(im)
            draw.line((0,60,999,60),fill='#90989d',width=2)
            draw.line((0,560,999,560),fill='#90989d',width=2)
            draw.text((400,300),'CALLIGRAPHY',fill='black');im.save(path)
            self.assertIsNone(same_colour_sheet(path))
            # Real backing texture must still be rejected if there is ink below.
            rng=np.random.default_rng(21)
            pixels=np.full((750,1000,3),190.,dtype='float32')
            pixels[60:560]=200
            texture=rng.normal(0,8,(190,1000)).astype('float32')
            from imaging import cv2
            texture=cv2.GaussianBlur(texture,(0,0),4)
            pixels[560:]+=texture[:,:,None]*4
            im=Image.fromarray(np.clip(pixels,0,255).astype('uint8'));draw=ImageDraw.Draw(im)
            draw.rectangle((200,250,250,350),fill='black');draw.rectangle((400,630,460,660),fill='black');im.save(path)
            self.assertIsNone(same_colour_sheet(path))

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
                storage=json.load(urllib.request.urlopen(base+'/api/settings/storage'))
                self.assertEqual(Path(storage['path']),Path(d));self.assertFalse(storage['can_change'])
                self.assertIn('文件存储',urllib.request.urlopen(base+'/settings.js').read().decode('utf-8'))
                with self.assertRaises(urllib.error.HTTPError):post('settings/storage',{'path':str(Path(d)/'new')})
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
                self.assertEqual(automatic['candidates'],[])
                self.assertEqual(automatic['points'],FULL)
                self.assertFalse(automatic['confirmed'])
                self.assertNotIn('auto_result',automatic)
                self.assertFalse(any(automatic['trim'].values()))
                post('prepare',{})
                for _ in range(100):
                    prepared=json.load(urllib.request.urlopen(base+'/api/prepare-job'))
                    if not prepared['running']:break
                    time.sleep(.05)
                self.assertFalse(prepared['running'])
                self.assertFalse(prepared['errors'])
                unchanged=next(x for x in json.load(urllib.request.urlopen(base+'/api/items')) if x['id']==automatic['id'])
                self.assertEqual(unchanged,automatic, 'background preparation must not modify imported geometry')
                with Image.open(io.BytesIO(urllib.request.urlopen(base+'/api/image/'+automatic['id']+'?mode=result').read())) as preview:
                    self.assertEqual(preview.size,(600,800))
                processed=post('process',{'id':automatic['id']})
                self.assertTrue(processed['candidates'])
                self.assertNotEqual(processed['points'],FULL)
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
                self.assertEqual(weak['points'],FULL)
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
