import argparse,base64,json,os,platform,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def run(args):subprocess.run([str(a) for a in args],check=True)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--private',action='store_true');args=parser.parse_args()
 if sys.platform not in ('darwin','win32'):raise SystemExit('Build on the target operating system: macOS or Windows.')
 key=os.environ.get('VOICEBRIDGE_EMBED_KEY','') if args.private else ''
 if args.private and not key:raise SystemExit('Private build requires VOICEBRIDGE_EMBED_KEY.')
 build=ROOT/'build'/'desktop';build.mkdir(parents=True,exist_ok=True);out=ROOT/'dist';out.mkdir(exist_ok=True)
 stage=build/'private';stage.mkdir(exist_ok=True)
 entry=build/'launcher.py';entry.write_text('import sys\nif "--self-test" in sys.argv:\n from voicebridge.selfcheck import main\n main(sys.argv[-1])\nelse:\n from voicebridge.ui import main\n main()\n',encoding='utf-8')
 extra=[]
 if args.private:
  secret=stage/'embedded_key.py';secret.write_text('import base64\ndef get_key(): return base64.b64decode('+repr(base64.b64encode(key.encode()).decode())+').decode()\n',encoding='utf-8')
  extra=['--paths',str(stage),'--hidden-import','embedded_key']
 try:
  icon=ROOT/'desktop'/'voicebridge'/'assets'/'app.ico'
  command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name','VoiceBridge','--distpath',out,'--workpath',build/'work','--specpath',build,'--paths',ROOT/'desktop','--exclude-module','numpy','--exclude-module','scipy','--icon',icon,'--add-data',str(icon)+os.pathsep+'voicebridge/assets',*extra]
  if sys.platform=='darwin':command+=['--osx-bundle-identifier','org.voicebridge.desktop']
  command+=[entry];run(command)
  if sys.platform=='darwin':
   import plistlib
   app=out/'VoiceBridge.app';plist=app/'Contents'/'Info.plist';info=plistlib.loads(plist.read_bytes());info.update(NSMicrophoneUsageDescription='声桥需要使用麦克风进行实时语音翻译和录制声音样本。',NSHighResolutionCapable=True,CFBundleShortVersionString='1.1.0');plist.write_bytes(plistlib.dumps(info))
   # Ad-hoc signature only. Distribution notarization requires the owner's Apple credentials.
   run(['codesign','--force','--deep','--sign','-',app]);run(['codesign','--verify','--deep','--strict',app])
   os.environ['VOICEBRIDGE_DATA_DIR']=str(build/'test-profile')
   run([app/'Contents'/'MacOS'/'VoiceBridge','--self-test',out/'selfcheck.json'])
   dmgroot=build/'dmg';dmgroot.mkdir(exist_ok=True)
   destination=dmgroot/'VoiceBridge.app'
   if destination.exists():shutil.rmtree(destination)
   shutil.copytree(app,destination,symlinks=True)
   link=dmgroot/'Applications'
   if not link.exists():link.symlink_to('/Applications',target_is_directory=True)
   dmg=out/('VoiceBridge-macOS-'+platform.machine()+'-'+('private' if args.private else 'public')+'.dmg')
   run(['hdiutil','create','-ov','-format','UDZO','-volname','VoiceBridge','-srcfolder',dmgroot,dmg]);print(dmg)
 finally:
  candidate=stage/'embedded_key.py'
  if candidate.exists():candidate.unlink()

if __name__=='__main__':main()
