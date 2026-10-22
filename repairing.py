"""Confirmed-crop repair workflow. Source files are never modified."""
import base64
import hashlib
import io
import json
import math
import os
import re
import urllib.request
import urllib.error
import uuid
from urllib.parse import urlparse
from PIL import Image, ImageDraw
from imaging import cv2, np, render
from ai_config import load_connection,save_connection


def crop_signature(item):
    values={key:item.get(key) for key in ('file','points','rotation','settings','trim')}
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()[:20]


def region_pixels(region,size):
    if not isinstance(region,list) or len(region)!=4:raise ValueError('请先框选修复区域')
    values=[float(x) for x in region]
    if not all(math.isfinite(x) and 0<=x<=1 for x in values):raise ValueError('区域超出图片')
    x1,y1,x2,y2=values;w,h=size
    rect=(round(x1*w),round(y1*h),round(x2*w),round(y2*h))
    if rect[2]-rect[0]<4 or rect[3]-rect[1]<4:raise ValueError('选区太小，请重新框选')
    return rect


def feather(size):
    w,h=size;y,x=np.mgrid[:h,:w]
    distance=np.minimum.reduce([x,y,w-1-x,h-1-y]).astype('float32')
    return np.clip(distance/max(2,min(20,min(w,h)*.15)),0,1)


def local_repair(image,region,strength=.65,kind='crease'):
    if kind not in ('crease','bump'):raise ValueError('请选择折痕或凸起')
    strength=float(strength)
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('强度范围为 0–1')
    rect=region_pixels(region,image.size);x1,y1,x2,y2=rect
    short=min(x2-x1,y2-y1)
    pad=max(32,min(320,short))
    box=(max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad))
    rgb=np.asarray(image.crop(box)).astype('float32');gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    # Close dark strokes out of the illumination estimate, not the output.
    radius=max(5,min(41,round(min(rgb.shape[:2])*.12)))|1
    closed=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius,radius)))
    lab=cv2.cvtColor(rgb.astype('uint8'),cv2.COLOR_RGB2LAB).astype(float)
    bg_color=np.median(lab.reshape(-1,3),axis=0)
    chroma=np.linalg.norm(lab[:,:,1:]-bg_color[1:],axis=2)
    protected=(gray<closed*.72)|(gray<float(np.percentile(gray,75))*.65)|(chroma>30)
    # Estimate illumination only from paper, never from ink/seals. Normalized
    # convolution avoids dark stroke halos without blurring the output pixels.
    protected=cv2.dilate(protected.astype('uint8'),np.ones((3,3),'uint8')).astype(bool)
    paper=(~protected).astype('float32')
    if not np.any(paper):return image.copy()
    def illumination(sigma):
        weight=cv2.GaussianBlur(paper,(0,0),sigma)
        value=cv2.GaussianBlur(gray*paper,(0,0),sigma)
        return np.divide(value,weight,out=np.full_like(gray,float(np.median(gray[~protected]))),where=weight>1e-4)
    # Broad bulges and narrow folds require different spatial scales. Grain is
    # kept in the original RGB pixels; only a smooth, additive light field moves.
    detail_scale=max(6,min(28,short*.06)) if kind=='bump' else max(2.5,min(6,short*.025))
    bg=illumination(detail_scale)
    smooth=illumination(max(detail_scale*3,short*.65))
    delta=smooth-bg
    if kind=='crease':
        # Ignore tiny variations rather than treating ordinary grain as a fold.
        delta*=np.clip((np.abs(delta)-1)/3,0,1)
        delta=cv2.GaussianBlur(delta,(0,0),1)
    delta=np.clip(delta,-35,35)
    # A soft protection margin suppresses transitions next to strokes; pixels
    # classified as ink/seals remain exactly unchanged.
    guard=1-cv2.GaussianBlur(protected.astype('float32'),(0,0),2)
    delta*=np.where(protected,0,guard)*strength
    fixed=np.clip(rgb+delta[:,:,None],0,255)
    left,top=x1-box[0],y1-box[1];w,h=x2-x1,y2-y1
    before=rgb[top:top+h,left:left+w];after=fixed[top:top+h,left:left+w]
    alpha=feather((w,h))[:,:,None]
    patch=np.rint(before*(1-alpha)+after*alpha).astype('uint8')
    out=image.copy();out.paste(Image.fromarray(patch),(x1,y1));return out


