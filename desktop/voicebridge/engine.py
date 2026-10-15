from .platform_support import com_start,com_end
"""Direct streaming with bounded recovery and sentence-aware session rotation."""
import asyncio
import base64
import contextlib
import ctypes
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
import queue
import threading
import time

import aiohttp
import sounddevice as sd
import audioop
from .audio import PCMBuffer,Resampler,level
from .service import URL,session_config,safe_error,endpoint_url
from .storage import DATA,load_key

class FatalServiceError(RuntimeError):pass

def service_error(event):
    error=event.get('error',event)
    code=str(error.get('code','')).lower();message=error.get('message','服务暂时不可用')
    combined=(code+' '+message).lower()
    if any(part in combined for part in ('context_length','context length','context window','maximum context','上下文','input too long')):
        return ConnectionError('会话上下文接近或达到限制，自动建立新会话。')
    if any(part in code for part in ('auth','api_key','permission','invalid_parameter','invalid_request','insufficient','quota')):
        return FatalServiceError(message)
    return ConnectionError(message)

@dataclass
class Policy:
    rotate_seconds:float=300
    rotation_grace:float=30
    quiet_seconds:float=.8
    token_budget:int=30000
    finish_timeout:float=12
    retry_delays:tuple=(1,2,4,8,15)
    max_retry_seconds:float=300
    max_retries:int=20

