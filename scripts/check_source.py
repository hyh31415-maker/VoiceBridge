"""Fail before publishing if obvious secret/build artifacts enter the source tree."""
import base64,os,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
excluded={'.git','build','dist','.venv','__pycache__'}
key=os.environ.get('VOICEBRIDGE_SCAN_KEY','').encode()
patterns=[key,base64.b64encode(key)] if key else []
bad=[]
for path in ROOT.rglob('*'):
    if not path.is_file() or any(p in excluded for p in path.relative_to(ROOT).parts):continue
    content=path.read_bytes()
    if path.suffix in ('.apk','.dmg','.jks','.keystore','.sqlite') or path.name in ('embedded_key.py','BuildSecrets.java') or re.search(rb'sk-[A-Za-z0-9]{24,}',content) or any(p in content for p in patterns):bad.append(str(path.relative_to(ROOT)))
if bad:raise SystemExit('Do not publish these paths: '+', '.join(bad))
print('Source secret/artifact check passed.')
