import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from .platform_support import data_directory,read_secret,save_secret

DATA = Path(os.environ.get('VOICEBRIDGE_DATA_DIR', str(data_directory())))
DEFAULTS = {'target':'en','voice':'Ethan','input':'','output':'','speak':True,'doc':True,
            'font_size':12,'autosave':True,'rotate_seconds':300,'reconnect':True,'volume':80,
            'terms':{'DOC':'D O C','溶解性有机碳':'dissolved organic carbon'},
            'model':'qwen3.8-livetranslate-flash-realtime','protocol':'qwen38',
            'endpoint':'wss://maas.qianwenaiapi.com/api-ws/v1/realtime',
            'enrollment':'https://maas.qianwenaiapi.com/api/v1/services/audio/tts/customization'}
PRESETS = [dict(id=v, name=n, voice=v, mode=None) for v,n in
           [('Ethan','Ethan · 阳光男声'),('Tina','Tina · 温暖女声'),('Serena','Serena · 温柔女声'),('Cindy','Cindy · 甜美女声')]] + [
    dict(id='once',name='我的声音 · 实时复刻',voice='default',mode='once'),
    dict(id='always',name='跟随发言人 · 多人复刻',voice='default',mode='always')]

def read_json(name, default):
    path=DATA/name
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))

def write_json(name, value):
    DATA.mkdir(parents=True,exist_ok=True)
    target=DATA/name
    pending=target.with_suffix('.pending')
    pending.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(pending,target)

def settings():
    return {**DEFAULTS,**read_json('settings.json',{})}

def load_key():
    key=read_secret(DATA/'credential.bin') or os.environ.get('VOICEBRIDGE_API_KEY','').strip()
    if key:return key
    try:
        from embedded_key import get_key
        return get_key()
    except ImportError:
        raise RuntimeError('请先在设置中填写 API key。') from None

def set_key(key):save_secret(key,DATA/'credential.bin')

class VoiceLibrary:
    def load(self): return read_json('voices.json',[dict(p) for p in PRESETS])
    def write(self,rows): write_json('voices.json',rows)
    def check_name(self,name,exclude=None):
        name=name.strip()
        if not 1<=len(name)<=40: raise ValueError('声音名称需为 1～40 个字。')
        if any(r['id']!=exclude and r['name'].casefold()==name.casefold() for r in self.load()): raise ValueError('这个名称已经存在。')
        return name
    def add(self,name,voice):
        row=dict(id=uuid.uuid4().hex,name=self.check_name(name),voice=voice,mode='never')
        rows=self.load();rows.append(row);self.write(rows);return row
    def rename(self,identity,name):
        name=self.check_name(name,identity);rows=self.load()
        next(r for r in rows if r['id']==identity)['name']=name;self.write(rows)

class History:
    def __init__(self):
        DATA.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(DATA/'history.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created TEXT, target TEXT, voice TEXT, state TEXT); CREATE TABLE IF NOT EXISTS lines(session TEXT, item TEXT, kind TEXT, at REAL, text TEXT, PRIMARY KEY(session,item,kind));')
        self.db.execute("UPDATE sessions SET state='意外中断，已恢复文字' WHERE state='进行中'");self.db.commit()
    def start(self,target,voice):
        identity=uuid.uuid4().hex
        self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(identity,dt.datetime.now().isoformat(timespec='seconds'),target,voice,'进行中'));self.db.commit();return identity
    def put(self,session,item,kind,at,text):
        self.db.execute('INSERT INTO lines VALUES(?,?,?,?,?) ON CONFLICT(session,item,kind) DO UPDATE SET text=excluded.text',(session,item,kind,at,text))
    def flush(self): self.db.commit()
    def end(self,identity,state='已结束'):
        self.db.execute('UPDATE sessions SET state=? WHERE id=?',(state,identity));self.db.commit()
    def list(self,query=''):
        return self.db.execute('SELECT s.id,s.created,s.target,s.voice,s.state FROM sessions s WHERE s.created LIKE ? OR s.voice LIKE ? OR EXISTS(SELECT 1 FROM lines l WHERE l.session=s.id AND l.text LIKE ?) ORDER BY created DESC LIMIT 200',tuple('%'+query+'%' for _ in range(3))).fetchall()
    def lines(self,identity): return self.db.execute('SELECT kind,at,text FROM lines WHERE session=? ORDER BY at,rowid',(identity,)).fetchall()

def timestamp(seconds):
    return f'{int(seconds)//3600:02}:{int(seconds)//60%60:02}:{int(seconds)%60:02}'

def export_text(rows):
    return '\n\n'.join(f'[{timestamp(at)}] '+{'source':'原文','translation':'译文','notice':'提示'}.get(kind,kind)+'\n'+text for kind,at,text in rows)

def export_srt(rows):
    selected=[r for r in rows if r[0]=='translation']
    def stamp(s):return timestamp(s)+f',{int(s*1000)%1000:03}'
    return '\n\n'.join(f'{i+1}\n{stamp(at)} --> {stamp(max(at+1,selected[i+1][1] if i+1<len(selected) else at+5))}\n{text}' for i,(_,at,text) in enumerate(selected))
