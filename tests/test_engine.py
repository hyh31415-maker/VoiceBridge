import asyncio
import base64
import json
import math
import struct
import threading
import unittest
from unittest.mock import patch,MagicMock
from aiohttp import web
from voicebridge.audio import PCMBuffer,Resampler
from voicebridge.engine import Translator,Policy,FatalServiceError,AudioSession,service_error
from voicebridge.service import session_config,safe_error

CONFIG=session_config({'target':'en','speak':True,'doc':True,'terms':{'DOC':'D O C'}},{'voice':'Ethan','mode':None})

class BufferTests(unittest.TestCase):
    def test_bounded_fifo_and_reinsert(self):
        b=PCMBuffer(8);b.put(b'1234');b.put(b'5678');b.put(b'90');self.assertEqual(b.dropped,4)
        x=b.get();self.assertEqual(x,b'5678');b.put(x,front=True);self.assertEqual(b.take(8),b'567890\0\0')
    def test_resampling_retains_fractional_state(self):
        data=b''.join(struct.pack('<h',int(4000*math.sin(i*.1))) for i in range(44100))
        r=Resampler(44100,16000)
        chunked=b''.join(r.process(data[i:i+882]) for i in range(0,len(data),882))
        full=Resampler(44100,16000).process(data)
        self.assertEqual(chunked,full);self.assertLessEqual(abs(len(full)-32000),2)
    def test_secret_mask(self):self.assertNotIn('sk-example',safe_error('bad sk-example'))
    def test_default_microphone_resolves_input_direction(self):
        import queue
        events=queue.Queue();session=AudioSession(events,None,None,{},dict(voice='Ethan'),local_only=True);session.stop.set()
        def devices(device,kind=None):
            if kind!='input':return ({'default_samplerate':48000},)
            return {'default_samplerate':48000}
        with patch('voicebridge.engine.sd.query_devices',side_effect=devices),patch('voicebridge.engine.sd.RawInputStream',return_value=MagicMock()):
            worker=threading.Thread(target=session.run);worker.start();worker.join(3)
        emitted=list(events.queue);self.assertFalse(any(k=='error' for k,v in emitted),emitted)
    def test_context_overflow_is_recoverable(self):
        error=service_error({'error':{'code':'invalid_request_error','message':'maximum context length exceeded'}})
        self.assertIsInstance(error,ConnectionError);self.assertNotIsInstance(error,FatalServiceError)

class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stop=threading.Event();self.abort=threading.Event();self.input=PCMBuffer();self.output=PCMBuffer();self.events=[]
        self.connections=0;self.received=[];self.finishes=0;self.disconnect_once=False;self.auth_error=False
        async def ws_handler(request):
            ws=web.WebSocketResponse();await ws.prepare(request);self.connections+=1;n=self.connections
            if self.auth_error:
                await ws.send_json({'type':'error','error':{'code':'invalid_api_key','message':'invalid'}});await ws.close();return ws
            await ws.send_json({'type':'session.created'})
            await ws.receive_json();await ws.send_json({'type':'session.updated','session':CONFIG})
            async for msg in ws:
                e=json.loads(msg.data)
                if e['type']=='input_audio_buffer.append':
                    data=base64.b64decode(e['audio']);self.received.append(data)
                    if self.disconnect_once and n==1:
                        await ws.close();return ws
                    await ws.send_json({'type':'response.text.delta','item_id':'same-id','delta':'ok'})
                    if len(self.received)>=self.stop_at:self.stop.set()
                if e['type']=='session.finish':
                    self.finishes+=1;await ws.send_json({'type':'session.finished'});await ws.close();return ws
            return ws
        app=web.Application();app.router.add_get('/ws',ws_handler)
        self.runner=web.AppRunner(app);await self.runner.setup();site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        self.url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])+'/ws';self.stop_at=8
    async def asyncTearDown(self):await self.runner.cleanup()
    def engine(self,**values):
        return Translator(CONFIG,'test-key',lambda k,v:self.events.append((k,v)),self.input,self.output,self.stop,self.abort,
                          Policy(retry_delays=(.01,),finish_timeout=.5,**values),self.url)
    async def test_reconnect_preserves_unsent_audio(self):
        self.disconnect_once=True
        for i in range(12):self.input.put(bytes([i,0])*1600)
        await asyncio.wait_for(self.engine(rotate_seconds=100).run(),5)
        self.assertGreaterEqual(self.connections,2)
        self.assertEqual(self.received[-1],bytes([11,0])*1600)
        self.assertTrue(any(k=='notice' for k,v in self.events));self.assertEqual(self.finishes,1)
    async def test_rotation_keeps_audio_order_and_prefixes_ids(self):
        self.stop_at=12
        for _ in range(12):self.input.put(bytes(3200))
        await asyncio.wait_for(self.engine(rotate_seconds=.12,rotation_grace=.1,quiet_seconds=.01).run(),5)
        self.assertGreater(self.connections,1);self.assertEqual(len(self.received),12)
        ids={v[0] for k,v in self.events if k=='translation'};self.assertGreater(len(ids),1)
        self.assertGreaterEqual(self.finishes,2)
    async def test_auth_errors_do_not_loop(self):
        self.auth_error=True;self.input.put(bytes(3200))
        with self.assertRaises(FatalServiceError):await self.engine().run()
        self.assertEqual(self.connections,1)
    async def test_token_budget_rotates_at_quiet_boundary(self):
        engine=self.engine();engine.session_start=100;engine.last_voice=100;engine.tokens=30001
        self.assertTrue(engine.rotation_due(101));engine.last_voice=100.5;self.assertFalse(engine.rotation_due(101))
    async def test_abort_ends_stream(self):
        async def abort():await asyncio.sleep(.1);self.abort.set()
        await asyncio.wait_for(asyncio.gather(self.engine().run(),abort()),2)

if __name__=='__main__':unittest.main()

