"""Small SDK-only Android build. No secrets are read unless --private is explicit."""
import argparse,base64,hashlib,json,os,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES={
 'Java-WebSocket-1.6.0.jar':'org/java-websocket/Java-WebSocket/1.6.0/Java-WebSocket-1.6.0.jar',
 'slf4j-api-2.0.16.jar':'org/slf4j/slf4j-api/2.0.16/slf4j-api-2.0.16.jar',
 'slf4j-nop-2.0.16.jar':'org/slf4j/slf4j-nop/2.0.16/slf4j-nop-2.0.16.jar'}

def relative(path):
 try:return os.path.relpath(path,ROOT)
 except ValueError:return str(path)
def run(args,**kwargs):subprocess.run([relative(x) if isinstance(x,Path) else str(x) for x in args],check=True,cwd=ROOT,**kwargs)
def main():
 p=argparse.ArgumentParser();p.add_argument('--private',action='store_true');p.add_argument('--work',type=Path,default=ROOT/'build'/'android');p.add_argument('--output',type=Path,default=ROOT/'dist');p.add_argument('--deps',type=Path);p.add_argument('--keystore',type=Path);args=p.parse_args()
 key=os.environ.get('VOICEBRIDGE_EMBED_KEY','') if args.private else ''
 if args.private and not key:raise SystemExit('Private build requires VOICEBRIDGE_EMBED_KEY.')
 sdk=Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT',''))
 tools=sdk/'build-tools'/'36.0.0';android=sdk/'platforms'/'android-35'/'android.jar'
 if not android.exists() or not tools.exists():raise SystemExit('Install Android platform 35 and build-tools 36.0.0.')
 work=args.work.resolve();work.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
 for name in ['gen','classes','dex','deps']:(work/name).mkdir(exist_ok=True)
 jars=[]
 for name,path in DEPENDENCIES.items():
  dest=work/'deps'/name
  if args.deps and (args.deps/name).exists():shutil.copyfile(args.deps/name,dest)
  elif not dest.exists():
   url='https://repo.maven.apache.org/maven2/'+path
   try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=30) as r:dest.write_bytes(r.read())
   except OSError:
    with urllib.request.urlopen(url,timeout=60) as r:dest.write_bytes(r.read())
  jars.append(dest)
 secret=work/'gen'/'org'/'voicebridge'/'app'/'BuildSecrets.java';secret.parent.mkdir(parents=True,exist_ok=True)
 secret.write_text('package org.voicebridge.app; public final class BuildSecrets { public static final String KEY = '+json.dumps(base64.b64encode(key.encode()).decode())+'; }',encoding='utf-8')
 exe='.exe' if os.name=='nt' else '';bat='.bat' if os.name=='nt' else ''
 run([tools/('aapt2'+exe),'compile','--dir',ROOT/'android'/'res','-o',work/'resources.zip'])
 run([tools/('aapt2'+exe),'link','-o',work/'unsigned.apk','-I',android,'--manifest',ROOT/'android'/'AndroidManifest.xml','--java',work/'gen','-A',ROOT/'android'/'assets',work/'resources.zip'])
 sources=list((ROOT/'android'/'src').rglob('*.java'))+list((work/'gen').rglob('*.java'))
 arguments=['-encoding','UTF-8','-source','8','-target','8','-bootclasspath',str(android)+os.pathsep+str(tools/'core-lambda-stubs.jar'),'-classpath',os.pathsep.join(map(relative,jars)),'-d',relative(work/'classes'),*map(relative,sources)]
 argfile=work/'javac.args';argfile.write_text('\n'.join('"'+s.replace('\\','/')+'"' for s in arguments),encoding='utf-8')
 run(['javac','-J-Dfile.encoding=UTF-8','@'+relative(argfile)])
 run(['jar','cf',work/'classes.jar','-C',work/'classes','.'])
 run([tools/('d8'+bat),'--min-api','26','--lib',android,'--output',work/'dex',work/'classes.jar',*jars])
 with zipfile.ZipFile(work/'unsigned.apk','a') as z:
  for dex in (work/'dex').glob('*.dex'):z.write(dex,dex.name)
 run([tools/('zipalign'+exe),'-f','4',work/'unsigned.apk',work/'aligned.apk'])
 store=args.keystore or work/'debug-signing.jks';store.parent.mkdir(parents=True,exist_ok=True)
 if not args.keystore:os.environ['VOICEBRIDGE_STORE_PASSWORD']='android'
 if not os.environ.get('VOICEBRIDGE_STORE_PASSWORD'):raise SystemExit('Set VOICEBRIDGE_STORE_PASSWORD for the signing key.')
 if not store.exists():run(['keytool','-genkeypair','-keystore',store,'-alias','voicebridge','-storepass:env','VOICEBRIDGE_STORE_PASSWORD','-keypass:env','VOICEBRIDGE_STORE_PASSWORD','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=VoiceBridge, O=VoiceBridge, C=CN'])
 output=args.output/('VoiceBridge-Android-1.1.0-'+('private' if args.private else 'public')+'.apk')
 run([tools/('apksigner'+bat),'sign','--ks',store,'--ks-key-alias','voicebridge','--ks-pass','env:VOICEBRIDGE_STORE_PASSWORD','--key-pass','env:VOICEBRIDGE_STORE_PASSWORD','--out',output,work/'aligned.apk'])
 run([tools/('apksigner'+bat),'verify','--verbose',output])
 # Never retain the generated source containing the injected credential.
 secret.unlink()
 print(json.dumps({'artifact':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))

if __name__=='__main__':main()
