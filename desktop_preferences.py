"""Desktop-only preferences, kept outside the photograph library."""
import json
import os
from pathlib import Path
import threading


class DesktopPreferences:
    def __init__(self,root):
        self.path=Path(root)/'desktop-window.json'
        self.lock=threading.RLock()

    def read(self):
        with self.lock:
            try:value=json.loads(self.path.read_text('utf-8'))
            except (OSError,ValueError):value={}
            if not isinstance(value,dict):value={}
            if value.get('close_action') not in ('ask','tray','exit'):value['close_action']='ask'
            return value

    def update(self,**changes):
        if 'close_action' in changes and changes['close_action'] not in ('ask','tray','exit'):
            raise ValueError('关闭方式不正确')
        with self.lock:
            value=self.read();value.update(changes)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(value,ensure_ascii=False),'utf-8');os.replace(temp,self.path)
            return value
