"""Public Windows ZIP and optional Inno Setup installer; never embeds a key."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iscc', type=Path, help='Path to the Inno Setup compiler')
    parser.add_argument('--skip-build', action='store_true', help='Package an already verified public dist/VoiceBridge')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('Run on Windows.')
    env = dict(os.environ)
    for name in ('VOICEBRIDGE_EMBED_KEY', 'VOICEBRIDGE_API_KEY', 'PYTHONPATH'):
        env.pop(name, None)
    if not args.skip_build:
        subprocess.run([sys.executable, str(ROOT/'scripts/build_desktop.py')], env=env, check=True)
    folder = ROOT/'dist/VoiceBridge'
    report = ROOT/'build/desktop/public-selfcheck.json'
    with tempfile.TemporaryDirectory(prefix='voicebridge-public-check-') as profile:
        env['VOICEBRIDGE_DATA_DIR'] = profile
        subprocess.run([str(folder/'VoiceBridge.exe'), '--self-test', str(report)], env=env, check=True, timeout=60)
    checked = json.loads(report.read_text(encoding='utf-8'))
    if not checked.get('gui_created') or checked.get('key_present'):
        raise RuntimeError('Public build must start without a bundled credential.')
    for name in ('README.md', 'LICENSE'):
        shutil.copyfile(ROOT/name, folder/name)
    notices = []
    for name in ['aiohttp','sounddevice','audioop-lts','cffi','aiohappyeyeballs','aiosignal','attrs','frozenlist','idna','multidict','propcache','yarl','pycparser','pyinstaller']:
        dist = importlib.metadata.distribution(name)
        notices.append('\n===== '+name+' '+dist.version+' =====\n')
        for path in dist.files or []:
            if '.dist-info/' in str(path) and any(word in path.name.lower() for word in ('license','copying','notice')):
                notices.append(dist.locate_file(path).read_text(encoding='utf-8', errors='replace'))
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():
        notices.append('\n===== Python =====\n'+python_license.read_text(encoding='utf-8', errors='replace'))
    (folder/'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices), encoding='utf-8')
    archive = ROOT/'dist/VoiceBridge-Windows-x64-Portable-1.1.0.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in folder.rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(ROOT/'dist'))
    if args.iscc:
        subprocess.run([str(args.iscc), '/DSourceRoot='+str(folder), '/DOutputRoot='+str(ROOT/'dist'), str(ROOT/'scripts/windows.iss')], check=True)
    print(archive)

if __name__ == '__main__':
    main()
