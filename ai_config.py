"""Local connection settings; secrets protected by the current Windows account."""
import base64
import ctypes
import json
import os
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect_secret(value,decrypt=False):
    if os.name!='nt':raise ValueError('当前系统不支持 Windows 本机密钥加密，未写入 Key')
    buffer=ctypes.create_string_buffer(value)
    source=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if decrypt:
        fn=crypt.CryptUnprotectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    else:
        fn=crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        args=(ctypes.byref(source),'Scroll Studio AI connection',None,None,None,1,ctypes.byref(output))
    fn.restype=wintypes.BOOL
    if not fn(*args):raise ValueError('无法'+('解密' if decrypt else '加密')+'本机 AI Key，请使用原 Windows 账户或重新配置')
    try:return ctypes.string_at(output.data,output.size)
    finally:kernel.LocalFree(ctypes.cast(output.data,ctypes.c_void_p))


def save_connection(path,base_url,model,key):
    settings=dict(version=1,base_url=base_url,model=model,key_dpapi=base64.b64encode(protect_secret(key.encode())).decode() if key else '')
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(settings,ensure_ascii=False,indent=2),'utf-8')
    os.replace(temporary,path)


def load_connection(path):
    if not path.exists():return {}
    settings=json.loads(path.read_text('utf-8'))
    if settings.get('version')!=1:raise ValueError('本机 AI 配置版本不支持，请重新保存连接')
    encrypted=settings.get('key_dpapi','')
    return dict(base_url=settings['base_url'],model=settings['model'],key=protect_secret(base64.b64decode(encrypted),True).decode() if encrypted else '')