class Translator:
    def __init__(self,config,key,emit,incoming,playback,stop,abort,policy=None,url=URL):
        self.config=config;self.key=key;self.emit=emit;self.incoming=incoming;self.playback=playback
        self.stop=stop;self.abort=abort;self.policy=policy or Policy();self.url=url
        self.segment=0;self.total_sent=0;self.session_sent=0;self.tokens=0;self.spoken_at=0
        self.last_voice=time.monotonic();self.health=None;self.reconnect=True;self.ws=None
        self.paused=False;self.last_drop=0;self.audio_converter=Resampler(24000,24000)
        self.first_output=None;self.session_start=0;self.retry_count=0;self.current_task=None;self.last_event=0;self.legacy_text={}

    async def connect(self,client):
        ws=await client.ws_connect(self.url,headers={'Authorization':'Bearer '+self.key},
                                   heartbeat=10,max_msg_size=8_000_000)
        try:
            event=await asyncio.wait_for(ws.receive_json(),15)
            if event.get('type')!='session.created':raise service_error(event)
            await ws.send_json({'type':'session.update','session':self.config})
            event=await asyncio.wait_for(ws.receive_json(),15)
            if event.get('type')!='session.updated':raise service_error(event)
            received=event.get('session',{})
            actual=received.get('audio',{}).get('output',{}).get('voice',received.get('voice'))
            if actual and actual!=self.config['voice']:raise FatalServiceError('服务器没有确认所选音色。')
            return ws
        except BaseException:
            await ws.close();raise

    def handle(self,event):
        self.last_event=time.monotonic()
        kind=event.get('type','')
        if kind=='error':raise service_error(event)
        item=f'{self.segment}:'+(event.get('item_id') or event.get('response_id') or 'current')
        if kind=='conversation.item.input_audio_transcription.delta':self.emit('source',(item,event.get('delta',''),True))
        elif kind=='conversation.item.input_audio_transcription.completed':self.emit('source',(item,event.get('transcript',''),False))
        elif kind in ('response.audio_transcript.text','response.text.text','conversation.item.input_audio_transcription.text'):
            self.legacy_text[item]=self.legacy_text.get(item,'')+event.get('text','')
            self.emit('source' if kind.startswith('conversation') else 'translation',(item,self.legacy_text[item]+event.get('stash',''),False))
        elif kind in ('response.audio_transcript.delta','response.text.delta'):
            self.emit('translation',(item,event.get('delta',''),True))
            if self.first_output is None:
                self.first_output=time.monotonic();self.emit('first_output',self.first_output-self.session_start)
        elif kind in ('response.audio_transcript.done','response.text.done'):
            self.emit('translation',(item,event.get('transcript') or event.get('text',''),False))
        elif kind=='response.audio.delta':
            pcm=self.audio_converter.process(base64.b64decode(event['delta']))
            self.playback.put(pcm)
        elif kind=='response.done':
            response=event.get('response',{})
            if response.get('status') in ('failed','incomplete'):
                detail=response.get('status_details') or {}
                raise service_error(detail if isinstance(detail,dict) else {'message':str(detail)})
            usage=response.get('usage') or event.get('usage') or {}
            # A conservative accumulated usage budget; do not claim an exact live context meter.
            self.tokens+=int(usage.get('total_tokens',0) or 0)
        return kind

    async def receive(self,ws,finished):
        async for message in ws:
            if self.abort.is_set():return
            if message.type==aiohttp.WSMsgType.TEXT:
                if self.handle(message.json())=='session.finished':finished.set();return
            elif message.type==aiohttp.WSMsgType.ERROR:raise ConnectionError('连接中断。')
        if not finished.is_set() and not self.abort.is_set():raise ConnectionError('同传连接提前结束。')

    def rotation_due(self,now):
        age=now-self.session_start
        due=age>=self.policy.rotate_seconds or self.tokens>=self.policy.token_budget
        return due and (now-self.last_voice>=self.policy.quiet_seconds or age>=self.policy.rotate_seconds+self.policy.rotation_grace)

    async def stream(self,ws,client):
        self.session_start=time.monotonic();self.last_voice=self.session_start;self.last_event=self.session_start
        self.session_sent=0;self.tokens=0;self.first_output=None;self.legacy_text={}
        finished=asyncio.Event();receiver=asyncio.create_task(self.receive(ws,finished));next_connection=None;handed_off=False
        stopped_at=None;next_health=0;sent_drop=self.incoming.dropped;output_drop=self.playback.dropped
        try:
            while not self.abort.is_set():
                now=time.monotonic()
                if receiver.done():
                    await receiver
                    if self.stop.is_set():return None
                    raise ConnectionError('会话已结束，需要重新连接。')
                if self.health and now>=next_health:self.health();next_health=now+1
                if self.session_sent>10 and now-self.last_voice<5 and now-self.last_event>45:
                    raise ConnectionError('持续讲话但服务 45 秒没有返回事件，准备重新连接。')
                if self.stop.is_set() and stopped_at is None:stopped_at=now
                if self.incoming.dropped!=sent_drop:
                    lost=(self.incoming.dropped-sent_drop)/32000;sent_drop=self.incoming.dropped
                    self.emit('notice',f'待发送缓存已满，舍弃最早 {lost:.1f} 秒录音。请复述遗漏部分。')
                if self.playback.dropped!=output_drop:
                    output_drop=self.playback.dropped;self.emit('notice','译音播放积压已超过上限，跳过过旧译音；文字仍保留。')
                rotating=not self.stop.is_set() and self.rotation_due(now)
                stopping=self.stop.is_set() and (not self.incoming.size or now-stopped_at>20)
                if rotating or stopping:
                    if rotating:
                        self.emit('state','续接中');self.emit('status','正在续接新会话，麦克风继续采集。')
                        next_connection=asyncio.create_task(self.connect(client))
                    elif self.incoming.size:
                        self.emit('notice','停止等待已达上限，部分断线缓存尚未发送。');self.incoming.clear()
                    await asyncio.wait_for(ws.send_json({'type':'session.finish'}),8)
                    try:await asyncio.wait_for(asyncio.shield(receiver),self.policy.finish_timeout)
                    except asyncio.TimeoutError:
                        self.emit('notice','上一段结束确认超时，末尾可能不完整，请核对文字。')
                    if next_connection:
                        prepared=await next_connection;handed_off=True;return prepared
                    return None
                data=self.incoming.get()
                if data:
                    try:
                        await asyncio.wait_for(ws.send_json({'type':'input_audio_buffer.append','audio':base64.b64encode(data).decode()}),8)
                    except BaseException:
                        self.incoming.put(data,front=True);raise
                    self.total_sent+=len(data)/32000;self.session_sent+=len(data)/32000
                    if level(data)>-48:self.last_voice=now
                    self.emit('sent',(self.total_sent,self.incoming.size/32000))
                    # Catch-up is bounded at 2x realtime, preserving order without flooding the API.
                    await asyncio.sleep(len(data)/64000)
                else:await asyncio.sleep(.015)
            return None
        finally:
            receiver.cancel();await asyncio.gather(receiver,return_exceptions=True)
            if next_connection and not next_connection.done():
                next_connection.cancel();await asyncio.gather(next_connection,return_exceptions=True)
            elif next_connection and not handed_off:
                with contextlib.suppress(BaseException):await next_connection.result().close()
            await ws.close()

    async def run(self):
        failed_since=None;attempt=0;prepared=None
        timeout=aiohttp.ClientTimeout(total=None,sock_connect=12)
        async with aiohttp.ClientSession(timeout=timeout) as client:
            try:
                while not self.abort.is_set():
                    if self.stop.is_set() and prepared is None and not self.incoming.size:return
                    try:
                        self.emit('state','连接中' if not attempt else '重连中')
                        self.ws=prepared or await self.connect(client);prepared=None
                        self.segment+=1;self.emit('segment',self.segment);self.emit('state','已连接')
                        self.emit('status','正在同传。讲话停顿时会自动续接新会话。')
                        connected_at=time.monotonic()
                        prepared=await self.stream(self.ws,client)
                        if time.monotonic()-connected_at>10:failed_since=None;attempt=0
                        if self.stop.is_set() or self.abort.is_set():return
                        attempt=0;failed_since=None
                    except FatalServiceError:raise
                    except aiohttp.WSServerHandshakeError as error:
                        if error.status in (400,401,403,404):raise FatalServiceError(f'接口拒绝连接（{error.status}），请检查密钥、额度或模型权限。') from None
                        self.emit('notice',f'服务器暂时不可用（{error.status}），准备重连。')
                    except (aiohttp.ClientError,OSError,TimeoutError,ConnectionError) as error:
                        self.emit('notice','连接中断：'+safe_error(error,self.key)+'；已经发送但未确认的末尾可能不完整。')
                    else:continue
                    if self.stop.is_set() or self.abort.is_set():
                        if self.incoming.size:self.emit('notice','已停止：断线期间尚未发送的录音未完成翻译。')
                        return
                    if not self.reconnect:raise ConnectionError('连接已中断，自动重连未开启。')
                    failed_since=failed_since or time.monotonic();attempt+=1;self.retry_count+=1
                    if time.monotonic()-failed_since>self.policy.max_retry_seconds or attempt>self.policy.max_retries:
                        raise ConnectionError('重连未成功，已停止。请检查网络后重新开始。')
                    delay=self.policy.retry_delays[min(attempt-1,len(self.policy.retry_delays)-1)]
                    self.emit('state','重连中');self.emit('status',f'{delay} 秒后自动重连（第 {attempt} 次）；最多缓存 60 秒待发送录音。')
                    until=time.monotonic()+delay
                    while time.monotonic()<until and not self.stop.is_set() and not self.abort.is_set():await asyncio.sleep(.1)
            finally:
                if prepared:await prepared.close()
                if self.ws:await self.ws.close()