def repair_prompt(kind,annotation=None):
    task={'crease':'Repair a localized paper fold: reduce the narrow bright ridge, dark crease line and paired fold shadow, blending into the adjacent paper texture without blurring ink.',
          'bump':'Repair a localized paper bulge: even the broad highlight/shadow gradient caused by the raised paper while preserving natural paper grain. Do not treat it as a thin crack or erase intentional strokes.'}[kind]
    return ('Conservative archival restoration of a Chinese calligraphy photograph. The user explicitly classified this masked region as '+kind+'. '+task+
            ' Modify only the transparent mask. Surrounding pixels are reference only. Preserve the exact shape, position, thickness and tonal variation of every ink stroke, inscription and seal, including faint ink and strokes crossing the defect. Preserve the original paper colour, ink colour, seal colour, white balance, exposure, saturation, printed patterns and grain; match the adjacent unmasked paper with no colour cast or visible patch seams. Do not apply global colour grading or change resolution, aspect ratio or composition. Added canvas padding is reference only and must not move the artwork. Do not invent or reconstruct illegible characters, remove seals, whiten the paper, sharpen, recolour, rotate, warp or redraw the artwork. If a detail cannot be distinguished from ink, leave it unchanged. No added text or borders. '+
            ('User annotation metadata (original image normalized coordinates): '+json.dumps(annotation,ensure_ascii=False) if annotation else ''))


def validate_regions(regions,size):
    if not isinstance(regions,list) or not 1<=len(regions)<=100:raise ValueError('请标记 1–100 个修复区域')
    result=[];ids=set()
    for index,mark in enumerate(regions):
        if not isinstance(mark,dict) or mark.get('kind') not in ('crease','bump'):raise ValueError('每个区域都需要选择折痕或凸起')
        region_pixels(mark.get('region'),size)
        key=str(mark.get('id',index+1))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',key) or key in ids:raise ValueError('标记编号无效或重复')
        ids.add(key);result.append(dict(id=key,region=[float(v) for v in mark['region']],kind=mark['kind']))
    return result


def verify_ai_patch(before,after):
    """Conservative rejection heuristic, not a guarantee of unchanged calligraphy."""
    a=np.asarray(before.convert('RGB'));b=np.asarray(after.convert('RGB'))
    if a.shape!=b.shape:raise ValueError('AI 结果尺寸不一致，已拒绝使用')
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY);other=cv2.cvtColor(b,cv2.COLOR_RGB2GRAY)
    threshold=max(12,float(np.percentile(gray,75))*.55)
    ink=(gray<threshold).astype('uint8');new=(other<threshold).astype('uint8');kernel=np.ones((3,3),'uint8')
    lost=int(np.count_nonzero(ink&(1-cv2.dilate(new,kernel))));added=int(np.count_nonzero(new&(1-cv2.dilate(ink,kernel))))
    limit=max(8,int(ink.sum()*.04))
    if lost>limit or added>limit:raise ValueError('AI 结果疑似改动笔画或印章，已拦截；请缩小选区或改用常规修复')
    lab=cv2.cvtColor(a,cv2.COLOR_RGB2LAB).astype(float);lab_new=cv2.cvtColor(b,cv2.COLOR_RGB2LAB).astype(float)
    paper=(gray>=np.percentile(gray,45))&(ink==0)
    if paper.sum()>20:
        cast=np.median(lab_new[:,:,1:][paper]-lab[:,:,1:][paper],axis=0)
        if np.linalg.norm(cast)>7:raise ValueError('AI 结果出现明显纸色色差，已拦截；请重试或缩小选区')


def protected_ink(image):
    pixels=np.asarray(image.convert('RGB'));gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
    paper=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,np.ones((21,21),np.uint8))
    ink=gray<np.maximum(65,paper.astype(float)*.72)
    red=(pixels[:,:,0].astype(float)-pixels[:,:,1]>20)&(pixels[:,:,0].astype(float)-pixels[:,:,2]>15)
    return cv2.dilate((ink|red).astype('uint8'),np.ones((9,9),np.uint8))>0


