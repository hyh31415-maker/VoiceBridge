import asyncio,json,sys
from pathlib import Path
import aiohttp
from .storage import load_key,settings
from .service import endpoint_url,session_config,safe_error

def main(report_path):
    import tkinter as tk
    from .ui import App
    result={'platform':sys.platform}
    root=tk.Tk();app=App(root);root.update()
    result['gui_created']=root.winfo_width()>500
    for page in ('声音库','术语表','历史记录','设置','实时同传'):app.show(page);root.update()
    app.close()
    async def verify():
        try:key=load_key()
        except RuntimeError:key=''
        result['key_present']=bool(key)
        if not key:return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as client:
                async with client.ws_connect(endpoint_url(settings()),headers={'Authorization':'Bearer '+key}) as ws:
                    result['session_created']=(await ws.receive_json())['type']=='session.created'
                    await ws.send_json({'type':'session.update','session':session_config(settings(),{'voice':'Ethan','mode':None})})
                    result['session_updated']=(await ws.receive_json())['type']=='session.updated'
        except Exception as error:result['error']=safe_error(error,key)
    asyncio.run(verify());Path(report_path).write_text(json.dumps(result,indent=2),encoding='utf-8')
    if not result['gui_created'] or result.get('key_present') and not result.get('session_updated'):raise SystemExit(1)