class AudioSession:
    def __init__(self,events,input_device,output_device,options,profile,local_only=False):
        self.events=events;self.input_device=input_device;self.output_device=output_device
        self.options=dict(options);self.profile=profile;self.local_only=local_only
        self.stop=threading.Event();self.abort=threading.Event();self.paused=False
        self.input=PCMBuffer();self.output=PCMBuffer(24000*2*30)
        self.volume=options.get('volume',80)/100;self.frames=0;self.last_callback=time.monotonic()
        self.worker=threading.Thread(target=self.run,daemon=True);self.translator=None
    def emit(self,kind,value):self.events.put((kind,value))
    def input_callback(self,data,frames,timing,status):
        self.last_callback=time.monotonic();self.frames+=frames
        self.emit('level',(level(bytes(data)),self.frames/self.input_rate))
        if status:self.emit('warning','录音设备提示：'+str(status))
        if not self.local_only and not self.stop.is_set():
            pcm=self.resampler.process(bytes(data))
            self.input.put(bytes(len(pcm)) if self.paused else pcm)
    def output_callback(self,outdata,frames,timing,status):
        data=self.output.take(frames*2)
        outdata[:]=audioop.mul(data,2,self.volume) if self.volume!=1 else data
    def check_input(self):
        if not self.stop.is_set() and time.monotonic()-self.last_callback>5:
            raise FatalServiceError('麦克风已断开或停止采集。请重新连接设备，再点击开始。')
    def run(self):
        hr=com_start();recorder=player=None
        key=''
        try:
            if hr not in (0,1):raise RuntimeError('Windows 音频初始化失败。')
            self.input_rate=int(sd.query_devices(self.input_device,kind='input')['default_samplerate'])
            self.resampler=Resampler(self.input_rate,16000)
            recorder=sd.RawInputStream(device=self.input_device,samplerate=self.input_rate,channels=1,dtype='int16',blocksize=self.input_rate//10,callback=self.input_callback)
            recorder.start();self.last_callback=time.monotonic()
            if self.local_only:
                self.emit('state','检测中');self.emit('status','请讲话并观察音量。检测只在本机进行。')
                while not self.stop.wait(.2):self.check_input()
                return
            output_rate=24000
            if self.options['speak']:
                try:sd.check_output_settings(device=self.output_device,channels=1,dtype='int16',samplerate=output_rate)
                except sd.PortAudioError:output_rate=int(sd.query_devices(self.output_device,kind='output')['default_samplerate'])
                self.output.limit=output_rate*2*30
                player=sd.RawOutputStream(device=self.output_device,samplerate=output_rate,channels=1,dtype='int16',blocksize=output_rate//20,callback=self.output_callback)
                player.start()
            key=load_key()
            self.translator=Translator(session_config(self.options,self.profile),key,self.emit,self.input,self.output,self.stop,self.abort,
                                       Policy(rotate_seconds=self.options.get('rotate_seconds',300)),url=endpoint_url(self.options))
            self.translator.audio_converter=Resampler(24000,output_rate)
            self.translator.reconnect=self.options.get('reconnect',True);self.translator.health=self.check_input
            asyncio.run(self.translator.run())
            recorder.stop()
            deadline=time.monotonic()+30
            while self.output.size and not self.abort.is_set() and time.monotonic()<deadline:time.sleep(.05)
        except Exception as error:
            message=safe_error(error,key);self.emit('error',message)
            DATA.mkdir(parents=True,exist_ok=True)
            logger=logging.getLogger('voicebridge');logger.setLevel(logging.INFO)
            if not logger.handlers:
                logger.addHandler(RotatingFileHandler(DATA/'diagnostics.log',maxBytes=500000,backupCount=2,encoding='utf-8'))
            logger.error('%s %s',time.strftime('%Y-%m-%d %H:%M:%S'),message)
        finally:
            for stream in (recorder,player):
                if stream:
                    with contextlib.suppress(Exception):stream.stop();stream.close()
            if hr in (0,1):com_end(hr)
            self.emit('done',None)
