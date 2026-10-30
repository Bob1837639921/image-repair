"""Native Windows window hosting the same local-only workbench."""
import ctypes
import json
import logging
import os
from pathlib import Path
import sys
import threading
import urllib.request
from desktop_preferences import DesktopPreferences

TITLE='画心 · 书画整理工作台'


def window_options(root):
    """Restore bounded window dimensions, keeping a first launch maximized."""
    try:
        state=json.loads((root/'desktop-window.json').read_text('utf-8'))
        return dict(width=max(1024,min(1920,int(state['width']))),height=max(700,min(1200,int(state['height']))),maximized=bool(state.get('maximized',True)))
    except (OSError,ValueError,KeyError,TypeError):
        return dict(width=1360,height=900,maximized=True)


def smoke_test(app, httpd):
    """Exercise the bundled assets and image pipeline without touching real data."""
    import io
    import re
    from PIL import Image
    url=f'http://127.0.0.1:{httpd.server_port}'
    with urllib.request.urlopen(url) as response:
        html=response.read().decode('utf-8')
    assert '__TOKEN__' not in html and app.TOKEN in html
    assets=set(re.findall(r'(?:src|href)=["\'](/[^"\']+\.(?:js|css|svg))["\']',html))
    assert assets
    for asset in assets:
        with urllib.request.urlopen(url+asset) as response:assert response.read()
    image=Image.new('RGB',(160,240),'ivory')
    source=io.BytesIO();image.save(source,'PNG')
    request=urllib.request.Request(url+'/api/import?name=desktop-smoke.png',data=source.getvalue(),headers={'X-App-Token':app.TOKEN,'Origin':url},method='POST')
    with urllib.request.urlopen(request) as response:item=json.load(response)
    with app.render(app.source(item),item['points'],0) as result:assert result.size==(160,240)
    report=dict(ok=True,assets=len(assets),data=str(app.DATA),image=item['id'])
    destination=os.environ.get('SCROLL_STUDIO_SMOKE_REPORT')
    if destination:Path(destination).write_text(json.dumps(report,ensure_ascii=False),'utf-8')
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke-test',action='store_true')
    args=parser.parse_args()
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    assets=Path(__file__).resolve().parent/'assets'
    # The desktop trial keeps its own library beside the executable by default.
    os.environ.setdefault('PYWEBVIEW_LOG','error')
    (root/'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=root/'logs'/'desktop.log',encoding='utf-8',level=logging.INFO)
    if os.name=='nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ScrollStudio.Huaxin.Desktop')
    mutex=None
    if os.name=='nt' and not args.smoke_test:
        # Separate package copies must not open the same configured library twice.
        import hashlib
        from data_store import data_directory
        name='Local\\ScrollStudio-'+hashlib.sha256(str(data_directory(root).resolve()).casefold().encode()).hexdigest()[:24]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
        kernel.CreateMutexW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,False,name)
        if not mutex:raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            ctypes.windll.user32.MessageBoxW(None,'画心已经打开，请切换到已有窗口。','画心',64)
            kernel.CloseHandle(ctypes.c_void_p(mutex));return
    lifecycle=dict(httpd=None,app=None,starting=True,closed=False,error=False,exiting=False,tray=None)
    preferences=DesktopPreferences(root)
    try:
        if args.smoke_test:
            import server as app
            httpd=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            lifecycle['httpd']=httpd
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            smoke_test(app,httpd);return
        import webview
        options=window_options(root)
        maximized=[options['maximized']]
        startup=(assets/'starting.html').read_text('utf-8').replace('__ICON__',(assets.parent/'static'/'app-icon.svg').read_text('utf-8'))
        class DesktopBridge:
            def report_client_error(self,message):logging.error('Workbench script: %s',str(message)[:1200])
            def get_settings(self):return dict(close_action=preferences.read()['close_action'])
            def set_close_action(self,action):return dict(close_action=preferences.update(close_action=action)['close_action'])
            def resolve_close(self,action,remember=False):
                if action not in ('tray','exit'):raise ValueError('关闭方式不正确')
                if remember:preferences.update(close_action=action)
                if action=='tray':window.hide()
                else:
                    if not can_exit():return dict(ok=False)
                    save_window()
                    lifecycle['exiting']=True;window.destroy()
                return dict(ok=True)
        bridge=DesktopBridge()
        window=webview.create_window(TITLE,html=startup,js_api=bridge,**options,min_size=(1024,700),background_color='#f6f2e9')
        def restore(*_):
            window.show()
            if maximized[0]:window.maximize()
            else:window.restore()
        def tray_exit(*_):
            restore()
            window.evaluate_js("window.requestDesktopClose && window.requestDesktopClose('exit')")
        def start_tray():
            import pystray
            from PIL import Image
            icon=pystray.Icon('ScrollStudio',Image.open(assets/'app-icon.png'),TITLE,menu=pystray.Menu(pystray.MenuItem('打开画心',restore,default=True),pystray.Menu.SEPARATOR,pystray.MenuItem('退出画心',tray_exit)))
            icon.run_detached();lifecycle['tray']=icon
        def bootstrap():
            try:
                window.events.loaded.wait(20)
                import server as app
                if lifecycle['closed']:return
                httpd=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
                lifecycle.update(app=app,httpd=httpd)
                threading.Thread(target=httpd.serve_forever,daemon=True).start()
                start_tray()
                app.start_prepare()
                window.load_url(f'http://127.0.0.1:{httpd.server_port}')
                lifecycle['starting']=False
            except Exception:
                lifecycle.update(starting=False,error=True)
                logging.exception('Workbench initialization failed')
                window.evaluate_js("document.getElementById('status').textContent='工作台启动失败，请查看 logs/desktop.log';document.getElementById('loading').style.display='none'")
        def can_exit():
            app=lifecycle['app']
            if lifecycle['starting']:return False
            if app is None:return True
            if app.JOB['running'] or app.BATCH.job['running'] or app.RECOGNITION.job['running'] or app.STORAGE.status()['running'] or app.STORAGE.active:
                ctypes.windll.user32.MessageBoxW(None,'图片处理或文件保存仍在进行，请等待完成后关闭。','画心',64)
                return False
            return True
        def closing():
            if lifecycle['exiting']:return
            if lifecycle['starting']:return False
            if lifecycle['error']:return
            action=preferences.read()['close_action']
            if action=='exit':
                threading.Thread(target=lambda:window.evaluate_js("window.requestDesktopClose && window.requestDesktopClose('exit')"),daemon=True).start()
                return False
            if action=='tray':
                threading.Thread(target=window.hide,daemon=True).start();return False
            # Closing handlers run synchronously on the WinForms UI thread.
            # Never wait for JavaScript (or invoke WinForms) from that thread.
            threading.Thread(target=lambda:window.evaluate_js('window.showDesktopCloseDialog && window.showDesktopCloseDialog()'),daemon=True).start()
            return False
        def closed():
            lifecycle['closed']=True
        def save_window():
            try:
                state=dict(width=window.width,height=window.height,maximized=maximized[0])
                preferences.update(**state)
            except Exception:logging.exception('Could not save window state')
        def on_maximized():maximized[0]=True
        def on_restored():maximized[0]=False
        window.events.maximized+=on_maximized
        window.events.restored+=on_restored
        window.events.closing+=closing
        window.events.closed+=closed
        # WebView2 uses the installed Microsoft Edge runtime, no external browser.
        webview.start(bootstrap,gui='edgechromium',private_mode=True,icon=str(assets/'app.ico'))
    except Exception:
        logging.exception('Desktop startup failed')
        if args.smoke_test:sys.exit(1)
        ctypes.windll.user32.MessageBoxW(None,'启动失败，请查看程序目录 logs\\desktop.log。\n需要 Microsoft Edge WebView2 运行时。','画心',16)
    finally:
        if lifecycle['tray']:lifecycle['tray'].stop()
        httpd=lifecycle['httpd']
        if httpd:
            httpd.shutdown();httpd.server_close()
        if mutex:kernel.CloseHandle(ctypes.c_void_p(mutex))


if __name__=='__main__':main()
