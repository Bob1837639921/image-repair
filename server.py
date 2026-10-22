import io
import json
import os
import secrets
import shutil
import threading
import time
import uuid
import webbrowser
import numpy as np
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

from imaging import load, render, detect, refine_native, validate, validate_trim, suggest_trim, automatic_process, FULL, DEFAULTS
from repairing import RepairService, crop_signature
from repair_batch import RepairBatch

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('SCROLL_STUDIO_DATA',str(ROOT/'data')))
DATA.mkdir(parents=True,exist_ok=True)
(DATA/'originals').mkdir(exist_ok=True)
(DATA/'previews').mkdir(exist_ok=True)
DB=DATA/'project.json'
LOCK=threading.RLock()
IMAGE_SLOTS=threading.Semaphore(2)
CACHE_LOCK=threading.Lock()
PREPARE={'running':False,'done':0,'total':0,'errors':[]}
TOKEN=secrets.token_urlsafe(32)
ITEMS=json.loads(DB.read_text('utf-8')) if DB.exists() else []
JOB={'running':False,'done':0,'total':0,'errors':[],'folder':None}
EXT={'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.webp'}


def save():
    temp=DB.with_suffix('.tmp')
    temp.write_text(json.dumps(ITEMS,ensure_ascii=False,indent=2),'utf-8')
    os.replace(temp,DB)


def find(key):
    with LOCK:
        item=next((x for x in ITEMS if x['id']==key),None)
        if not item: raise ValueError('图片不存在')
        return json.loads(json.dumps(item))


def source(item): return DATA/'originals'/item['file']


REPAIRS=RepairService(DATA,find,source,LOCK,save,ITEMS)
BATCH=RepairBatch(DATA,REPAIRS)


def import_image(name, content):
    name=Path(name.replace('\\','/')).name
    suffix=Path(name).suffix.lower()
    if suffix not in EXT: raise ValueError('不支持该图片格式')
    key=uuid.uuid4().hex
    dest=DATA/'originals'/(key+suffix)
    dest.write_bytes(content)
    try:
        im=load(dest)
        w,h=im.size
        im.close()
    except Exception:
        dest.unlink(missing_ok=True)
        raise ValueError('图片无法读取，请检查文件')
    item=dict(id=key,name=name,file=dest.name,width=w,height=h,points=FULL,rotation=0,settings=DEFAULTS.copy(),confirmed=False,candidates=[],revision=0)
    try:
        item.update(automatic_process(dest))
    except Exception as e:
        item['detection_note']='自动识别未完成：'+str(e)
    with LOCK:
        ITEMS.append(item)
        save()
    prepare_previews(item)
    return item


def process_item(key, ensure=False):
    item=find(key)
    if ensure and (item.get('auto_result') or item.get('confirmed')):
        return item
    candidates=item.get('candidates',[])
    adjusted=not np.allclose(item['points'],candidates[0]['points'] if candidates else FULL,atol=1e-5)
    if ensure and adjusted:
        with render(source(item),item['points'],item['rotation']) as image:
            trim=item.get('trim') or suggest_trim(image)['trim']
        processed=dict(trim=trim,auto_result=dict(needs_review=False,note='已保留手动裁剪并完成收边'))
    else:
        processed=automatic_process(source(item),item['rotation'])
        # Weak evidence must not replace an existing useful crop.
        existing=not np.allclose(item['points'],FULL,atol=1e-5)
        if existing and processed['auto_result']['needs_review']:
            with render(source(item),item['points'],item['rotation']) as image:
                trim=item.get('trim') or suggest_trim(image)['trim']
            processed.update(points=item['points'],trim=trim,auto_result=dict(needs_review=True,note='边界不明确，已保留原裁剪'))
    with LOCK:
        target=next(x for x in ITEMS if x['id']==item['id'])
        if target['revision']!=item['revision']:raise ValueError('图片已修改，请重新自动处理')
        target.setdefault('before_auto',{key:item.get(key) for key in ('points','trim','confirmed')})
        target.update(processed,confirmed=False,revision=target['revision']+1)
        save()
        return json.loads(json.dumps(target))


def image_payload(item,mode):
    extension='png' if mode=='detail' else 'jpg'
    version='_v'+str(item['revision']) if mode=='result' else ''
    cached=DATA/'previews'/f"{item['id']}_{item['rotation']}_{mode}{version}.{extension}"
    if cached.exists():return cached.read_bytes()
    with CACHE_LOCK:
        if cached.exists():return cached.read_bytes()
        image=render(source(item),item['points'],item['rotation'],item['settings'],preview=True,trim=item.get('trim')) if mode=='result' else load(source(item),item['rotation'])
        with image:
            if mode!='detail':image.thumbnail((180,180) if mode=='thumb' else (1600,1600))
            buf=io.BytesIO();image.save(buf,'PNG' if mode=='detail' else 'JPEG',**({} if mode=='detail' else {'quality':92}))
        payload=buf.getvalue();cached.write_bytes(payload)
        return payload


