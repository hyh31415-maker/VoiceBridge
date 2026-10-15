package org.voicebridge.app;
import android.content.*;
import android.security.keystore.*;
import android.util.Base64;
import org.json.*;
import java.net.*;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.util.*;

public final class Config {
 public static final String MODEL="qwen3.8-livetranslate-flash-realtime";
 public static final String ENDPOINT="wss://maas.qianwenaiapi.com/api-ws/v1/realtime";
 public static final String ENROLL="https://maas.qianwenaiapi.com/api/v1/services/audio/tts/customization";
 public static final String[] CODES={"en","zh","ja","ko","fr","de","es","pt","ru","ar","it","hi","id","vi","th","tr","nl","pl","sv","uk"};
 public static final String[] LANGS={"英语","中文","日语","韩语","法语","德语","西班牙语","葡萄牙语","俄语","阿拉伯语","意大利语（文字）","印地语（文字）","印度尼西亚语（文字）","越南语（文字）","泰语（文字）","土耳其语（文字）","荷兰语（文字）","波兰语（文字）","瑞典语（文字）","乌克兰语（文字）"};
 public final SharedPreferences prefs;
 public Config(Context context){prefs=context.getSharedPreferences("voicebridge",Context.MODE_PRIVATE);}
 public static JSONObject obj(Object... fields){JSONObject j=new JSONObject();try{for(int i=0;i<fields.length;i+=2)j.put((String)fields[i],fields[i+1]);}catch(JSONException e){throw new IllegalArgumentException(e);}return j;}
 public String get(String key,String fallback){return prefs.getString(key,fallback);}
 public boolean audio(){return prefs.getBoolean("audio",true)&&index(get("target","en"))<10;}
 public static int index(String code){for(int i=0;i<CODES.length;i++)if(CODES[i].equals(code))return i;return 0;}
 private SecretKey secret() throws Exception {
  KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);
  if(!ks.containsAlias("VoiceBridgeApiKey")){KeyGenerator gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");gen.init(new KeyGenParameterSpec.Builder("VoiceBridgeApiKey",KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());gen.generateKey();}
  return (SecretKey)ks.getKey("VoiceBridgeApiKey",null);
 }
 public void saveKey(String value) throws Exception {
  Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,secret());byte[] encrypted=c.doFinal(value.trim().getBytes("UTF-8"));
  prefs.edit().putString("key_data",Base64.encodeToString(encrypted,Base64.NO_WRAP)).putString("key_iv",Base64.encodeToString(c.getIV(),Base64.NO_WRAP)).apply();
 }
 public String key() throws Exception {
  String data=get("key_data","");if(data.isEmpty())return new String(Base64.decode(BuildSecrets.KEY,Base64.DEFAULT),"UTF-8");
  Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,secret(),new GCMParameterSpec(128,Base64.decode(get("key_iv",""),Base64.DEFAULT)));return new String(c.doFinal(Base64.decode(data,Base64.DEFAULT)),"UTF-8");
 }
 public URI uri() throws Exception {
  URI input=new URI(get("endpoint",ENDPOINT));if(!"wss".equals(input.getScheme())||input.getHost()==null||input.getUserInfo()!=null||input.getQuery()!=null)throw new Exception("请填写不带查询参数的 wss:// 接口地址");
  String model=get("model",MODEL).trim();if(model.isEmpty())throw new Exception("请填写模型名称");
  return new URI(input.toString()+"?model="+URLEncoder.encode(model,"UTF-8"));
 }
 public JSONArray voices(){
  JSONArray list=new JSONArray();String[] ids={"Ethan","Tina","Serena","Cindy","once","always"};String[] names={"Ethan · 阳光男声","Tina · 温暖女声","Serena · 温柔女声","Cindy · 甜美女声","我的声音 · 实时复刻","跟随发言人 · 多人复刻"};
  for(int i=0;i<ids.length;i++)list.put(obj("id",ids[i],"name",get("name_"+ids[i],names[i]),"voice",i<4?ids[i]:"default","mode",i<4?"":ids[i]));
  try{JSONArray custom=new JSONArray(get("voices","[]"));for(int i=0;i<custom.length();i++)list.put(custom.getJSONObject(i));}catch(Exception ignored){}
  return list;
 }
 public JSONObject voice(){JSONArray all=voices();for(int i=0;i<all.length();i++){JSONObject v=all.optJSONObject(i);if(v.optString("id").equals(get("voice","Ethan")))return v;}return all.optJSONObject(0);}
 public void addVoice(String name,String voice)throws Exception{JSONArray a=new JSONArray(get("voices","[]"));a.put(obj("id",UUID.randomUUID().toString(),"name",name,"voice",voice,"mode","never"));prefs.edit().putString("voices",a.toString()).apply();}
 public void renameVoice(JSONObject v,String name)throws Exception{if(!v.optString("mode").equals("never")){prefs.edit().putString("name_"+v.getString("id"),name).apply();return;}JSONArray a=new JSONArray(get("voices","[]"));for(int i=0;i<a.length();i++)if(a.getJSONObject(i).getString("id").equals(v.getString("id")))a.getJSONObject(i).put("name",name);prefs.edit().putString("voices",a.toString()).apply();}
 public JSONObject session() throws Exception {
  JSONObject v=voice();String mode=v.optString("mode");JSONObject translation=obj("language",get("target","en"));JSONObject phrases=new JSONObject();
  String terms=get("terms","DOC = D O C\n溶解性有机碳 = dissolved organic carbon");int count=0;
  for(String line:terms.split("\n")){if(line.trim().isEmpty())continue;String[] pair=line.split("=",2);if(pair.length!=2||pair[0].trim().isEmpty()||pair[1].trim().isEmpty())throw new Exception("术语格式应为：原词 = 译法");if(++count>100)throw new Exception("最多 100 条术语");phrases.put(pair[0].trim(),pair[1].trim());}
  translation.put("corpus",obj("phrases",phrases));JSONArray modalities=new JSONArray();modalities.put("text");if(audio())modalities.put("audio");
  JSONObject cfg=obj("voice",v.optString("voice"),"enable_voice_clone",!mode.isEmpty(),"translation",translation);
  if(!mode.isEmpty())cfg.put("voice_clone_options",obj("frequency",mode));
  if(get("protocol","qwen38").equals("qwen35")){cfg.put("modalities",modalities);cfg.put("sample_rate",16000);cfg.put("input_audio_format","pcm");cfg.put("output_audio_format","pcm");cfg.put("input_audio_transcription",obj("model","qwen3-asr-flash-realtime"));cfg.put("turn_detection",obj("type","server_vad","threshold",.2,"silence_duration_ms",800));}
  else{cfg.put("output_modalities",modalities);cfg.put("audio",obj("output",obj("voice",v.optString("voice"))));}
  return cfg;
 }
 public static String safe(String text,String key){if(text==null)return "连接错误";if(key!=null&&!key.isEmpty())text=text.replace(key,"[redacted]");return text.replaceAll("sk-[A-Za-z0-9_-]+","[redacted]");}
}
