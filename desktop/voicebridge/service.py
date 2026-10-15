import asyncio
import base64
import io
import re
import uuid
import wave
import aiohttp
from .storage import load_key,settings
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from .languages import audio as language_audio

MODEL='qwen3.8-livetranslate-flash-realtime'
URL='wss://maas.qianwenaiapi.com/api-ws/v1/realtime?model='+MODEL
ENROLL='https://maas.qianwenaiapi.com/api/v1/services/audio/tts/customization'

def endpoint_url(options):
    parts=urlsplit(options.get('endpoint',URL.split('?')[0]).strip())
    if parts.scheme!='wss' or not parts.hostname or parts.username or parts.password:raise ValueError('接口地址必须为不含用户名或密码的 wss:// 地址。')
    query=dict(parse_qsl(parts.query));query['model']=options.get('model',MODEL).strip()
    if not query['model']:raise ValueError('请填写模型名称。')
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),''))

def safe_error(error,key=''):
    text=str(error) or type(error).__name__
    if key:text=text.replace(key,'[redacted]')
    return re.sub(r'sk-[A-Za-z0-9_-]+','[redacted]',text)[:500]

def session_config(options,profile):
    cfg={'output_modalities':['text','audio'] if options['speak'] and language_audio(options['target']) else ['text'],
         'voice':profile['voice'],'audio':{'output':{'voice':profile['voice']}},
         'enable_voice_clone':profile['mode'] is not None,'translation':{'language':options['target']}}
    if profile['mode']:cfg['voice_clone_options']={'frequency':profile['mode']}
    if options.get('protocol')=='qwen35':
        cfg['modalities']=cfg.pop('output_modalities');cfg.pop('audio',None)
        cfg.update(sample_rate=16000,input_audio_format='pcm',output_audio_format='pcm',
                   input_audio_transcription={'model':'qwen3-asr-flash-realtime'},
                   turn_detection={'type':'server_vad','threshold':.2,'silence_duration_ms':800})
    terms=dict(options.get('terms',{}))
    if not options.get('doc'):terms.pop('DOC',None)
    if terms:cfg['translation']['corpus']={'phrases':terms}
    return cfg

def wav_bytes(pcm,rate):
    buf=io.BytesIO()
    with wave.open(buf,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(rate);audio.writeframes(pcm)
    return buf.getvalue()

async def create_voice(audio):
    key=load_key()
    options=settings();endpoint=options.get('enrollment',ENROLL)
    if not endpoint.startswith('https://'):raise ValueError('声音复刻接口需要 HTTPS。')
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as client:
            async with client.post(endpoint,headers={'Authorization':'Bearer '+key},json={'model':'qwen-voice-enrollment','input':{
                'action':'create','target_model':options.get('model',MODEL),'preferred_name':'speaker'+uuid.uuid4().hex[:8],
                'audio':{'data':'data:audio/wav;base64,'+base64.b64encode(audio).decode()}}}) as response:
                info=await response.json(content_type=None)
                if response.status!=200 or not info.get('output',{}).get('voice'):raise RuntimeError(info.get('message','音色创建失败。'))
                return info['output']['voice']
    except Exception as error:raise RuntimeError(safe_error(error,key)) from None