def image_data_url(image):
    buffer=io.BytesIO();image.save(buffer,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()


def ai_repair(image,region,key,kind='crease',base_url='https://api.openai.com/v1',model='gpt-image-1.5',annotation=None):
    if not key:raise ValueError('请先在 AI 连接中配置 OpenAI API Key')
    x1,y1,x2,y2=region_pixels(region,image.size)
    pad=max(32,min(200,max(x2-x1,y2-y1)//4))
    box=(max(0,x1-pad),max(0,y1-pad),min(image.width,x2+pad),min(image.height,y2+pad))
    context=image.crop(box);ratio=context.width/context.height
    units=(3,2) if ratio>1.2 else (2,3) if ratio<.83 else (1,1)
    unit=math.ceil(max(context.width/units[0],context.height/units[1]));canvas_size=(units[0]*unit,units[1]*unit)
    offset=((canvas_size[0]-context.width)//2,(canvas_size[1]-context.height)//2)
    colour=tuple(int(v) for v in np.median(np.asarray(context).reshape(-1,3),axis=0))
    canvas=Image.new('RGB',canvas_size,colour);canvas.paste(context,offset)
    mask=Image.new('RGBA',canvas_size,(255,255,255,255))
    ImageDraw.Draw(mask).rectangle((x1-box[0]+offset[0],y1-box[1]+offset[1],x2-box[0]-1+offset[0],y2-box[1]-1+offset[1]),fill=(0,0,0,0))
    protected=protected_ink(canvas)
    mask_pixels=np.array(mask);mask_pixels[protected,3]=255;mask=Image.fromarray(mask_pixels)
    output_size='1536x1024' if units==(3,2) else '1024x1536' if units==(2,3) else '1024x1024'
    fields={'model':model,'prompt':repair_prompt(kind,annotation),'input_fidelity':'high','quality':'high','size':output_size,'output_format':'png'}
    boundary='repair-'+uuid.uuid4().hex;chunks=[]
    for name,value in fields.items():chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name,im in [('image',canvas),('mask',mask)]:
        buf=io.BytesIO();im.save(buf,'PNG')
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),buf.getvalue(),b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    request=urllib.request.Request(base_url+'/images/edits',data=b''.join(chunks),headers={'Authorization':'Bearer '+key,'Content-Type':'multipart/form-data; boundary='+boundary})
    responses=not model.startswith(('gpt-image','grok-imagine','image-'))
    if responses:
        body=dict(model=model,input=[dict(role='user',content=[dict(type='input_text',text=repair_prompt(kind,annotation)+' Keep exact canvas framing and dimensions. No padding or borders. Only edit transparent mask pixels; opaque pixels and ink are protected.'),dict(type='input_image',image_url=image_data_url(canvas))])],tools=[dict(type='image_generation',size=output_size,quality='high',input_image_mask=dict(image_url=image_data_url(mask)))],tool_choice=dict(type='image_generation'),store=False)
        request=urllib.request.Request(base_url+'/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=300) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        note='代理未提供图像编辑接口，请检查模型及 /images/edits 支持情况' if error.code in (404,405) else '请检查图像编辑模型、Key、权限及额度'
        raise ValueError(f'AI 服务请求失败（HTTP {error.code}），{note}') from None
    except (OSError,TimeoutError):raise ValueError('AI 服务连接超时或网络不可用，请重试') from None
    raw=next((entry.get('result') for entry in result.get('output',[]) if entry.get('type')=='image_generation_call' and entry.get('result')),None) if responses else result.get('data',[{}])[0].get('b64_json')
    if not raw:raise ValueError('AI 未返回图像，请重试')
    with Image.open(io.BytesIO(base64.b64decode(raw))) as generated:
        if abs((generated.width/generated.height)/(canvas.width/canvas.height)-1)>.01:raise ValueError('AI 返回宽高比例改变，已拒绝拉伸结果，避免字体变形')
        generated=generated.convert('RGB').resize(canvas_size,Image.Resampling.LANCZOS)
    patch=generated.crop((x1-box[0]+offset[0],y1-box[1]+offset[1],x2-box[0]+offset[0],y2-box[1]+offset[1]))
    verify_ai_patch(image.crop((x1,y1,x2,y2)),patch)
    before=np.asarray(image.crop((x1,y1,x2,y2))).astype(float);after=np.asarray(patch).astype(float)
    allowed=(np.asarray(mask)[:,:,3]==0)[y1-box[1]+offset[1]:y2-box[1]+offset[1],x1-box[0]+offset[0]:x2-box[0]+offset[0]]
    # Smooth only the AI correction field, retaining the original paper grain.
    correction=cv2.GaussianBlur((after-before).astype('float32'),(0,0),2)
    after=np.clip(before+correction,0,255)
    distance=cv2.distanceTransform(allowed.astype('uint8'),cv2.DIST_L2,3)
    alpha=(feather(patch.size)*np.minimum(distance/4,1))[:,:,None]
    out=image.copy();out.paste(Image.fromarray(np.rint(before*(1-alpha)+after*alpha).astype('uint8')),(x1,y1));return out


class RepairService:
    def __init__(self,data,find,source,lock,save,items):
        self.folder=data/'repairs';self.folder.mkdir(exist_ok=True)
        self.find=find;self.source=source;self.lock=lock;self.save=save;self.items=items
        self.drafts={};self.key=os.environ.get('OPENAI_API_KEY','')
        self.draft_path=self.folder/'drafts.json'
        try:
            if self.draft_path.exists():self.drafts=json.loads(self.draft_path.read_text('utf-8'))
        except (ValueError,OSError):self.drafts={}
        self.base_url='http://127.0.0.1:8317/v1';self.model='gpt-image-1.5'
        self.config_path=data/'ai-connection.json';self.config_warning='';self.persisted=False
        try:
            saved=load_connection(self.config_path)
            if saved:self.base_url=saved['base_url'];self.model=saved['model'];self.key=saved['key'] or self.key;self.persisted=bool(saved['key'])
        except (ValueError,OSError,KeyError,TypeError):self.config_warning='本机 AI 配置无法读取，请重新填写并保存；原配置文件已保留'

    def config(self):return dict(configured=bool(self.key),base_url=self.base_url,model=self.model,persisted=self.persisted,warning=self.config_warning)

    def save_drafts(self):
        with self.lock:
            temporary=self.draft_path.with_suffix('.tmp');temporary.write_text(json.dumps(self.drafts,ensure_ascii=False),'utf-8');os.replace(temporary,self.draft_path)

    def valid_draft(self,item,token):
        draft=self.drafts.get(token)
        return bool(draft and draft['id']==item['id'] and draft['signature']==crop_signature(item) and draft['layers']==self.state(item).get('layers',[]) and draft.get('marks',self.marks(item))==self.marks(item) and (self.folder/draft['file']).exists())

    def pending(self,item):
        with self.lock:
            for token,draft in reversed(list(self.drafts.items())):
                if draft.get('origin')=='single' and self.valid_draft(item,token):
                    return dict(draft=token,regions=draft['regions'],method=draft['method'],strength=draft.get('strength',.65))
        return None

    def state(self,item):
        state=item.get('repair_state',{})
        return state if state.get('signature')==crop_signature(item) else {}

    def marks(self,item):
        marks=item.get('repair_marks',{})
        return marks.get('regions',[]) if marks.get('signature')==crop_signature(item) else []

    def image(self,item,before=False):
        state=self.state(item)
        if not before and state.get('layers'):
            with Image.open(self.folder/state['layers'][-1]) as im:return im.convert('RGB')
        signature=crop_signature(item);path=self.folder/(item['id']+'_'+signature+'_base.png')
        if path.exists():
            with Image.open(path) as im:return im.convert('RGB')
        im=render(self.source(item),item['points'],item['rotation'],item['settings'],trim=item.get('trim'));im.save(path,'PNG');return im

    def complete(self,item):return bool(item.get('confirmed') and self.state(item).get('completed'))

    def payload(self,key,detail=False,before=False,draft=None):
        item=self.find(key)
        if not item.get('confirmed'):raise ValueError('请先确认裁剪，再进入修复')
        if draft:
            candidate=self.drafts.get(draft)
            if not self.valid_draft(item,draft):raise ValueError('修复预览已失效')
            with Image.open(self.folder/candidate['file']) as im:image=im.convert('RGB')
        else:image=self.image(item,before)
        with image:
            if not detail:image.thumbnail((1600,1600))
            buf=io.BytesIO();image.save(buf,'PNG' if detail else 'JPEG',**({} if detail else {'quality':94}));return buf.getvalue()

    def post(self,action,body,ai_config=None):
        if action=='config':
            key=str(body.get('key',self.key)).strip()
            if len(key)>8192 or '\n' in key or '\r' in key:raise ValueError('API Key 格式不正确')
            base=str(body.get('base_url',self.base_url)).strip().rstrip('/')
            parsed=urlparse(base)
            if parsed.username or parsed.password or parsed.query or parsed.fragment or not (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):raise ValueError('代理地址须为 HTTPS 或本机 HTTP 地址')
            model=str(body.get('model',self.model)).strip()
            if not model or len(model)>150:raise ValueError('请填写图像编辑模型名')
            with self.lock:
                save_connection(self.config_path,base,model,key)
                self.key=key;self.base_url=base;self.model=model;self.persisted=bool(key);self.config_warning=''
            return self.config()
        if action=='test':
            request=urllib.request.Request(self.base_url+'/models',headers={'Authorization':'Bearer '+self.key})
            try:
                with urllib.request.urlopen(request,timeout=15) as response:models=json.load(response)
            except urllib.error.HTTPError as e:raise ValueError(f'连接失败（HTTP {e.code}），请检查代理及 Key') from None
            except (OSError,ValueError):raise ValueError('无法连接模型服务，请检查地址和代理状态') from None
            return dict(models=[x.get('id') for x in models.get('data',[]) if x.get('id')],note='已连通模型列表，图像编辑能力以实际修复请求为准')
        item=self.find(body['id'])
        if not item.get('confirmed'):raise ValueError('请先确认裁剪，再进入修复')
        signature=crop_signature(item);state=self.state(item)
        if action=='discard':
            with self.lock:
                draft=self.drafts.get(body.get('draft'))
                if draft and draft['id']!=item['id']:raise ValueError('预览不属于当前作品')
                self.drafts.pop(body.get('draft'),None);self.save_drafts()
            return dict(discarded=True)
        if action=='marks':
            if body.get('signature')!=signature:raise ValueError('裁剪已改变，请重新加载后标记')
            regions=body.get('regions')
            if regions!=[]:
                with self.image(item) as im:regions=validate_regions(regions,im.size)
            with self.lock:
                target=next(x for x in self.items if x['id']==item['id'])
                if not target.get('confirmed') or crop_signature(target)!=signature:raise ValueError('裁剪已改变，请重新标记')
                if self.state(target) and regions!=self.marks(target):target['repair_state']['completed']=False
                target['repair_marks']=dict(signature=signature,regions=regions);self.save()
                return json.loads(json.dumps(target))
        if action=='preview':
            method=body.get('method','local');kind=body.get('kind','crease')
            if method not in ('local','ai') or kind not in ('crease','bump'):raise ValueError('修复方式不正确')
            with self.image(item) as image:
                regions=validate_regions(body['regions'],image.size) if 'regions' in body else validate_regions([dict(region=body.get('region'),kind=kind)],image.size)
                repaired=image.copy()
                for index,mark in enumerate(regions):
                    if method=='ai':
                        key,base,model=ai_config or (self.key,self.base_url,self.model)
                        result=ai_repair(repaired,mark['region'],key,mark['kind'],base,model,dict(index=index+1,total=len(regions),**mark))
                    else:result=local_repair(repaired,mark['region'],body.get('strength',.65),mark['kind'])
                    repaired.close();repaired=result
                    if repaired.size!=image.size:raise ValueError('修复结果像素尺寸改变，已拒绝保存')
                token=uuid.uuid4().hex;name=token+'.png';repaired.save(self.folder/name,'PNG');size=list(repaired.size)
                repaired.close()
            with self.lock:
                origin='batch' if body.get('origin')=='batch' else 'single'
                if origin=='single':
                    for old in list(self.drafts):
                        if self.drafts[old]['id']==item['id'] and self.drafts[old].get('origin')=='single':self.drafts.pop(old)
                self.drafts[token]=dict(id=item['id'],signature=signature,layers=list(state.get('layers',[])),file=name,regions=regions,marks=self.marks(item),origin=origin,method=method,strength=body.get('strength',.65));self.save_drafts()
            return dict(draft=token,width=size[0],height=size[1],method=method,regions=regions)
        with self.lock:
            target=next(x for x in self.items if x['id']==item['id'])
            if not target.get('confirmed') or crop_signature(target)!=signature:raise ValueError('裁剪已改变，请重新进入修复')
            latest=self.state(target)
            if list(latest.get('layers',[]))!=list(state.get('layers',[])):raise ValueError('修复已改变，请重新加载')
            if not latest:
                if target.get('repair_state'):target.setdefault('repair_history',[]).append(target['repair_state'])
                latest=dict(signature=signature,layers=[],redo=[],completed=False);target['repair_state']=latest
            if action=='accept':
                draft=self.drafts.get(body.get('draft'))
                if not self.valid_draft(target,body.get('draft')):raise ValueError('预览已失效，请重新生成')
                latest['layers'].append(draft['file']);latest['redo']=[];latest['completed']=False
                latest.setdefault('details',{})[draft['file']]=dict(regions=draft['regions'])
                self.drafts.pop(body['draft'])
                self.save_drafts()
            elif action=='undo':
                if latest['layers']:latest.setdefault('redo',[]).append(latest['layers'].pop())
                latest['completed']=False
            elif action=='redo':
                if latest.get('redo'):latest['layers'].append(latest['redo'].pop())
                latest['completed']=False
            elif action=='complete':latest['completed']=True
            else:raise ValueError('未知修复操作')
            target['revision']+=1;self.save();return json.loads(json.dumps(target))