def prepare_previews(item):
    for mode in ('original','thumb','result'):image_payload(item,mode)


def prepare_worker(keys):
    for key in keys:
        try:
            item=process_item(key,ensure=True)
            prepare_previews(item)
        except Exception as e:
            with LOCK:PREPARE['errors'].append({'id':key,'error':str(e)})
        finally:
            with LOCK:PREPARE['done']+=1
    with LOCK:PREPARE['running']=False


def start_prepare():
    with LOCK:
        if PREPARE['running']:return dict(PREPARE)
        keys=[item['id'] for item in ITEMS]
        PREPARE.update(running=bool(keys),done=0,total=len(keys),errors=[])
        if keys:threading.Thread(target=prepare_worker,args=(keys,),daemon=True).start()
        return dict(PREPARE)


def export_worker(items, fmt):
    folder=DATA/'exports'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:4])
    folder.mkdir(parents=True)
    manifest=[]
    for i,item in enumerate(items,1):
        try:
            im=REPAIRS.image(item) if REPAIRS.complete(item) else render(source(item),item['points'],item['rotation'],item['settings'],trim=item.get('trim'))
            stem=Path(item['name']).stem
            filename=f'{i:03d}_{stem}.{fmt}'
            im.save(folder/filename,**({'quality':97,'subsampling':0} if fmt=='jpg' else {}))
            manifest.append({**item,'output':filename,'output_size':list(im.size)})
            im.close()
        except Exception as e:
            with LOCK: JOB['errors'].append(item['name']+': '+str(e))
        with LOCK: JOB['done']=i
    (folder/'处理记录.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    with LOCK: JOB.update(running=False,folder=str(folder))


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass

    def respond(self,value,status=200,mime='application/json; charset=utf-8',cache='no-store'):
        data=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control',cache)
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return self.headers.get('Host','').split(':')[0] in ('127.0.0.1','localhost')

    def do_GET(self):
        try:
            if not self.allowed(): return self.respond({'error':'非法主机'},403)
            u=urlparse(self.path); q=parse_qs(u.query)
            if u.path=='/':
                return self.respond((ROOT/'static/index.html').read_text('utf-8').replace('__TOKEN__',TOKEN).encode(),mime='text/html; charset=utf-8')
            if u.path in ('/app.js','/style.css','/repair.js','/repair-batch.js'):
                return self.respond((ROOT/'static'/u.path[1:]).read_bytes(),mime='text/javascript; charset=utf-8' if u.path.endswith('js') else 'text/css; charset=utf-8')
            if u.path=='/api/items':
                with LOCK: return self.respond(ITEMS)
            if u.path=='/api/job':
                with LOCK: return self.respond(JOB)
            if u.path=='/api/prepare-job':
                with LOCK:return self.respond(PREPARE)
            if u.path=='/api/repair/config':return self.respond(REPAIRS.config())
            if u.path=='/api/repair/batch-status':return self.respond(BATCH.status())
            if u.path=='/api/repair/batch-candidates':
                BATCH.status();return self.respond(BATCH.candidates())
            if u.path.startswith('/api/repair/info/'):
                item=find(u.path.rsplit('/',1)[1])
                if not item.get('confirmed'):raise ValueError('请先确认裁剪')
                with REPAIRS.image(item) as image:size=list(image.size)
                return self.respond(dict(size=size,state=REPAIRS.state(item),marks=REPAIRS.marks(item),signature=crop_signature(item)))
            if u.path.startswith('/api/repair/image/'):
                payload=REPAIRS.payload(u.path.rsplit('/',1)[1],detail=q.get('detail')==['1'],before=q.get('before')==['1'],draft=q.get('draft',[None])[0])
                return self.respond(payload,mime='image/png' if q.get('detail')==['1'] else 'image/jpeg',cache='no-store')
            if u.path.startswith('/api/image/'):
                item=find(u.path.rsplit('/',1)[1]); mode=q.get('mode',['original'])[0]
                if mode not in ('original','thumb','result','detail'): raise ValueError('预览类型不正确')
                with IMAGE_SLOTS:
                    payload=image_payload(item,mode)
                return self.respond(payload,mime='image/png' if mode=='detail' else 'image/jpeg',cache='no-store' if mode=='result' else 'private, max-age=86400')
            return self.respond({'error':'没有此页面'},404)
        except Exception as e: self.respond({'error':str(e)},400)

    def do_POST(self):
        try:
            if not self.allowed() or self.headers.get('X-App-Token')!=TOKEN:
                return self.respond({'error':'请求未授权，请刷新页面'},403)
            size=int(self.headers.get('Content-Length',0))
            if size>120*1024*1024: raise ValueError('单张图片请小于 120 MB')
            raw=self.rfile.read(size); u=urlparse(self.path)
            if u.path=='/api/import':
                name=parse_qs(u.query).get('name',['image.jpg'])[0]
                return self.respond(import_image(name,raw))
            body=json.loads(raw or b'{}')
            if u.path=='/api/repair/batch-start':return self.respond(BATCH.start(body.get('ids'),body.get('workers',2)))
            if u.path=='/api/repair/batch-cancel':return self.respond(BATCH.cancel())
            if u.path=='/api/repair/batch-dismiss':return self.respond(BATCH.dismiss(body['id'],body['draft']))
            if u.path.startswith('/api/repair/'):
                if u.path=='/api/repair/preview' and BATCH.active(body.get('id')):raise ValueError('本作品已在批量队列中，请勿重复提交')
                return self.respond(REPAIRS.post(u.path.rsplit('/',1)[1],body))
            if u.path=='/api/prepare':return self.respond(start_prepare())
            if u.path=='/api/update':
                points=validate(body['points']).tolist()
                settings={k:float(body.get('settings',{}).get(k,v)) for k,v in DEFAULTS.items()}
                if not all(.5<=v<=2 for v in settings.values()): raise ValueError('参数超出范围')
                rotation=int(body.get('rotation',0))
                trim=validate_trim(body.get('trim'))
                if rotation not in (0,90,180,270): raise ValueError('旋转角度不正确')
                with LOCK:
                    item=next(x for x in ITEMS if x['id']==body['id'])
                    item.update(points=points,settings=settings,rotation=rotation,trim=trim,confirmed=bool(body.get('confirmed',False)),revision=item['revision']+1)
                    if item.get('repair_state') and not REPAIRS.state(item):item.setdefault('repair_history',[]).append(item.pop('repair_state'))
                    save()
                    return self.respond(item)
            if u.path=='/api/process':
                return self.respond(process_item(body['id'],bool(body.get('only_if_needed'))))
            if u.path=='/api/trim':
                item=find(body['id'])
                with render(source(item),item['points'],item['rotation']) as image:
                    suggestion=suggest_trim(image)
                with LOCK:
                    target=next(x for x in ITEMS if x['id']==item['id'])
                    if target['revision']!=item['revision']:raise ValueError('图片已修改，请重新去残边')
                    target.update(trim=suggestion['trim'],confirmed=False,revision=target['revision']+1)
                    save()
                    return self.respond({'item':target,'note':suggestion['note']})
            if u.path=='/api/refine':
                item=find(body['id'])
                with load(source(item),item['rotation']) as image:
                    precise=refine_native(image,item['points'])
                with LOCK:
                    target=next(x for x in ITEMS if x['id']==item['id'])
                    if target['revision']!=item['revision']: raise ValueError('图片已被修改，请重新精定位')
                    target.update(candidates=[{**precise,'method':'native'},{'points':item['points'],'method':'before-native'}],points=precise['points'],confirmed=False,revision=target['revision']+1)
                    save()
                    return self.respond(target)
            if u.path=='/api/detect':
                item=find(body['id']); candidates=detect(source(item),item['rotation'])
                with LOCK:
                    target=next(x for x in ITEMS if x['id']==item['id'])
                    target.update(candidates=candidates,confirmed=False,revision=target['revision']+1)
                    if candidates: target['points']=candidates[0]['points']
                    save()
                    return self.respond(target)
            if u.path=='/api/export':
                with LOCK:
                    if JOB['running']: raise ValueError('导出正在进行中')
                    selection=[find(x['id']) for x in ITEMS if x['confirmed']]
                    if body.get('stage')=='repair':selection=[x for x in selection if REPAIRS.complete(x)]
                    if not selection: raise ValueError('请先检查并确认至少一张图片')
                    fmt=body.get('format','png')
                    if fmt not in ('png','jpg'): raise ValueError('导出格式不正确')
                    JOB.update(running=True,done=0,total=len(selection),errors=[],folder=None)
                    threading.Thread(target=export_worker,args=(selection,fmt),daemon=True).start()
                return self.respond({'ok':True})
            if u.path=='/api/open-export':
                if not JOB['folder']: raise ValueError('还没有导出文件')
                os.startfile(JOB['folder'])
                return self.respond({'ok':True})
            return self.respond({'error':'接口不存在'},404)
        except Exception as e: self.respond({'error':str(e)},400)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--no-browser',action='store_true'); parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{args.port}'
    print('Scroll Studio: '+url,flush=True)
    start_prepare()
    if not args.no_browser: webbrowser.open(url)
    server.serve_forever()
