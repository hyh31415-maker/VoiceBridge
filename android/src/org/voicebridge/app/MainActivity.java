package org.voicebridge.app;
import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.*;
import android.os.*;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {
 static final int BLUE=0xff3864ed,INK=0xff192b50,MUTED=0xff7b89a6,BG=0xfff4f6fa;
 Config cfg;LinearLayout shell,content;Handler handler=new Handler(Looper.getMainLooper());String page="同传",exportText="";boolean pendingTest=false;
 TextView status,notice,source,translation,level;ProgressBar meter;Button start,test,stop,pause;Spinner target,voice;Switch speak;
 final AtomicBoolean recordingCancel=new AtomicBoolean(true);boolean recording=false;byte[] recorded=null;
 final Runnable ticker=new Runnable(){public void run(){refresh();handler.postDelayed(this,400);}};
 int dp(int n){return (int)(getResources().getDisplayMetrics().density*n+.5f);}
 public void onCreate(Bundle saved){super.onCreate(saved);cfg=new Config(this);getWindow().setStatusBarColor(BG);getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);show("同传");handler.post(ticker);}
 public void onDestroy(){handler.removeCallbacks(ticker);recordingCancel.set(true);super.onDestroy();}
 public void onPause(){recordingCancel.set(true);super.onPause();}
 boolean active(){VoiceService s=VoiceService.instance;return s!=null&&!s.status.equals("已结束");}
 GradientDrawable background(int color,int radius){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));return g;}
 TextView text(String value,int size,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setPadding(0,dp(4),0,dp(4));return t;}
 Button button(String value,Runnable action,boolean primary){Button b=new Button(this);b.setAllCaps(false);b.setText(value);b.setTextSize(13);b.setTextColor(primary?Color.WHITE:BLUE);b.setBackground(background(primary?BLUE:0xffedf1fc,10));b.setMinHeight(dp(44));b.setOnClickListener(v->action.run());return b;}
 LinearLayout column(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);return l;}
 LinearLayout row(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.HORIZONTAL);l.setGravity(Gravity.CENTER_VERTICAL);return l;}
 void weighted(LinearLayout row,View child){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(46),1);p.setMargins(dp(3),dp(4),dp(3),dp(4));row.addView(child,p);}
 LinearLayout card(){LinearLayout l=column();l.setPadding(dp(16),dp(14),dp(16),dp(14));l.setBackground(background(Color.WHITE,16));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(8),0,dp(8));content.addView(l,p);return l;}
 Spinner spinner(String[] values,int selected){Spinner s=new Spinner(this);ArrayAdapter<String>a=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,values);s.setAdapter(a);s.setSelection(Math.max(0,selected));return s;}
 EditText field(String value,String hint,boolean secret){EditText e=new EditText(this);e.setText(value);e.setTextSize(14);e.setHint(hint);e.setSingleLine(true);if(secret)e.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return e;}
 void toast(String message){Toast.makeText(this,message,Toast.LENGTH_LONG).show();}
 void show(String name){
  page=name;shell=column();shell.setBackgroundColor(BG);shell.setPadding(dp(16),dp(16),dp(16),dp(12));setContentView(shell);
  if(Build.VERSION.SDK_INT>=35)shell.setOnApplyWindowInsetsListener((v,insets)->{android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());v.setPadding(dp(16)+bars.left,dp(16)+bars.top,dp(16)+bars.right,dp(12)+bars.bottom);return insets;});
  TextView title=text("声桥",27,INK);title.setTypeface(null,Typeface.BOLD);shell.addView(title);shell.addView(text("VOICE BRIDGE  ·  "+name,11,MUTED));
  LinearLayout nav=row();for(String p:new String[]{"同传","声音","术语","历史","设置"})weighted(nav,button(p,()->show(p),p.equals(name)));shell.addView(nav);
  ScrollView scroll=new ScrollView(this);content=column();scroll.addView(content);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
  if(name.equals("同传"))live();else if(name.equals("声音"))voices();else if(name.equals("术语"))terms();else if(name.equals("历史"))history();else settings();
 }
 void live(){
  LinearLayout c=card();c.addView(text("目标语言 · 输入语言自动识别",12,MUTED));target=spinner(Config.LANGS,Config.index(cfg.get("target","en")));c.addView(target);
  c.addView(text("译音声音",12,MUTED));JSONArray profiles=cfg.voices();String[] names=new String[profiles.length()];int selected=0;for(int i=0;i<names.length;i++){JSONObject v=profiles.optJSONObject(i);names[i]=v.optString("name");if(v.optString("id").equals(cfg.get("voice","Ethan")))selected=i;}voice=spinner(names,selected);c.addView(voice);
  speak=new Switch(this);speak.setText("播放译音 · 建议佩戴耳机");speak.setTextColor(INK);speak.setChecked(cfg.prefs.getBoolean("audio",true));c.addView(speak);
  c=card();c.addView(text("实时麦克风输入",13,BLUE));level=text("等待录音",23,INK);c.addView(level);meter=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);meter.setMax(60);c.addView(meter,new LinearLayout.LayoutParams(-1,dp(12)));
  c.addView(text("耳机和麦克风由 Android 自动路由，连接蓝牙或有线耳机后再开始。",11,MUTED));LinearLayout actions=row();test=button("检测",()->begin(true),false);start=button("开始同传",()->begin(false),true);stop=button("停止",()->{if(VoiceService.instance!=null)VoiceService.instance.stopNow();},false);weighted(actions,test);weighted(actions,start);weighted(actions,stop);c.addView(actions);
  pause=button("暂停输入",()->{VoiceService s=VoiceService.instance;if(s!=null)s.paused=!s.paused;},false);c.addView(pause);status=text("准备就绪",13,INK);notice=text("",12,0xffa35e37);c.addView(status);c.addView(notice);
  c=card();c.addView(text("原文",19,INK));source=text("等待讲话…",16,INK);source.setTextIsSelectable(true);c.addView(source);
  c=card();c.addView(text("译文",19,INK));translation=text("等待讲话…",16,INK);translation.setTextIsSelectable(true);c.addView(translation);c.addView(button("导出记录",()->{VoiceService s=VoiceService.instance;if(s!=null)export("原文\n"+s.text(true)+"\n\n译文\n"+s.text(false));},false));
  content.addView(text("断线自动重连 · 最多缓存 60 秒 · 约每 5 分钟续接\n已发出但未确认的末尾可能不完整；历史记录仅保存在本机。",11,MUTED));refresh();
 }
 void begin(boolean local){
  if(active())return;pendingTest=local;
  if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},10);return;}
  try{
   cfg.prefs.edit().putString("target",Config.CODES[target.getSelectedItemPosition()]).putString("voice",cfg.voices().getJSONObject(voice.getSelectedItemPosition()).getString("id")).putBoolean("audio",speak.isChecked()).apply();
   if(!local){if(cfg.key().isEmpty())throw new Exception("请先在设置中填写 API key");cfg.uri();cfg.session();}
   if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},11);
   startForegroundService(new Intent(this,VoiceService.class).putExtra("test",local));
  }catch(Exception e){toast(e.getMessage());}
 }
 public void onRequestPermissionsResult(int code,String[] permissions,int[] grants){super.onRequestPermissionsResult(code,permissions,grants);if(code==10){if(grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED)begin(pendingTest);else toast("需要允许麦克风权限才能录音");}}
 void refresh(){
  if(!page.equals("同传")||status==null)return;VoiceService s=VoiceService.instance;boolean busy=active();start.setEnabled(!busy);test.setEnabled(!busy);stop.setEnabled(busy);pause.setEnabled(busy);target.setEnabled(!busy);voice.setEnabled(!busy);speak.setEnabled(!busy);
  if(s==null)return;status.setText(s.status+"  ·  "+s.elapsed()+" 秒 / 第 "+s.segment+" 段");notice.setText(s.notice);level.setText(s.db<-99?"静音":String.format(Locale.US,"%.0f dBFS",s.db));meter.setProgress((int)Math.max(0,Math.min(60,s.db+60)));pause.setText(s.paused?"恢复输入":"暂停输入");String a=s.text(true),b=s.text(false);if(!a.isEmpty()&&!a.contentEquals(source.getText()))source.setText(a);if(!b.isEmpty()&&!b.contentEquals(translation.getText()))translation.setText(b);
 }
 void settings(){
  LinearLayout c=card();c.addView(text("模型与连接",20,INK));c.addView(text("仅支持 Qwen 实时翻译兼容协议，普通聊天模型不可直接使用。密钥只发送给下面配置的接口。",12,MUTED));
  EditText model=field(cfg.get("model",Config.MODEL),"模型名称",false);c.addView(text("模型",12,MUTED));c.addView(model);
  EditText endpoint=field(cfg.get("endpoint",Config.ENDPOINT),"wss://…",false);c.addView(text("WebSocket 接口（不带 model 参数）",12,MUTED));c.addView(endpoint);
  EditText enrollment=field(cfg.get("enrollment",Config.ENROLL),"https://…",false);c.addView(text("声音复刻接口",12,MUTED));c.addView(enrollment);
  Spinner protocol=spinner(new String[]{"qwen38","qwen35"},cfg.get("protocol","qwen38").equals("qwen35")?1:0);c.addView(text("协议版本",12,MUTED));c.addView(protocol);
  EditText key=field("","API key · 留空保持现有",true);c.addView(key);
  c.addView(button("保存设置",()->{if(active()){toast("请停止同传后更换连接设置");return;}try{URI u=new URI(endpoint.getText().toString().trim());if(!"wss".equals(u.getScheme())||u.getHost()==null||u.getQuery()!=null||u.getUserInfo()!=null)throw new Exception("需要不带查询参数的 wss:// 地址");if(!enrollment.getText().toString().startsWith("https://"))throw new Exception("声音接口需要 HTTPS");if(!key.getText().toString().trim().isEmpty())cfg.saveKey(key.getText().toString());cfg.prefs.edit().putString("model",model.getText().toString().trim()).putString("endpoint",u.toString()).putString("enrollment",enrollment.getText().toString().trim()).putString("protocol",protocol.getSelectedItem().toString()).apply();key.setText("");toast("设置已保存");}catch(Exception e){toast(e.getMessage());}},true));
  c.addView(text("用户填写的密钥通过 Android Keystore 加密保存。私有发行包内置密钥可以被提取；开源构建默认不包含密钥。",12,MUTED));
 }
 void terms(){LinearLayout c=card();c.addView(text("术语表",20,INK));c.addView(text("每行：原词 = 译法。最多 100 条，下次开始生效。",12,MUTED));EditText edit=field(cfg.get("terms","DOC = D O C\n溶解性有机碳 = dissolved organic carbon"),"原词 = 译法",false);edit.setSingleLine(false);edit.setMinLines(10);edit.setGravity(Gravity.TOP);c.addView(edit);c.addView(button("保存术语",()->{String old=cfg.get("terms","");cfg.prefs.edit().putString("terms",edit.getText().toString()).apply();try{cfg.session();toast("术语已保存");}catch(Exception e){cfg.prefs.edit().putString("terms",old).apply();toast(e.getMessage());}},true));}
 void voices(){
  content.addView(button("＋ 录制并保存声音",this::recordVoice,true));JSONArray all=cfg.voices();for(int i=0;i<all.length();i++){JSONObject v=all.optJSONObject(i);LinearLayout c=card();c.addView(text(v.optString("name"),17,INK));LinearLayout actions=row();weighted(actions,button("使用",()->{if(active()){toast("请先停止同传");return;}cfg.prefs.edit().putString("voice",v.optString("id")).apply();show("同传");},false));weighted(actions,button("命名",()->{EditText name=field(v.optString("name"),"声音名称",false);new AlertDialog.Builder(this).setTitle("声音命名").setView(name).setPositiveButton("保存",(d,w)->{try{String n=name.getText().toString().trim();if(n.isEmpty()||n.length()>40)throw new Exception("名称需要 1～40 字");cfg.renameVoice(v,n);show("声音");}catch(Exception e){toast(e.getMessage());}}).setNegativeButton("取消",null).show();},false));c.addView(actions);}
  content.addView(text("使用自己的或已获授权的声音。保存的音色与创建时的模型相关；切换模型后可能需要重新录制。",12,MUTED));
 }
 void recordVoice(){
  if(active()){toast("请先停止同传");return;}if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},12);toast("允许权限后再点新增声音");return;}
  LinearLayout panel=column();panel.setPadding(dp(20),dp(10),dp(20),dp(10));EditText name=field("","声音名称",false);panel.addView(name);panel.addView(text("请自然朗读约 15 秒：大家好，这是我的声音样本。今天我们一起讨论新的研究计划，希望通过这次交流，让不同语言之间的沟通更加顺畅。",15,INK));TextView progress=text("录音暂存内存，点击上传才发送。",12,MUTED);panel.addView(progress);recorded=null;
  AlertDialog dialog=new AlertDialog.Builder(this).setTitle("保存一个人的声音").setView(panel).setPositiveButton("上传并保存",null).setNegativeButton("关闭",null).setNeutralButton("录制 15 秒",null).create();dialog.setOnDismissListener(d->{recordingCancel.set(true);recorded=null;});dialog.show();dialog.getButton(-1).setEnabled(false);
  dialog.getButton(-3).setOnClickListener(v->{if(recording){recordingCancel.set(true);return;}recording=true;recordingCancel.set(false);recorded=null;dialog.getButton(-1).setEnabled(false);dialog.getButton(-3).setText("停止录音");new Thread(()->{AudioRecord r=null;try{int min=AudioRecord.getMinBufferSize(24000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);r=new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,24000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(min,19200));r.startRecording();ByteArrayOutputStream bytes=new ByteArrayOutputStream();byte[] buf=new byte[4800];for(int n=0;n<150&&!recordingCancel.get();n++){int count=r.read(buf,0,buf.length);if(count<=0)throw new Exception("麦克风读取失败");bytes.write(buf,0,count);final double seconds=bytes.size()/48000.0;runOnUiThread(()->progress.setText(String.format(Locale.US,"已录制 %.1f 秒",seconds)));}if(bytes.size()<240000)throw new Exception("请至少录制 5 秒");recorded=wav(bytes.toByteArray());runOnUiThread(()->{progress.setText("录制完成，可以上传保存。");dialog.getButton(-1).setEnabled(true);});}catch(Exception e){runOnUiThread(()->progress.setText(e.getMessage()));}finally{if(r!=null){try{r.stop();}catch(Exception ignored){}r.release();}recording=false;runOnUiThread(()->dialog.getButton(-3).setText("重新录制"));}},"voice-enroll-record").start();});
  dialog.getButton(-1).setOnClickListener(v->{String n=name.getText().toString().trim();if(n.isEmpty()||n.length()>40||recorded==null){toast("请先录音并填写 1～40 字名称");return;}byte[] audio=recorded;dialog.getButton(-1).setEnabled(false);dialog.getButton(-2).setEnabled(false);dialog.getButton(-3).setEnabled(false);dialog.setCancelable(false);progress.setText("正在上传并创建声音…");new Thread(()->{String apiKey="";try{apiKey=cfg.key();if(apiKey.isEmpty())throw new Exception("请先填写 API key");URL url=new URL(cfg.get("enrollment",Config.ENROLL));if(!url.getProtocol().equals("https"))throw new Exception("声音接口需要 HTTPS");HttpURLConnection c=(HttpURLConnection)url.openConnection();c.setInstanceFollowRedirects(false);c.setRequestMethod("POST");c.setConnectTimeout(15000);c.setReadTimeout(90000);c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+apiKey);c.setRequestProperty("Content-Type","application/json");JSONObject payload=Config.obj("model","qwen-voice-enrollment","input",Config.obj("action","create","target_model",cfg.get("model",Config.MODEL),"preferred_name","speaker"+UUID.randomUUID().toString().replace("-","").substring(0,8),"audio",Config.obj("data","data:audio/wav;base64,"+android.util.Base64.encodeToString(audio,android.util.Base64.NO_WRAP))));try(OutputStream out=c.getOutputStream()){out.write(payload.toString().getBytes("UTF-8"));}if(c.getResponseCode()!=200)throw new Exception("声音创建失败：HTTP "+c.getResponseCode());JSONObject response=new JSONObject(read(c.getInputStream()));String id=response.getJSONObject("output").getString("voice");cfg.addVoice(n,id);c.disconnect();runOnUiThread(()->{dialog.dismiss();show("声音");toast("声音已保存");});}catch(Exception e){final String error=Config.safe(e.getMessage(),apiKey);runOnUiThread(()->{progress.setText(error);dialog.setCancelable(true);dialog.getButton(-1).setEnabled(true);dialog.getButton(-2).setEnabled(true);dialog.getButton(-3).setEnabled(true);});}},"voice-enroll-upload").start();});
 }
 static byte[] wav(byte[] pcm)throws Exception{ByteBuffer b=ByteBuffer.allocate(44+pcm.length).order(ByteOrder.LITTLE_ENDIAN);b.put("RIFF".getBytes("US-ASCII")).putInt(36+pcm.length).put("WAVEfmt ".getBytes("US-ASCII")).putInt(16).putShort((short)1).putShort((short)1).putInt(24000).putInt(48000).putShort((short)2).putShort((short)16).put("data".getBytes("US-ASCII")).putInt(pcm.length).put(pcm);return b.array();}
 static String read(InputStream input)throws Exception{try(InputStream in=input;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];for(int n;(n=in.read(b))!=-1;)out.write(b,0,n);return out.toString("UTF-8");}}
 void history(){File dir=new File(getFilesDir(),"history");File[] files=dir.listFiles((d,n)->n.endsWith(".jsonl"));if(files==null||files.length==0){card().addView(text("暂无记录",18,MUTED));return;}Arrays.sort(files,Comparator.comparing(File::getName).reversed());for(int i=0;i<Math.min(100,files.length);i++){File file=files[i];LinearLayout c=card();c.addView(text(file.getName().replace(".jsonl",""),17,INK));c.addView(button("查看 / 导出",()->{try{String raw=read(new FileInputStream(file));StringBuilder display=new StringBuilder();for(String line:raw.split("\n")){JSONObject j=new JSONObject(line);display.append("[").append(j.optLong("seconds")).append("s] ").append(j.optString("kind").equals("source")?"原文":"译文").append("\n").append(j.optString("text")).append("\n\n");}TextView preview=text(display.toString(),15,INK);preview.setTextIsSelectable(true);ScrollView scroll=new ScrollView(this);scroll.setPadding(dp(16),dp(8),dp(16),dp(8));scroll.addView(preview);new AlertDialog.Builder(this).setTitle("历史记录").setView(scroll).setPositiveButton("导出",(d,w)->export(display.toString())).setNegativeButton("关闭",null).show();}catch(Exception e){toast(e.getMessage());}},false));}}
 void export(String text){exportText=text;Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("text/plain").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,"声桥同传记录.txt");startActivityForResult(intent,20);}
 protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==20&&result==RESULT_OK&&data!=null)try(OutputStream out=getContentResolver().openOutputStream(data.getData())){out.write(exportText.getBytes("UTF-8"));toast("已导出");}catch(Exception e){toast("导出失败");}}
}
