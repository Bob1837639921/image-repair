"""Quiesced, verified data relocation with an atomic local configuration change."""
import hashlib
import os
import shutil
import subprocess
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path


class StorageSettings:
    def __init__(self,root,current,activate,busy,environment_override=False):
        self.root=Path(root);self.current=Path(current).resolve()
        self.activate=activate;self.busy=busy;self.environment_override=environment_override
        self.lock=threading.RLock();self.active=0
        self.job=dict(running=False,phase='idle',done=0,total=0,error='',destination='',previous='')

    def status(self):
        with self.lock:return dict(path=str(self.current),can_change=not self.environment_override,**self.job)

    @contextmanager
    def request(self):
        with self.lock:
            if self.job['running']:raise ValueError('正在迁移文件，请等待完成后再操作')
            self.active+=1
        try:yield
        finally:
            with self.lock:self.active-=1

    def start(self,value):
        with self.lock:
            if self.environment_override:raise ValueError('当前启动通过环境变量指定了数据目录，请先取消该覆盖配置')
            if self.job['running']:raise ValueError('文件迁移正在进行中')
            if self.active>1 or self.busy():raise ValueError('当前有图片加载、修复或导出任务，请稍后再迁移')
            if not isinstance(value,str) or not value.strip():raise ValueError('请选择文件存储位置')
            target=Path(value.strip()).expanduser()
            if not target.is_absolute():raise ValueError('请填写完整的文件夹路径')
            target=target.resolve();source=self.current
            if target==source:return dict(unchanged=True,**self.status())
            if target==target.parent or target in source.parents or source in target.parents:raise ValueError('请选择独立的数据文件夹，不要选择盘符根目录或当前目录的父子目录')
            if target.exists() and (not target.is_dir() or any(target.iterdir())):raise ValueError('请选择新的或空的文件夹，避免与已有文件混合')
            self.job=dict(running=True,phase='copy',done=0,total=0,error='',destination=str(target),previous=str(source))
            threading.Thread(target=self._migrate,args=(source,target),daemon=True).start()
            return self.status()

    def _migrate(self,source,target):
        temporary=self.root/('data-location.'+uuid.uuid4().hex+'.tmp');switched=False
        try:
            entries=list(source.rglob('*'))
            if source.is_symlink() or any(p.is_symlink() for p in entries):raise ValueError('数据目录包含链接，请先移除链接后再迁移')
            files=[p for p in entries if p.is_file()]
            required=sum(p.stat().st_size for p in files)
            parent=target
            while not parent.exists():
                if parent==parent.parent:raise ValueError('目标磁盘不存在或不可用，请检查存储位置')
                parent=parent.parent
            if shutil.disk_usage(parent).free<required+16*1024*1024:raise ValueError('目标磁盘空间不足')
            target.mkdir(parents=True,exist_ok=True)
            if any(target.iterdir()):raise ValueError('目标文件夹已出现其他文件，请选择空文件夹')
            with self.lock:self.job['total']=len(files)
            for folder in (p for p in entries if p.is_dir()):(target/folder.relative_to(source)).mkdir(parents=True,exist_ok=True)
            for index,path in enumerate(files,1):
                destination=target/path.relative_to(source);destination.parent.mkdir(parents=True,exist_ok=True)
                with path.open('rb') as reader,destination.open('xb') as writer:shutil.copyfileobj(reader,writer)
                shutil.copystat(path,destination)
                def digest(file):
                    result=hashlib.sha256()
                    with file.open('rb') as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
                    return result.digest()
                if digest(path)!=digest(destination):raise ValueError('文件校验失败，已保留原目录继续使用')
                with self.lock:self.job['done']=index
            with self.lock:self.job['phase']='switch'
            temporary.write_text(str(target)+'\n','utf-8')
            self.activate(target);switched=True
            os.replace(temporary,self.root/'data-location.txt')
            with self.lock:self.current=target;self.job.update(running=False,phase='complete')
        except Exception as error:
            if switched:self.activate(source)
            with self.lock:self.job.update(running=False,phase='error',error=str(error))
        finally:temporary.unlink(missing_ok=True)


def choose_directory():
    if os.name!='nt':raise ValueError('当前系统请直接填写目录路径')
    script="""[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$picker = New-Object System.Windows.Forms.FolderBrowserDialog
$picker.Description = '选择画心文件存储位置（新的或空的文件夹）'
$picker.ShowNewFolderButton = $true
try { if ($picker.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($picker.SelectedPath) } }
finally { $picker.Dispose() }
"""
    result=subprocess.run(['powershell.exe','-NoProfile','-STA','-Command',script],capture_output=True,encoding='utf-8-sig',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('无法打开文件夹选择窗口，请直接填写路径')
    return result.stdout.strip()
