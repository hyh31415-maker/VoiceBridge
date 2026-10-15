package org.voicebridge.app;
import android.app.*;
import android.content.*;
import android.os.*;
import android.util.Base64;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.json.*;
import javax.net.ssl.SSLParameters;
import java.util.*;
import java.util.concurrent.*;
import java.io.*;

/** Separate test APK only; never included in the production application. */
public class Smoke extends Instrumentation {
 public void onCreate(Bundle args){super.onCreate(args);start();}
 void check(boolean value,String reason)throws Exception{if(!value)throw new Exception(reason);}
 public void onStart(){Bundle result=new Bundle();Config cfg=new Config(getTargetContext());String key="";WebSocketClient socket=null;
  Map<String,?> saved=new HashMap<>(cfg.prefs.getAll());
  try{
   key=cfg.key();check(!key.isEmpty(),"embedded credential missing");result.putString("embedded_key","present");
   cfg.saveKey("instrumentation-placeholder");check(cfg.key().equals("instrumentation-placeholder"),"Keystore roundtrip");cfg.prefs.edit().remove("key_data").remove("key_iv").commit();result.putString("keystore","passed");
   cfg.prefs.edit().putString("target","ja").commit();check(cfg.audio(),"Japanese audio");cfg.prefs.edit().putString("target","it").putString("protocol","qwen35").commit();check(!cfg.audio()&&cfg.session().has("modalities"),"legacy text mode");cfg.prefs.edit().putString("target","en").putString("protocol","qwen38").commit();result.putString("languages","passed");
   MainActivity activity=(MainActivity)startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
   runOnMainSync(()->{for(String page:new String[]{"声音","术语","历史","设置","同传"})activity.show(page);});result.putString("pages","passed");
   for(int cycle=0;cycle<2;cycle++){
    runOnMainSync(()->activity.startForegroundService(new Intent(activity,VoiceService.class).putExtra("test",true)));
    Thread.sleep(2500);VoiceService service=VoiceService.instance;check(service!=null&&service.status.startsWith("麦克风检测"),"mic service start");service.stopNow();
    for(int wait=0;wait<40&&!service.status.equals("已结束");wait++)Thread.sleep(100);check(service.status.equals("已结束"),"mic service stop");Thread.sleep(500);
   }result.putString("mic_start_stop_restart","passed");
   final CountDownLatch ready=new CountDownLatch(1),finished=new CountDownLatch(1);final String[] failure={""};final boolean[] updated={false};final int[] texts={0},audio={0};
   socket=new WebSocketClient(cfg.uri(),Collections.singletonMap("Authorization","Bearer "+key)){
    protected void onSetSSLParameters(SSLParameters p){p.setEndpointIdentificationAlgorithm("HTTPS");}
    public void onOpen(ServerHandshake h){}
    public void onClose(int c,String r,boolean remote){ready.countDown();finished.countDown();}
    public void onError(Exception e){failure[0]=e.getClass().getSimpleName();ready.countDown();finished.countDown();}
    public void onMessage(String raw){try{JSONObject e=new JSONObject(raw);String type=e.optString("type");
     if(type.equals("session.created"))send(Config.obj("type","session.update","session",cfg.session()).toString());
     if(type.equals("session.updated")){updated[0]=true;ready.countDown();}
     if(type.equals("error")){failure[0]="service error";ready.countDown();finished.countDown();}
     if(type.equals("response.text.done")||type.equals("response.audio_transcript.done"))texts[0]++;
     if(type.equals("response.audio.delta"))audio[0]+=Base64.decode(e.getString("delta"),Base64.DEFAULT).length;
     if(type.equals("session.finished"))finished.countDown();
    }catch(Exception e){failure[0]=e.getClass().getSimpleName();ready.countDown();}}
   };
   check(socket.connectBlocking(20,TimeUnit.SECONDS)&&ready.await(20,TimeUnit.SECONDS)&&updated[0],"model handshake: "+failure[0]);result.putString("model_session","passed");
   try(InputStream in=getContext().getAssets().open("smoke-input.wav")){byte[] header=new byte[44];check(in.read(header)==44,"wav header");byte[] data=new byte[3200];for(int count;(count=in.read(data))>0;){socket.send(Config.obj("type","input_audio_buffer.append","audio",Base64.encodeToString(Arrays.copyOf(data,count),Base64.NO_WRAP)).toString());Thread.sleep(100);}}
   for(int i=0;i<15;i++){socket.send(Config.obj("type","input_audio_buffer.append","audio",Base64.encodeToString(new byte[3200],Base64.NO_WRAP)).toString());Thread.sleep(100);}
   socket.send(Config.obj("type","session.finish").toString());check(finished.await(45,TimeUnit.SECONDS),"finish timeout");check(failure[0].isEmpty()&&texts[0]>0&&audio[0]>0,"translation/audio missing: "+failure[0]);result.putInt("translation_events",texts[0]);result.putInt("audio_bytes",audio[0]);result.putString("result","PASS");finish(Activity.RESULT_OK,result);
  }catch(Exception e){result.putString("result","FAIL");result.putString("error",Config.safe(e.getMessage(),key));finish(Activity.RESULT_CANCELED,result);}
  finally{if(socket!=null)socket.close();if(VoiceService.instance!=null)VoiceService.instance.stopNow();android.content.SharedPreferences.Editor edit=cfg.prefs.edit().clear();for(Map.Entry<String,?> entry:saved.entrySet()){Object value=entry.getValue();if(value instanceof String)edit.putString(entry.getKey(),(String)value);else if(value instanceof Boolean)edit.putBoolean(entry.getKey(),(Boolean)value);}edit.commit();}
 }
}
