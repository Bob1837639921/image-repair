"""Explicit, persistent AI queue. Results require review; never auto-accept."""
import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from repairing import crop_signature


class RepairBatch:
    def __init__(self,data,service):
        self.service=service;self.path=data/'repair-batch.json';self.lock=threading.RLock()
        self.job=dict(id=None,running=False,cancel=False,entries=[])
        if self.path.exists():
            try:self.job=json.loads(self.path.read_text('utf-8'))
            except (ValueError,OSError):pass
        self.job['running']=False
        for entry in self.job['entries']:
            if entry['status'] in ('queued','running'):entry.update(status='interrupted',error='服务重启中断，请手动重新加入，不会自动重复扣费')
        self.persist()

    def persist(self):
        with self.lock:
            temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.job,ensure_ascii=False,indent=2),'utf-8');os.replace(temporary,self.path)

    def fingerprint(self,item):
        values=[crop_signature(item),self.service.state(item).get('layers',[]),self.service.marks(item)]
        return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

    def active(self,key):
        with self.lock:return any(e['id']==key and e['status'] in ('queued','running') for e in self.job['entries'])

    def candidates(self):
        result=[]
        with self.service.lock:items=json.loads(json.dumps(self.service.items))
        with self.lock:ready={e['id'] for e in self.job['entries'] if e['status']=='ready'}
        for item in items:
            if not item.get('confirmed') or item['id'] in ready:continue
            state=self.service.state(item);applied=[]
            for layer in state.get('layers',[]):applied.extend(state.get('details',{}).get(layer,{}).get('regions',[]))
            regions=[mark for mark in self.service.marks(item) if mark not in applied]
            if regions:result.append(dict(id=item['id'],name=item['name'],regions=regions,fingerprint=self.fingerprint(item)))
        return result

    def status(self):
        with self.lock:
            changed=False
            for e in self.job['entries']:
                if e['status']!='ready':continue
                try:
                    item=self.service.find(e['id'])
                    if e.get('draft') not in self.service.drafts:e['status']='reviewed';changed=True
                    elif self.fingerprint(item)!=e['fingerprint'] or not self.service.valid_draft(item,e['draft']):e.update(status='stale',error='裁剪、标记或修复底图已变化，请重新加入');changed=True
                except ValueError:e.update(status='stale',error='作品不存在');changed=True
            if changed:self.persist()
            return json.loads(json.dumps(self.job))

    def start(self,ids,workers=2):
        if not self.service.key:raise ValueError('请先配置并保存 AI 连接')
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('请选择需要修复的作品')
        if workers not in (1,2):raise ValueError('同时处理数量只能为 1 或 2')
        self.status();available={e['id']:e for e in self.candidates()}
        if any(key not in available for key in ids):raise ValueError('所选作品已变化、暂无待修复标记或已有待审核结果，请刷新列表')
        with self.lock:
            if self.job['running']:raise ValueError('已有批量任务正在处理')
            kept=[e for e in self.job['entries'] if e['status']=='ready']
            entries=[dict(available[key],status='queued',draft=None,error=None) for key in ids]
            self.job=dict(id=uuid.uuid4().hex,running=True,cancel=False,workers=workers,entries=kept+entries)
            config=(self.service.key,self.service.base_url,self.service.model)
            self.persist();threading.Thread(target=self.run,args=(entries,workers,config),daemon=True).start()
        return self.status()

    def run(self,entries,workers,config):
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:list(pool.map(lambda e:self.process(e,config),entries))
        finally:
            with self.lock:self.job['running']=False;self.persist()

    def process(self,entry,config):
        with self.lock:
            if self.job['cancel']:entry['status']='cancelled';self.persist();return
            entry['status']='running';self.persist()
        try:
            item=self.service.find(entry['id'])
            if self.fingerprint(item)!=entry['fingerprint']:raise ValueError('作品标记或裁剪已变化，请重新加入')
            result=self.service.post('preview',dict(id=entry['id'],method='ai',regions=entry['regions']),ai_config=config)
            if self.fingerprint(self.service.find(entry['id']))!=entry['fingerprint']:raise ValueError('处理期间作品或标记发生变化，结果不再适用')
            with self.lock:entry.update(status='ready',draft=result['draft'],width=result['width'],height=result['height']);self.persist()
        except Exception as error:
            with self.lock:entry.update(status='failed',error=str(error));self.persist()

    def cancel(self):
        with self.lock:self.job['cancel']=True;self.persist()
        return self.status()

    def dismiss(self,key,draft):
        with self.lock:
            entry=next((e for e in self.job['entries'] if e['id']==key and e.get('draft')==draft),None)
            if not entry or entry['status']!='ready':raise ValueError('结果已失效，请刷新队列')
            entry['status']='discarded';self.persist()
        with self.service.lock:self.service.drafts.pop(draft,None);self.service.save_drafts()
        return self.status()
