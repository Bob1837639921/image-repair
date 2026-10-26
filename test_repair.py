import io
import json
import math
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from repairing import local_repair,RepairService,crop_signature,region_pixels,ai_repair,repair_prompt,verify_ai_patch,crease_correction,brush_mask,validate_brush,snap_crease
from imaging import np,cv2,FULL,DEFAULTS


class RepairTests(unittest.TestCase):
    def test_direct_ai_preserves_previous_preview_until_success_and_supports_one_region(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.new('RGB',(100,200),'#d8cfb4').save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            marks=[dict(id='first',kind='crease',region=[.1,.1,.3,.3]),dict(id='second',kind='bump',region=[.6,.6,.8,.8])]
            service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
            old=service.post('preview',dict(id='test',regions=marks,method='local'))['draft']
            with patch('repairing.ai_repair',side_effect=ValueError('offline')):
                with self.assertRaises(ValueError):service.post('preview',dict(id='test',regions=marks,method='ai',replace_draft=old))
            self.assertTrue(service.valid_draft(item,old))
            with patch('repairing.ai_repair',side_effect=lambda image,*args:image.copy()) as ai:
                result=service.post('retry-region',dict(id='test',draft=old,mark_id='second',method='ai'))
                self.assertEqual(ai.call_count,1);self.assertEqual(ai.call_args.args[1],marks[1]['region']);self.assertEqual(result['regions'],marks)
                new=service.post('preview',dict(id='test',regions=marks,method='ai',replace_draft=old))['draft']
            self.assertTrue(service.valid_draft(item,old));self.assertTrue(service.valid_draft(item,new))
            self.assertEqual(service.marks(item),marks);self.assertFalse(service.state(item).get('layers'))
            service.post('discard',dict(id='test',draft=old));self.assertTrue(service.valid_draft(item,new))

    def test_blemish_replacement_keeps_grain_and_only_changes_selected_paper(self):
        rng=np.random.default_rng(43)
        noise=rng.normal(0,3,(240,320)).astype('float32')
        paper=np.clip(205+noise[:,:,None]+np.array([0,-5,-16]),0,255).astype('uint8')
        image=Image.fromarray(paper);draw=ImageDraw.Draw(image)
        draw.ellipse((151,111,168,128),fill=(155,150,140));draw.ellipse((154,112,163,116),fill=(240,235,220))
        region=[.44,.41,.56,.59];before=np.asarray(image);result=np.asarray(local_repair(image,region,.65,'blemish'))
        rect=region_pixels(region,image.size);x1,y1,x2,y2=rect
        self.assertGreater(float(result[116:124,155:164,0].mean()),190)
        self.assertLess(float(result[116:124,155:164,0].std()),8)
        self.assertGreater(float(result[y1+6:y2-6,x1+6:x2-6,0].std()),1.5,'retain donor grain, not a flat colour')
        mask=np.ones(before.shape[:2],bool);mask[y1:y2,x1:x2]=False
        self.assertTrue(np.array_equal(before[mask],result[mask]))
        self.assertTrue(np.array_equal(before,np.asarray(local_repair(image,region,0,'blemish'))))
        self.assertIn('adjacent clean paper',repair_prompt('blemish'))

    def test_blemish_does_not_copy_nearby_ink_and_all_mark_kinds_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'paper.png';image=Image.new('RGB',(240,360),'#d8cfb4');draw=ImageDraw.Draw(image)
            draw.rectangle((75,50,115,130),fill='black');draw.ellipse((101,164,112,175),fill='#99907a');image.save(source)
            out=np.asarray(local_repair(image,[.4,.44,.5,.5],.65,'blemish'))
            self.assertGreater(int(out[169,106,0]),190)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            marks=[dict(id='spot',region=[.4,.44,.5,.5],kind='blemish')]
            service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
            preview=service.post('preview',dict(id='test',regions=marks,method='local'))
            self.assertEqual(preview['regions'],marks)
            service.post('accept-region',dict(id='test',draft=preview['draft'],mark_id='spot'))
            self.assertEqual(service.marks(item),[])

    def test_region_retry_discard_and_new_marks_preserve_other_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.new('RGB',(100,200),(180,175,160)).save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            marks=[dict(id='one',region=[.1,.1,.4,.3],kind='crease'),dict(id='two',region=[.6,.6,.9,.9],kind='bump')]
            service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
            calls=[]
            def fake(image,region,*args):
                calls.append(region);result=image.copy();result.paste((190+len(calls),180,170),region_pixels(region,image.size));return result
            with patch('repairing.local_repair',side_effect=fake):
                preview=service.post('preview',dict(id='test',regions=marks));token=preview['draft']
                new=dict(id='new',region=[.1,.7,.3,.9],kind='crease')
                service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks+[new]))
                self.assertTrue(service.valid_draft(item,token))
                with self.assertRaises(ValueError):service.post('marks',dict(id='test',signature=crop_signature(item),regions=[marks[0],new]))
                with self.assertRaises(ValueError):service.post('complete',dict(id='test'))
                result=service.post('retry-region',dict(id='test',draft=token,mark_id='one'))
                self.assertEqual(len(calls),3);self.assertEqual(calls[-1],marks[0]['region']);self.assertEqual(result['regions'],marks)
                with Image.open(service.folder/service.drafts[token]['file']) as im:self.assertEqual(im.getpixel((70,140)),(192,180,170))
                result=service.post('discard-region',dict(id='test',draft=token,mark_id='two'))
                self.assertEqual(result['regions'],marks[:1]);self.assertEqual(service.marks(item),marks+[new]);self.assertEqual(len(calls),3)
                with Image.open(service.folder/service.drafts[token]['file']) as im:self.assertEqual(im.getpixel((70,140)),(180,175,160))
                service.post('accept',dict(id='test',draft=token))
                self.assertEqual(service.marks(item),[marks[1],new])
                with service.image(item) as im:
                    self.assertEqual(im.getpixel((20,40)),(193,180,170));self.assertEqual(im.getpixel((70,140)),(180,175,160))
                with service.image(item,before=True) as im:self.assertEqual(im.getpixel((20,40)),(180,175,160))

    def test_accept_one_region_preserves_pending_pixels_marks_and_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.new('RGB',(100,200),(180,175,160)).save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            marks=[dict(id='one',region=[.1,.1,.4,.3],kind='crease'),dict(id='two',region=[.6,.6,.9,.9],kind='bump')]
            service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
            def fake(image,region,*args):
                result=image.copy();rect=region_pixels(region,image.size)
                result.paste((200,195,180),rect);return result
            with patch('repairing.local_repair',side_effect=fake) as repair:
                preview=service.post('preview',dict(id='test',regions=marks))
                before=np.asarray(service.image(item)).copy()
                result=service.post('accept-region',dict(id='test',draft=preview['draft'],mark_id='two'))
                self.assertEqual(repair.call_count,2,'accept must not regenerate')
            self.assertEqual(result['draft'],preview['draft']);self.assertEqual(result['regions'],marks[:1])
            self.assertEqual(service.marks(item),marks[:1]);self.assertTrue(service.valid_draft(item,preview['draft']))
            after=np.asarray(service.image(item));self.assertTrue(np.array_equal(after[:100],before[:100]))
            self.assertEqual(after[140,70].tolist(),[200,195,180])
            restored=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            self.assertTrue(restored.valid_draft(item,preview['draft']))
            with self.assertRaises(ValueError):restored.post('accept-region',dict(id='test',draft=preview['draft'],mark_id='two'))
            final=restored.post('accept-region',dict(id='test',draft=preview['draft'],mark_id='one'))
            self.assertIsNone(final['draft']);self.assertEqual(restored.marks(item),[])
            after=np.asarray(restored.image(item));self.assertEqual(after[40,20].tolist(),[200,195,180]);self.assertEqual(after[140,70].tolist(),[200,195,180])
            restored.post('undo',dict(id='test'));self.assertEqual(restored.marks(item),marks[:1])
            restored.post('redo',dict(id='test'));self.assertEqual(restored.marks(item),[])

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

    @staticmethod
    def crease_paper(depth,angle,size=400,seed=0):
        rng=np.random.default_rng(seed);y,x=np.mgrid[:size,:size].astype('float32')
        mottle=cv2.GaussianBlur(rng.normal(0,1,(size,size)).astype('float32'),(0,0),6);mottle*=5/mottle.std()
        clean=np.array([228,212,182],'float32')+(rng.normal(0,4,(size,size)).astype('float32')+mottle)[:,:,None]
        a=math.radians(angle);d=(x-size/2)*math.cos(a)+(y-size/2)*math.sin(a)
        shade=1-depth*np.exp(-(d/3)**2)+depth*.5*np.exp(-((d-4.8)/3)**2)
        return np.clip(clean,0,255),np.clip(clean*shade[:,:,None],0,255),np.abs(d)<9

    def test_crease_removes_diagonal_and_deep_folds_keeping_colour_and_grain(self):
        for depth,angle,region in ((.1,45,[.1,.1,.9,.9]),(.3,-45,[.1,.1,.9,.9]),(.3,0,[.45,.1,.55,.9])):
            clean,folded,line=self.crease_paper(depth,angle)
            out=np.asarray(local_repair(Image.fromarray(folded.astype('uint8')),region,1,'crease')).astype('float32')
            x1,y1,x2,y2=region_pixels(region,(400,400));mx=min(20,(x2-x1)//4);inner=np.zeros((400,400),bool);inner[y1+20:y2-20,x1+mx:x2-mx]=True
            fold=inner&line;paper=inner&~line
            before=np.abs(folded-clean)[fold].mean();after=np.abs(out-clean)[fold].mean()
            self.assertLess(after,before*.5,(depth,angle))
            lab=lambda a:cv2.cvtColor(a.astype('uint8'),cv2.COLOR_RGB2LAB).astype('float32')
            self.assertLess(float(np.abs((lab(out)-lab(clean))[:,:,1:][fold].mean(0)).max()),1,'no colour cast on the fold')
            high=lambda a:(a[:,:,1]-cv2.GaussianBlur(a[:,:,1],(0,0),12))[paper]
            self.assertGreater(high(out).std()/high(clean).std(),.93,'paper grain kept beside the fold')

    def test_crease_follows_wavy_step_fold_in_thin_strip(self):
        # Mirrors a real scan: bright ridge, sharp step down, slow recovery,
        # zig-zagging line, and a user box only ~35 px tall.
        rng=np.random.default_rng(5);h,w=200,320;y,x=np.mgrid[:h,:w].astype('float32')
        line=100+8*np.abs(((x/60)%2)-1)*2-8
        d=y-line
        shade=np.where(d<0,1+.03*np.exp(-(d/1.5)**2),1-.10*np.exp(-d/25))
        clean=np.array([200,190,165],'float32')+rng.normal(0,2.5,(h,w,1)).astype('float32')
        folded=np.clip(clean*shade[:,:,None],0,255).astype('uint8')
        out=np.asarray(local_repair(Image.fromarray(folded),[.1,82/h,.9,117/h],1,'crease')).astype('float32')
        def jump(a):
            g=a[:,:,1];cols=range(60,260,10)
            return float(np.mean([g[int(line[0,c])-4:int(line[0,c])-1,c].mean()-g[int(line[0,c])+1:int(line[0,c])+4,c].mean() for c in cols]))
        self.assertLess(jump(out),jump(folded.astype('float32'))*.45)

    def wavy_fold(self,seed=5):
        rng=np.random.default_rng(seed);h,w=200,320;y,x=np.mgrid[:h,:w].astype('float32')
        line=100+8*np.abs(((x/60)%2)-1)*2-8
        d=y-line
        shade=np.where(d<0,1+.03*np.exp(-(d/1.5)**2),1-.10*np.exp(-d/25))
        clean=np.array([200,190,165],'float32')+rng.normal(0,2.5,(h,w,1)).astype('float32')
        return np.clip(clean*shade[:,:,None],0,255).astype('uint8'),line[0]

    def test_brush_crease_changes_only_painted_pixels(self):
        folded,line=self.wavy_fold();h,w=folded.shape[:2]
        path=[[x/w,float(line[x]+3)/h] for x in range(40,281,8)]
        brush=dict(size=16/w,paths=[path]);region=[30/w,float(line.min()-12)/h,290/w,float(line.max()+16)/h]
        out=np.asarray(local_repair(Image.fromarray(folded),region,1,'crease',brush)).astype(int)
        mask,_=brush_mask(brush,(w,h),(0,0,w,h))
        self.assertTrue(np.array_equal(out[~mask],folded.astype(int)[~mask]),'nothing outside the stroke moves')
        g=out[:,:,1];before=folded[:,:,1].astype(int)
        jump=lambda a:float(np.mean([a[int(line[c])-4:int(line[c])-1,c].mean()-a[int(line[c])+1:int(line[c])+4,c].mean() for c in range(70,250,10)]))
        self.assertLess(jump(g),jump(before)*.5)

    def test_snap_pulls_rough_stroke_onto_the_fold(self):
        folded,line=self.wavy_fold();h,w=folded.shape[:2]
        path=[[x/w,float(line[x]+9)/h] for x in range(40,281,10)]  # sloppy: 9 px low
        brush=dict(size=40/w,paths=[path]);region=[10/w,float(line.min()-14)/h,310/w,float(line.max()+32)/h]
        snapped=snap_crease(Image.fromarray(folded),region,brush)
        self.assertIsNotNone(snapped)
        points=np.array(snapped['brush']['paths'][0])*[w,h]
        offsets=np.array([py-line[int(round(px))] for px,py in points if 50<px<270])
        radius=snapped['brush']['size']*w/2
        self.assertLess(float(offsets.std()),2,'snapped path follows the zig-zag')
        self.assertTrue(np.all(np.abs(offsets)<radius-2),'snapped stroke covers the fold line')
        self.assertLess(snapped['brush']['size'],brush['size'],'width tightened to the fold')
        x1,y1,x2,y2=snapped['region'];self.assertTrue(0<=x1<x2<=1 and 0<=y1<y2<=1)
        plain=np.clip(np.random.default_rng(1).normal(200,2.5,(h,w,3)),0,255).astype('uint8')
        self.assertIsNone(snap_crease(Image.fromarray(plain),region,brush),'no fold, no snap')

    def test_brush_marks_validate_persist_and_preview(self):
        with self.assertRaises(ValueError):validate_brush(dict(size=0,paths=[[[.1,.1]]]))
        with self.assertRaises(ValueError):validate_brush(dict(size=.02,paths=[[[1.2,.1]]]))
        with self.assertRaises(ValueError):validate_brush(dict(size=.02,paths=[]))
        with tempfile.TemporaryDirectory() as directory:
            folded,line=self.wavy_fold();h,w=folded.shape[:2]
            root=Path(directory);source=root/'fold.png';Image.fromarray(folded).save(source)
            item=dict(id='test',file=source.name,points=FULL,rotation=0,settings=DEFAULTS,trim={},confirmed=True,revision=0)
            service=RepairService(root,lambda key:json.loads(json.dumps(item)),lambda x:source,threading.RLock(),lambda:None,[item])
            brush=dict(size=16/w,paths=[[[x/w,float(line[x]+3)/h] for x in range(40,281,8)]])
            marks=[dict(id='fold',kind='crease',region=[30/w,float(line.min()-12)/h,290/w,float(line.max()+16)/h],brush=brush)]
            service.post('marks',dict(id='test',signature=crop_signature(item),regions=marks))
            self.assertEqual(service.marks(item),marks)
            preview=service.post('preview',dict(id='test',regions=marks,method='local',strength=1))
            self.assertEqual(preview['regions'],marks)
            snapped=service.post('snap',dict(id='test',region=marks[0]['region'],brush=brush))
            self.assertIn('brush',snapped);self.assertIn('region',snapped)
            self.assertNotIn('paths',repair_prompt('crease',marks[0]))

    def test_crease_keeps_crossing_and_parallel_faint_ink_exact(self):
        _,folded,_=self.crease_paper(.3,0)
        image=Image.fromarray(folded.astype('uint8'));draw=ImageDraw.Draw(image)
        draw.rectangle((150,180,250,196),fill=(25,22,20))
        draw.rectangle((222,205,227,330),fill=(150,138,118))
        draw.ellipse((170,260,186,276),fill=(165,152,130))
        draw.rectangle((150,300,175,320),fill=(180,50,45))
        before=np.asarray(image).astype(int);after=np.asarray(local_repair(image,[.3,.1,.7,.9],1,'crease')).astype(int)
        for sl in (np.s_[182:195,152:249],np.s_[207:328,223:227],np.s_[263:274,173:184],np.s_[302:319,152:174]):
            self.assertTrue(np.array_equal(before[sl],after[sl]),sl)
        self.assertGreater(float((after-before)[60:170,197:204].mean()),20,'deep fold is not mistaken for ink')
        self.assertGreater(float((after-before)[172:179,197:204].mean()),15,'fold corrected right up to the stroke')

    def test_crease_without_dominant_direction_falls_back(self):
        clean,_,_=self.crease_paper(0,0)
        gray=cv2.cvtColor(clean.astype('uint8'),cv2.COLOR_RGB2GRAY).astype('float32')
        self.assertIsNone(crease_correction(clean,gray,np.s_[40:360,40:360],320,320))
        one,a,_=self.crease_paper(.2,30);_,b,_=self.crease_paper(.2,120)
        crossed=one*(a/one)*(b/one)
        gray=cv2.cvtColor(crossed.astype('uint8'),cv2.COLOR_RGB2GRAY).astype('float32')
        self.assertIsNone(crease_correction(crossed.astype('float32'),gray,np.s_[40:360,40:360],320,320))

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
