package org.voicebridge.app;
import android.app.*;
import android.content.*;
import android.media.*;
import android.os.*;
import android.util.Base64;
import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;
import org.json.*;
import javax.net.ssl.SSLParameters;
import java.util.*;
import java.util.concurrent.*;
import java.io.*;

public class VoiceService extends Service {
 public static volatile VoiceService instance;
 public volatile String status="准备就绪",notice="";public volatile double db=-100,sent=0;public volatile int segment=0;public volatile boolean stopping=false,paused=false;
 private volatile boolean terminate=false;private boolean test=false;private long started,voiceAt;
 private final LinkedBlockingDeque<byte[]> input=new LinkedBlockingDeque<>(600),output=new LinkedBlockingDeque<>(300);
 private final LinkedHashMap<String,String> source=new LinkedHashMap<>(),translation=new LinkedHashMap<>();
 private Config cfg;private String key="";private JSONObject session;private Thread worker,recordThread,playThread;private AudioRecord recorder;private AudioTrack player;private Conn connection;private PowerManager.WakeLock wake;private File historyFile;private AudioManager manager;private AudioFocusRequest focus;
 public IBinder onBind(Intent i){return null;}
 public int onStartCommand(Intent intent,int flags,int id){
  if(intent!=null&&"stop".equals(intent.getAction())){stopping=true;return START_NOT_STICKY;}
  if(worker!=null)return START_NOT_STICKY;
  instance=this;cfg=new Config(this);test=intent!=null&&intent.getBooleanExtra("test",false);started=SystemClock.elapsedRealtime();voiceAt=started;
  NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);nm.createNotificationChannel(new NotificationChannel("live","实时同传",NotificationManager.IMPORTANCE_LOW));
  PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
  PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,VoiceService.class).setAction("stop"),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
  startForeground(1,new Notification.Builder(this,"live").setSmallIcon(R.drawable.ic_wave).setContentTitle("声桥 · 麦克风使用中").setContentText("点击返回，或停止录音").setContentIntent(open).setOngoing(true).addAction(new Notification.Action.Builder(null,"停止",stop).build()).build());
  worker=new Thread(this::run,"voicebridge-session");worker.start();return START_NOT_STICKY;
 }
 public long elapsed(){return (SystemClock.elapsedRealtime()-started)/1000;}
 public synchronized String text(boolean original){return String.join("\n\n",(original?source:translation).values());}
 private synchronized void text(String kind,String id,String value,boolean append,boolean complete){
  LinkedHashMap<String,String> rows=kind.equals("source")?source:translation;String old=rows.get(id);rows.put(id,append?(old==null?"":old)+value:value);
  while(rows.size()>200)rows.remove(rows.keySet().iterator().next());
  if(complete&&historyFile!=null)try(FileOutputStream f=new FileOutputStream(historyFile,true)){f.write((Config.obj("kind",kind,"seconds",elapsed(),"text",value).toString()+"\n").getBytes("UTF-8"));}catch(Exception e){notice="历史记录写入失败";}
 }
 public void stopNow(){if(stopping){terminate=true;if(connection!=null)connection.close();}stopping=true;}
 private void run(){
  try{
   if(!test){key=cfg.key();if(key.isEmpty())throw new Exception("请在设置中填写 API key");cfg.uri();session=cfg.session();File folder=new File(getFilesDir(),"history");folder.mkdirs();historyFile=new File(folder,new java.text.SimpleDateFormat("yyyyMMdd-HHmmss",Locale.US).format(new Date())+".jsonl");}
   wake=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"voicebridge:record");wake.acquire(6*60*60*1000L);
   int buffer=AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
   recorder=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(buffer,12800));
   if(recorder.getState()!=AudioRecord.STATE_INITIALIZED)throw new Exception("无法打开麦克风");recorder.startRecording();
   recordThread=new Thread(this::record,"voicebridge-input");recordThread.start();
   if(!test&&cfg.audio()){
    manager=(AudioManager)getSystemService(AUDIO_SERVICE);focus=new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT).setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).setOnAudioFocusChangeListener(change->{if(change<0){paused=true;notice="被其他音频打断，点击恢复后继续";}}).build();manager.requestAudioFocus(focus);
    player=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()).setAudioFormat(new AudioFormat.Builder().setSampleRate(24000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build()).setBufferSizeInBytes(Math.max(24000,AudioTrack.getMinBufferSize(24000,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT))).setTransferMode(AudioTrack.MODE_STREAM).build();player.play();
    playThread=new Thread(this::play,"voicebridge-output");playThread.start();
   }
   if(test){status="麦克风检测 · 不上传音频";while(!stopping&&!terminate)Thread.sleep(100);return;}
   int attempts=0;long failureStart=0;int[] delays={1,2,4,8,15};
   while(!terminate){
    if(stopping&&input.isEmpty())break;
    Conn c=null;long connectedAt=0;
    try{
     status=attempts==0?"正在连接…":"正在重连…";segment++;c=new Conn(segment);connection=c;
     if(!c.connectBlocking(12,TimeUnit.SECONDS)||!c.ready.await(15,TimeUnit.SECONDS)||!c.configured)throw new IOException(c.error.isEmpty()?"连接超时":c.error);
     status="正在同传 · 输入语言自动识别";connectedAt=SystemClock.elapsedRealtime();long stoppedAt=0;
     while(!terminate){
      long now=SystemClock.elapsedRealtime();if(!c.error.isEmpty()||!c.isOpen())throw new IOException(c.error.isEmpty()?"连接已断开":c.error);
      if(stopping&&stoppedAt==0)stoppedAt=now;
      boolean rotate=!stopping&&(now-connectedAt>300000||c.tokens>30000)&&(now-voiceAt>800||now-connectedAt>330000);
      if(rotate||(stopping&&(input.isEmpty()||now-stoppedAt>20000))){
       status=rotate?"正在续接新会话…":"接收最后一段翻译…";c.send(Config.obj("type","session.finish").toString());
       if(!c.finished.await(12,TimeUnit.SECONDS))notice="结束确认超时，末尾可能不完整";c.close();break;
      }
      if(now-c.lastEvent>45000&&now-voiceAt<5000)throw new IOException("服务长时间没有返回事件");
      if(c.hasBufferedData()){if(now-c.lastSend>10000)throw new IOException("网络发送积压");Thread.sleep(20);continue;}
      byte[] data=input.pollFirst(50,TimeUnit.MILLISECONDS);if(data!=null){try{c.send(Config.obj("type","input_audio_buffer.append","audio",Base64.encodeToString(data,Base64.NO_WRAP)).toString());}catch(Exception e){input.offerFirst(data);throw e;}sent+=data.length/32000.0;c.lastSend=now;Thread.sleep(Math.max(1,data.length/64));}
     }
     attempts=0;failureStart=0;if(stopping||terminate)break;
    }catch(Exception e){
     if(terminate||stopping)break;
     String error=Config.safe(e.getMessage(),key);if((c!=null&&c.fatal)||error.contains("401")||error.contains("403"))throw new Exception("密钥、权限或参数错误："+error);
     if(failureStart==0)failureStart=SystemClock.elapsedRealtime();if(connectedAt>0&&SystemClock.elapsedRealtime()-connectedAt>10000){attempts=0;failureStart=SystemClock.elapsedRealtime();}
     if(++attempts>20||SystemClock.elapsedRealtime()-failureStart>300000)throw new Exception("重连未成功，请检查网络后重新开始");
     notice="连接中断，已发出但未确认的末尾可能不完整";int delay=delays[Math.min(attempts-1,4)];status=delay+" 秒后重连 · 最多缓存 60 秒";
     for(int i=0;i<delay*10&&!stopping&&!terminate;i++)Thread.sleep(100);
    }finally{if(c!=null)c.close();}
   }
   long end=SystemClock.elapsedRealtime()+20000;while(!output.isEmpty()&&!terminate&&SystemClock.elapsedRealtime()<end)Thread.sleep(50);
  }catch(Exception e){notice=Config.safe(e.getMessage(),key);status="已停止";}
  finally{
   terminate=true;stopping=true;if(connection!=null)connection.close();
   if(recorder!=null){try{recorder.stop();}catch(Exception ignored){}try{if(recordThread!=null)recordThread.join(1000);}catch(Exception ignored){}recorder.release();}
   if(player!=null){try{if(playThread!=null)playThread.join(1000);}catch(Exception ignored){}try{player.stop();}catch(Exception ignored){}player.release();}
   if(manager!=null&&focus!=null)manager.abandonAudioFocusRequest(focus);if(wake!=null&&wake.isHeld())wake.release();
   status="已结束";stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
  }
 }
 private void record(){try{byte[] buffer=new byte[3200];while(!terminate&&!stopping){int n=recorder.read(buffer,0,buffer.length);if(n<=0)throw new IOException("麦克风停止采集");double energy=0;for(int i=0;i+1<n;i+=2){short sample=(short)((buffer[i]&255)|(buffer[i+1]<<8));energy+=(double)sample*sample;}db=20*Math.log10(Math.max(1e-6,Math.sqrt(energy/(n/2))/32768));if(db>-48&&!paused)voiceAt=SystemClock.elapsedRealtime();if(!test){byte[] chunk=paused?new byte[n]:Arrays.copyOf(buffer,n);if(!input.offerLast(chunk)){input.pollFirst();input.offerLast(chunk);notice="断线缓存已满，正在舍弃最早录音";}}}}catch(Exception e){notice=Config.safe(e.getMessage(),key);terminate=true;}}
 private void play(){try{while(!terminate){byte[] data=output.pollFirst(200,TimeUnit.MILLISECONDS);if(data!=null){int offset=0;while(offset<data.length&&!terminate){int n=player.write(data,offset,data.length-offset);if(n<0)throw new IOException("音频播放中断");offset+=n;}}}}catch(Exception e){notice="译音播放失败，请检查耳机或输出设备";}}
 public void onDestroy(){terminate=true;stopping=true;if(connection!=null)connection.close();super.onDestroy();}
 private class Conn extends WebSocketClient {
  final CountDownLatch ready=new CountDownLatch(1),finished=new CountDownLatch(1);volatile boolean configured=false,fatal=false;volatile String error="";volatile long tokens=0,lastEvent=SystemClock.elapsedRealtime(),lastSend=lastEvent;final int generation;final Map<String,String> legacy=new HashMap<>();
  Conn(int n)throws Exception{super(cfg.uri(),Collections.singletonMap("Authorization","Bearer "+key));generation=n;setConnectionLostTimeout(15);}
  protected void onSetSSLParameters(SSLParameters parameters){parameters.setEndpointIdentificationAlgorithm("HTTPS");}
  public void onOpen(ServerHandshake handshake){}
  public void onClose(int code,String reason,boolean remote){if(!stopping&&finished.getCount()>0)error=reason.isEmpty()?"连接中断":reason;ready.countDown();}
  public void onError(Exception e){error=Config.safe(e.getMessage(),key);ready.countDown();}
  public void onMessage(String message){try{
   JSONObject e=new JSONObject(message);String type=e.optString("type");lastEvent=SystemClock.elapsedRealtime();
   if(type.equals("session.created")){send(Config.obj("type","session.update","session",session).toString());return;}
   if(type.equals("session.updated")){configured=true;ready.countDown();return;}
   if(type.equals("error")){JSONObject err=e.optJSONObject("error");error=err==null?"模型错误":err.optString("message");String code=err==null?"":err.optString("code");fatal=(code.contains("auth")||code.contains("api_key")||code.contains("invalid")||code.contains("quota"))&&!error.toLowerCase(Locale.ROOT).contains("context");ready.countDown();finished.countDown();return;}
   if(type.equals("session.finished")){finished.countDown();return;}
   String id=generation+":"+e.optString("item_id",e.optString("response_id","current"));
   if(type.equals("conversation.item.input_audio_transcription.delta"))text("source",id,e.optString("delta"),true,false);
   else if(type.equals("conversation.item.input_audio_transcription.completed"))text("source",id,e.optString("transcript"),false,true);
   else if(type.equals("response.audio_transcript.delta")||type.equals("response.text.delta"))text("translation",id,e.optString("delta"),true,false);
   else if(type.equals("response.audio_transcript.done")||type.equals("response.text.done"))text("translation",id,e.optString("transcript",e.optString("text")),false,true);
   else if(type.endsWith(".text")){String confirmed=legacy.getOrDefault(id,"")+e.optString("text");legacy.put(id,confirmed);text(type.startsWith("conversation")?"source":"translation",id,confirmed+e.optString("stash"),false,false);}
   else if(type.equals("response.audio.delta")&&player!=null){byte[] data=Base64.decode(e.getString("delta"),Base64.DEFAULT);for(int p=0;p<data.length;p+=4800){byte[] chunk=Arrays.copyOfRange(data,p,Math.min(p+4800,data.length));if(!output.offerLast(chunk)){output.pollFirst();output.offerLast(chunk);notice="译音积压，已跳过过旧语音";}}}
   else if(type.equals("response.done")){JSONObject response=e.optJSONObject("response");if(response!=null){JSONObject usage=response.optJSONObject("usage");if(usage!=null)tokens+=usage.optLong("total_tokens");if(response.optString("status").equals("failed"))error="模型响应失败";}}
  }catch(Exception ex){error=Config.safe(ex.getMessage(),key);ready.countDown();}}
 }
}
