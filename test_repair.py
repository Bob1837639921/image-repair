import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from repairing import local_repair,RepairService,crop_signature,region_pixels,ai_repair,repair_prompt,verify_ai_patch
from imaging import np,cv2,FULL,DEFAULTS


class RepairTests(unittest.TestCase):
    def test_local_preserves_grain_at_small_and_large_selection_scales(self):
        rng=np.random.default_rng(27)
        for size in (120,600):
            y,x=np.mgrid[:size,:size].astype('float32')
            grain=cv2.GaussianBlur(rng.normal(0,5,(size,size)).astype('float32'),(0,0),.6)
            grain+=cv2.GaussianBlur(rng.normal(0,8,(size,size)).astype('float32'),(0,0),2)
            shadow=-27*np.exp(-((x-size*.5)/(size*.11))**2)
            for kind in ('bump','crease'):
                image=Image.fromarray(np.rint(np.clip((210+grain+shadow)[:,:,None]+np.array([0,-6,-20]),0,255)).astype('uint8'))
                before=np.asarray(image)[:,:,0].astype('float32')
                after=np.asarray(local_repair(image,[.1,.1,.9,.9],.85,kind))[:,:,0].astype('float32')
                margin=int(size*.25);sl=np.s_[margin:-margin,margin:-margin]
                a=(before-cv2.GaussianBlur(before,(0,0),1.4))[sl]
                b=(after-cv2.GaussianBlur(after,(0,0),1.4))[sl]
                self.assertGreater(np.corrcoef(a.ravel(),b.ravel())[0,1],.95,(size,kind))
                self.assertGreater(b.std()/a.std(),.90,(size,kind))
                self.assertLess(b.std()/a.std(),1.10,(size,kind))
                center=np.s_[margin:-margin,int(size*.46):int(size*.54)]
                self.assertGreater(after[center].mean(),before[center].mean()+1,(size,kind))

    def test_local_modes_differ_and_zero_strength_is_exact(self):
        y,x=np.mgrid[:240,:240].astype('float32')
        grain=np.random.default_rng(3).normal(0,2,(240,240))
        paper=210+grain-28*np.exp(-((x-120)/5)**2)
        image=Image.fromarray(np.clip(np.repeat(paper[:,:,None],3,axis=2),0,255).astype('uint8'))
        self.assertTrue(np.array_equal(np.asarray(image),np.asarray(local_repair(image,[.1,.1,.9,.9],0,'bump'))))
        crease=np.asarray(local_repair(image,[.1,.1,.9,.9],.85,'crease'))
        bump=np.asarray(local_repair(image,[.1,.1,.9,.9],.85,'bump'))
        self.assertGreater(float(np.abs(crease.astype(float)-bump).sum()),100)

    def test_multiple_classified_marks_saved_and_only_run_on_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.png';Image.new('RGB',(100,240),'#d8cfb4').save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            saves=[];service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:saves.append(json.dumps(item)),[item])
            marks=[dict(id='one',region=[.1,.1,.3,.3],kind='crease'),dict(id='two',region=[.6,.6,.9,.9],kind='bump')]
            with patch('repairing.ai_repair',side_effect=lambda im,*args:im.copy()) as ai:
                service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
                self.assertEqual(ai.call_count,0);self.assertEqual(service.marks(item),marks)
                self.assertIn('repair_marks',json.loads(saves[-1]))
                result=service.post('preview',dict(id='test',regions=marks,method='ai'))
                self.assertEqual(ai.call_count,2)
                self.assertEqual([call.args[3] for call in ai.call_args_list],['crease','bump'])
                self.assertEqual(ai.call_args_list[1].args[-1]['index'],2)
                self.assertNotIn('repair_state',item)
                service.post('accept',dict(id='test',draft=result['draft']))
                layer=service.state(item)['layers'][-1]
                self.assertEqual(service.state(item)['details'][layer]['regions'],marks)
            self.assertIn('narrow bright ridge',repair_prompt('crease',marks[0]))
            self.assertIn('broad highlight/shadow',repair_prompt('bump',marks[1]))
            self.assertIn('Do not invent',repair_prompt('crease'))
            item['trim']={'left':.01};self.assertEqual(service.marks(item),[])
            with self.assertRaises(ValueError):service.post('marks',dict(id='test',signature='stale',regions=marks))

    def test_local_shadow_ink_and_unchanged_outside(self):
        image=Image.new('RGB',(320,500),(210,205,185));draw=ImageDraw.Draw(image)
        draw.rectangle((148,0,161,499),fill=(177,173,157))
        draw.rectangle((130,170,170,210),fill=(20,20,20))
        draw.rectangle((150,260,175,290),fill=(175,45,40))
        repaired=local_repair(image,[.35,.1,.65,.9],.85)
        before=np.asarray(image);after=np.asarray(repaired)
        self.assertGreater(int(after[100,155,0]),int(before[100,155,0]))
        self.assertTrue(np.array_equal(before[:50],after[:50]))
        self.assertTrue(np.array_equal(before[:, :112],after[:, :112]))
        self.assertTrue(np.array_equal(before[175:205,135:165],after[175:205,135:165]))
        self.assertTrue(np.array_equal(before[265:285,155:170],after[265:285,155:170]))

    def test_queue_preview_accept_undo_and_crop_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.png';Image.new('RGB',(100,240),'#d8cfb4').save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=False,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            with self.assertRaises(ValueError):service.post('preview',{'id':'test','region':[.1,.1,.8,.8]})
            item['confirmed']=True
            original=service.image(item);preview=service.post('preview',{'id':'test','region':[.1,.1,.8,.8]})
            self.assertNotIn('repair_state',item)
            service.post('accept',{'id':'test','draft':preview['draft']})
            self.assertEqual(len(service.state(item)['layers']),1)
            service.post('complete',{'id':'test'});self.assertTrue(service.complete(item))
            service.post('undo',{'id':'test'});self.assertEqual(service.state(item)['layers'],[])
            self.assertTrue(np.array_equal(np.asarray(service.image(item)),np.asarray(original)))
            service.post('redo',{'id':'test'});self.assertEqual(len(service.state(item)['layers']),1)
            stale=service.post('preview',{'id':'test','region':[.1,.1,.8,.8]})
            item['trim']={'left':.01}
            self.assertEqual(service.state(item),{})
            with self.assertRaises(ValueError):service.post('accept',{'id':'test','draft':stale['draft']})
            service.post('complete',{'id':'test'})
            self.assertEqual(len(item['repair_history']),1)
            self.assertTrue(source.exists())

    def test_pending_preview_survives_restart_and_discard(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.png';Image.new('RGB',(100,240),'#d8cfb4').save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            def create():return RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            service=create();body=dict(id='test',region=[.1,.1,.8,.8],strength=.8)
            first=service.post('preview',body)
            service=create();self.assertEqual(service.pending(item)['draft'],first['draft'])
            self.assertEqual(service.pending(item)['strength'],.8)
            second=service.post('preview',body)
            self.assertFalse(service.valid_draft(item,first['draft']))
            self.assertEqual(service.pending(item)['draft'],second['draft'])
            service.post('discard',dict(id='test',draft=second['draft']))
            self.assertIsNone(create().pending(item))
            batch=service.post('preview',dict(body,origin='batch'))
            self.assertIsNone(service.pending(item))
            self.assertTrue(service.valid_draft(item,batch['draft']))
            single=service.post('preview',body);item['trim']={'left':.01}
            self.assertIsNone(service.pending(item))

    def test_ai_proxy_payload_and_outside_composite(self):
        image=Image.new('RGB',(120,180),'#d8cfb4')
        buffer=io.BytesIO();Image.new('RGB',(100,150),'#d9d0b5').save(buffer,'PNG')
        import base64
        response=io.BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(buffer.getvalue()).decode()}]}).encode())
        with patch('urllib.request.urlopen',return_value=response) as call:
            out=ai_repair(image,[.2,.2,.6,.6],'proxy-key','crease','http://127.0.0.1:8317/v1','image-edit-test')
        request=call.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:8317/v1/images/edits')
        self.assertIn(b'image-edit-test',request.data);self.assertIn(b'name="mask"',request.data)
        self.assertTrue(np.array_equal(np.asarray(out)[:36],np.asarray(image)[:36]))
        self.assertEqual(out.size,image.size)

    def test_responses_mask_and_exact_protected_pixel_composite(self):
        import base64
        from repairing import protected_ink
        image=Image.new('RGB',(120,180),'#d8cfb4');draw=ImageDraw.Draw(image)
        draw.line((45,40,70,130),fill=(20,20,20),width=5)
        draw.rectangle((75,70,90,85),fill=(165,45,40))
        generated=image.copy();pixels=np.array(generated);pixels[:]=np.clip(pixels.astype(int)+2,0,255);generated=Image.fromarray(pixels)
        buffer=io.BytesIO();generated.save(buffer,'PNG')
        response=io.BytesIO(json.dumps({'output':[{'type':'image_generation_call','result':base64.b64encode(buffer.getvalue()).decode()}]}).encode())
        with patch('urllib.request.urlopen',return_value=response) as call:
            out=ai_repair(image,[.2,.2,.8,.8],'key',model='gpt-6.1-sol')
        request=call.call_args.args[0];self.assertTrue(request.full_url.endswith('/responses'))
        body=json.loads(request.data);self.assertEqual(body['model'],'gpt-6.1-sol')
        mask=Image.open(io.BytesIO(base64.b64decode(body['tools'][0]['input_image_mask']['image_url'].split(',')[1])))
        protected=protected_ink(image);self.assertTrue(np.all(np.asarray(mask)[protected,3]==255))
        before=np.asarray(image);after=np.asarray(out)
        self.assertTrue(np.array_equal(before[protected],after[protected]))
        self.assertTrue(np.array_equal(before[:36],after[:36]))
        self.assertGreater(np.count_nonzero(before!=after),0)

    def test_ai_rejects_colour_cast_and_displaced_ink(self):
        image=Image.new('RGB',(160,160),'#d8cfb4');draw=ImageDraw.Draw(image);draw.line((30,50,120,50),fill='black',width=8)
        verify_ai_patch(image,image.copy())
        shifted=Image.new('RGB',image.size,'#d8cfb4');ImageDraw.Draw(shifted).line((30,70,120,70),fill='black',width=8)
        with self.assertRaisesRegex(ValueError,'笔画'):verify_ai_patch(image,shifted)
        with self.assertRaisesRegex(ValueError,'色差'):verify_ai_patch(Image.new('RGB',(160,160),'#d8cfb4'),Image.new('RGB',(160,160),'#a0e0a0'))

    def test_ai_refuses_aspect_ratio_changes_instead_of_stretching(self):
        import base64
        image=Image.new('RGB',(120,180),'#d8cfb4');buffer=io.BytesIO();Image.new('RGB',(100,100),'#d8cfb4').save(buffer,'PNG')
        response=io.BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(buffer.getvalue()).decode()}]}).encode())
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'宽高比例'):ai_repair(image,[.2,.2,.6,.6],'test-key')

    def test_regions_are_validated(self):
        for region in ([],[0,0,0,0],[0,0,2,1],[0,0,float('nan'),1]):
            with self.assertRaises(ValueError):region_pixels(region,(100,200))


if __name__=='__main__':unittest.main(verbosity=2)
