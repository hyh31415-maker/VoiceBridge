import base64
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shlex
import subprocess
import sys

IS_WINDOWS=sys.platform=='win32'
IS_MAC=sys.platform=='darwin'
FONT='PingFang SC' if IS_MAC else 'Microsoft YaHei UI'

def data_directory():
    if IS_MAC:return Path.home()/'Library'/'Application Support'/'VoiceBridge'
    if IS_WINDOWS:return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'VoiceBridge'
    return Path.home()/'.local'/'share'/'VoiceBridge'

def com_start():return ctypes.windll.ole32.CoInitializeEx(None,0) if IS_WINDOWS else 0
def com_end(result):
    if IS_WINDOWS and result in (0,1):ctypes.windll.ole32.CoUninitialize()

def open_folder(path):
    if IS_WINDOWS:os.startfile(path)
    else:subprocess.Popen(['open' if IS_MAC else 'xdg-open',str(path)])

def _dpapi(data,protect):
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));result=Blob()
    fn=ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):raise ctypes.WinError()
    try:return ctypes.string_at(result.data,result.size)
    finally:ctypes.windll.kernel32.LocalFree(result.data)

def save_secret(key,path):
    key=key.strip()
    if IS_MAC:
        # Pass the secret on stdin, never in a command-line argument or log.
        command='add-generic-password -U -a VoiceBridge -s org.voicebridge.apikey -w '+shlex.quote(key)+'\n'
        result=subprocess.run(['/usr/bin/security','-i'],input=command,text=True,capture_output=True)
        if result.returncode:raise RuntimeError('无法写入 macOS 钥匙串。')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(_dpapi(key.encode(),True) if IS_WINDOWS else key.encode())
        if not IS_WINDOWS:path.chmod(0o600)

def read_secret(path):
    if IS_MAC:
        result=subprocess.run(['/usr/bin/security','find-generic-password','-a','VoiceBridge','-s','org.voicebridge.apikey','-w'],capture_output=True,text=True)
        return result.stdout.strip() if result.returncode==0 else ''
    if not path.exists():return ''
    data=path.read_bytes();return (_dpapi(data,False) if IS_WINDOWS else data).decode().strip()
