from .platform_support import FONT,com_start,com_end,open_folder
import ctypes
from collections import deque
import json
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
import sounddevice as sd
from . import VERSION
from .widgets import BG,WHITE,INK,MUTED,BLUE,GREEN,LINE,Button,Card,Toggle,label,theme,px
from .storage import DATA,History,VoiceLibrary,settings,write_json,timestamp,export_text,export_srt,set_key
from . import languages
from .service import endpoint_url
from .engine import AudioSession
from .audio import resample_pcm
from .voice_dialog import VoiceDialog

class App:
    def __init__(self,root):
        self.root=root;self.config=settings();self.library=VoiceLibrary();self.history=History()
        self.events=queue.Queue();self.session=None;self.voice_dialog=None;self.session_id=None
        self.lines={};self.started=0;self.last_commit=0;self.dirty=False;self.captured=0;self.sent=0
        self.wave=deque([-60]*66,maxlen=66);self.page='实时同传';self.closing=False;self.active_view='live'
        theme(root);root.title('声桥 · Voice Bridge')
        root.geometry(f'{min(px(1280),root.winfo_screenwidth()-60)}x{min(px(850),root.winfo_screenheight()-100)}')
        root.minsize(min(px(1080),root.winfo_screenwidth()-60),min(px(720),root.winfo_screenheight()-100))
        try:root.iconbitmap(str(Path(__file__).parent/'assets'/'app.ico'))
        except tk.TclError:pass
        self._variables();self._layout();self.refresh_devices();self.refresh_voices();self.show('实时同传');self.render_lines()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Control-Return>',lambda e:self.stop() if self.session else self.start())
        root.bind('<Control-s>',lambda e:self.export())
        root.after(80,self.poll)

    def _variables(self):
        self.target=tk.StringVar(value=languages.name(self.config['target']))
        self.voice=tk.StringVar();self.input=tk.StringVar();self.output=tk.StringVar()
        self.speak=tk.BooleanVar(value=self.config['speak']);self.doc=tk.BooleanVar(value=self.config['doc'])
        self.status=tk.StringVar(value='先检测麦克风，确认输入正常后开始同传。')
        self.state=tk.StringVar(value='准备就绪');self.clock=tk.StringVar(value='00:00:00');self.segment=tk.StringVar(value='第 0 段')
        self.counter=tk.StringVar(value='本机直连 · 自动重连已开启');self.db=tk.StringVar(value='— dBFS')
        self.error=tk.StringVar();self.auto=tk.BooleanVar(value=self.config['autosave']);self.reconnect=tk.BooleanVar(value=self.config['reconnect'])
        self.volume=tk.IntVar(value=self.config['volume']);self.rotate=tk.StringVar(value=str(int(self.config['rotate_seconds'])//60))
        self.fontsize=tk.StringVar(value=str(self.config['font_size']))

    def _layout(self):
        self.sidebar=tk.Frame(self.root,bg='#F0F3F9',width=px(185));self.sidebar.pack(side='left',fill='y');self.sidebar.pack_propagate(False)
        logo=tk.Canvas(self.sidebar,width=46,height=46,bg='#F0F3F9',highlightthickness=0)
        logo.place(x=px(20),y=px(25))
        for i,h in enumerate([13,27,37,25,12]):logo.create_line(6+i*8,23-h/2,6+i*8,23+h/2,fill=BLUE,width=4,capstyle='round')
        label(self.sidebar,'声桥',18,bold=True).place(x=px(62),y=px(18))
        label(self.sidebar,'VOICE BRIDGE',8,color=MUTED).place(x=px(62),y=px(48))
        self.nav={}
        for i,(name,prefix) in enumerate([('实时同传','◉'),('声音库','≋'),('术语表','▤'),('历史记录','◷')]):
            b=Button(self.sidebar,prefix+'   '+name,lambda n=name:self.show(n),width=157,height=48)
            b.place(x=px(14),y=px(100+i*62));self.nav[name]=b
        b=Button(self.sidebar,'⚙   设置',lambda:self.show('设置'),width=157,height=44);b.pack(side='bottom',pady=(0,18));self.nav['设置']=b
        label(self.sidebar,'版本 '+VERSION,9,color=MUTED).pack(side='bottom',anchor='w',padx=28,pady=12)
        self.main=tk.Frame(self.root,bg=BG);self.main.pack(side='left',fill='both',expand=True,padx=px(24),pady=px(22))
        header=tk.Frame(self.main,bg=BG);header.pack(fill='x',pady=(0,18))
        self.heading=label(header,'实时同传',23,bold=True);self.heading.pack(anchor='w')
        self.subtitle=label(header,'保留声音，让交流跨越语言',11,color=MUTED);self.subtitle.pack(anchor='w',pady=(3,0))
        self.badge=label(header,'● 准备就绪',10,color=MUTED);self.badge.place(relx=1,x=-8,y=8,anchor='ne')
        self.container=tk.Frame(self.main,bg=BG);self.container.pack(fill='both',expand=True)
        self.pages={name:tk.Frame(self.container,bg=BG) for name in self.nav}
        self._live(self.pages['实时同传']);self._voices(self.pages['声音库']);self._terms(self.pages['术语表']);self._history(self.pages['历史记录']);self._settings(self.pages['设置'])

    def _live(self,parent):
        parent.grid_columnconfigure(0,weight=1);parent.grid_rowconfigure(4,weight=1)
        card=Card(parent,height=94);card.grid(row=0,column=0,sticky='ew',pady=(0,12));f=card.body
        f.columnconfigure(0,weight=3);f.columnconfigure(1,weight=4);f.columnconfigure(2,weight=2)
        label(f,'目标语言 · 输入自动识别',9,color=MUTED).grid(row=0,column=0,sticky='w')
        self.target_box=ttk.Combobox(f,textvariable=self.target,values=[n for c,n,a in languages.LANGUAGES],state='readonly',width=23)
        self.target_box.grid(row=1,column=0,sticky='ew',padx=(0,26),pady=(6,0))
        label(f,'发言人 / 译音音色',9,color=MUTED).grid(row=0,column=1,sticky='w')
        self.voice_box=ttk.Combobox(f,textvariable=self.voice,state='readonly',width=30);self.voice_box.grid(row=1,column=1,sticky='ew',padx=(0,26),pady=(6,0))
        playback=tk.Frame(f,bg=WHITE);playback.grid(row=1,column=2,sticky='e')
        label(playback,'语音播放',10,color=MUTED).pack(side='left',padx=9);self.speak_toggle=Toggle(playback,self.speak);self.speak_toggle.pack(side='left')
        card=Card(parent,height=198);card.grid(row=1,column=0,sticky='ew',pady=(0,12));f=card.body
        top=tk.Frame(f,bg=WHITE);top.pack(fill='x');label(top,'♩  实时输入',11,color=BLUE).pack(side='left')
        label(top,textvariable=self.db,color=MUTED,size=10).pack(side='right')
        self.wave_canvas=tk.Canvas(f,height=px(52),bg=WHITE,highlightthickness=0);self.wave_canvas.pack(fill='x',pady=(px(2),px(8)));self.wave_canvas.bind('<Configure>',lambda e:self.draw_wave())
        devices=tk.Frame(f,bg=WHITE);devices.pack(fill='x');devices.columnconfigure(0,weight=1);devices.columnconfigure(1,weight=1)
        label(devices,'输入设备',9,color=MUTED).grid(row=0,column=0,sticky='w');label(devices,'输出设备',9,color=MUTED).grid(row=0,column=1,sticky='w')
        self.input_box=ttk.Combobox(devices,textvariable=self.input,state='readonly',width=28);self.input_box.grid(row=1,column=0,sticky='ew',padx=(0,12),pady=(4,0))
        self.output_box=ttk.Combobox(devices,textvariable=self.output,state='readonly',width=27);self.output_box.grid(row=1,column=1,sticky='ew',padx=(0,16),pady=(4,0))
        actions=tk.Frame(devices,bg=WHITE);actions.grid(row=0,column=2,rowspan=2,sticky='se')
        self.test_button=Button(actions,'检测麦克风',lambda:self.start(True),width=105);self.test_button.pack(side='left',padx=(0,8))
        self.start_button=Button(actions,'开始同传',self.start,primary=True,width=112);self.start_button.pack(side='left',padx=(0,8))
        self.stop_button=Button(actions,'停止',self.stop,width=68);self.stop_button.pack(side='left');self.stop_button.set(enabled=False)
        statusbar=Card(parent,height=53,padding=13);statusbar.grid(row=2,column=0,sticky='ew',pady=(0,8));f=statusbar.body
        label(f,textvariable=self.state,size=10,color=GREEN).pack(side='left');label(f,textvariable=self.counter,size=9,color=MUTED).pack(side='left',padx=14)
        label(f,textvariable=self.segment,size=9,color=MUTED).pack(side='right',padx=12);label(f,textvariable=self.clock,size=10,color=MUTED).pack(side='right')
        self.pause_button=Button(f,'暂停输入',self.pause,width=78,height=26);self.pause_button.pack(side='right',padx=12);self.pause_button.set(enabled=False)
        messages=tk.Frame(parent,bg=BG);messages.grid(row=3,column=0,sticky='ew',pady=(0,8))
        label(messages,textvariable=self.status,size=9,color=MUTED,anchor='w',wraplength=920).pack(fill='x')
        label(messages,textvariable=self.error,size=9,color='#AD613F',anchor='w',wraplength=920).pack(fill='x')
        columns=tk.Frame(parent,bg=BG);columns.grid(row=4,column=0,sticky='nsew');columns.columnconfigure((0,1),weight=1,uniform='text');columns.rowconfigure(0,weight=1)
        self.boxes={}
        for i,(kind,title,lang) in enumerate([('source','原文','SOURCE'),('translation','译文','TRANSLATION')]):
            card=Card(columns);card.grid(row=0,column=i,sticky='nsew',padx=(0,6) if i==0 else (6,0));f=card.body
            top=tk.Frame(f,bg=WHITE);top.pack(fill='x',pady=(0,10));label(top,title,15,bold=True).pack(side='left')
            label(top,lang,8,color=MUTED).pack(side='left',padx=12);Button(top,'复制',lambda k=kind:self.copy(k),height=28,width=48).pack(side='right')
            box=tk.Text(f,wrap='word',width=20,height=8,bg=WHITE,fg=INK,relief='flat',highlightthickness=0,font=(FONT,self.config['font_size']),spacing1=4,spacing3=9,state='disabled')
            box.pack(fill='both',expand=True);box.tag_configure('time',foreground=MUTED,font=(FONT,9));self.boxes[kind]=box
        footer=tk.Frame(parent,bg=BG);footer.grid(row=5,column=0,sticky='ew',pady=(12,0))
        self.save_hint=label(footer,'✓  自动保存至本机',9,color=MUTED);self.save_hint.pack(side='left')
        Button(footer,'导出记录',self.export,primary=True,width=120).pack(side='right')

    def _voices(self,parent):
        top=tk.Frame(parent,bg=BG);top.pack(fill='x',pady=(0,12))
        label(top,'为每一位发言人保存熟悉的声音',13,bold=True).pack(side='left')
        self.add_button=Button(top,'＋ 新增声音',self.add_voice,primary=True);self.add_button.pack(side='right')
        self.voice_tree=ttk.Treeview(parent,columns=('name','type'),show='headings',selectmode='browse')
        self.voice_tree.heading('name',text='声音名称');self.voice_tree.heading('type',text='类型');self.voice_tree.column('name',width=430);self.voice_tree.column('type',width=180)
        self.voice_tree.pack(fill='both',expand=True)
        self.voice_tree.tag_configure('alternate',background='#F8FAFD')
        actions=tk.Frame(parent,bg=BG);actions.pack(fill='x',pady=16)
        Button(actions,'使用所选声音',self.use_voice,primary=True).pack(side='left');Button(actions,'重命名',self.rename_voice).pack(side='left',padx=10)
        label(parent,'录音在试听后才上传。实时复刻在每次续接时需重新提取音色，长时间同传建议使用保存的音色。',10,color=MUTED,wraplength=850,anchor='w').pack(fill='x')

    def _terms(self,parent):
        label(parent,'让专业术语保持一致',15,bold=True).pack(anchor='w')
        label(parent,'每行填写：原词 = 译法。最多 100 条；在下一次开始同传时生效。',10,color=MUTED).pack(anchor='w',pady=(8,15))
        self.term_text=tk.Text(parent,bg=WHITE,fg=INK,relief='flat',font=(FONT,12),padx=18,pady=18,wrap='word',undo=True)
        self.term_text.pack(fill='both',expand=True);self.term_text.insert('1.0','\n'.join(k+' = '+v for k,v in self.config['terms'].items()))
        row=tk.Frame(parent,bg=BG);row.pack(fill='x',pady=14)
        Toggle(row,self.doc).pack(side='left');label(row,'DOC 按字母拼读（尽力提示）',10,color=MUTED).pack(side='left',padx=10)
        Button(row,'保存术语',self.save_terms,primary=True).pack(side='right')

    def _history(self,parent):
        row=tk.Frame(parent,bg=BG);row.pack(fill='x',pady=(0,12))
        self.search=tk.StringVar();entry=ttk.Entry(row,textvariable=self.search,width=35);entry.pack(side='left');entry.bind('<Return>',lambda e:self.refresh_history())
        Button(row,'搜索',self.refresh_history).pack(side='left',padx=8);Button(row,'导出所选记录',self.export_history,primary=True).pack(side='right')
        self.history_tree=ttk.Treeview(parent,columns=('time','direction','voice','state'),show='headings',height=7,selectmode='browse')
        for key,title,width in [('time','开始时间',180),('direction','目标语言',100),('voice','声音',240),('state','状态',180)]:
            self.history_tree.heading(key,text=title);self.history_tree.column(key,width=width)
        self.history_tree.pack(fill='x');self.history_tree.bind('<<TreeviewSelect>>',self.history_selected)
        self.history_preview=tk.Text(parent,font=(FONT,11),bg=WHITE,fg=INK,relief='flat',wrap='word',padx=18,pady=15,state='disabled')
        self.history_preview.pack(fill='both',expand=True,pady=(12,0))

    def _settings(self,parent):
        canvas=tk.Canvas(parent,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        inner=tk.Frame(canvas,bg=BG);window=canvas.create_window(0,0,anchor='nw',window=inner)
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        parent=inner
        card=Card(parent,height=580);card.pack(fill='x');f=card.body
        label(f,'运行与连接',16,bold=True).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,16))
        for i,(text,var) in enumerate([('连接中断时自动重连',self.reconnect),('自动保存文字记录到本机',self.auto)],1):
            label(f,text,11).grid(row=i,column=0,sticky='w',pady=12);Toggle(f,var).grid(row=i,column=1,sticky='w',padx=30)
        label(f,'会话续接间隔（分钟）',11).grid(row=3,column=0,sticky='w',pady=12)
        ttk.Combobox(f,textvariable=self.rotate,values=['3','5','8'],state='readonly',width=10).grid(row=3,column=1,sticky='w',padx=30)
        label(f,'正文大小',11).grid(row=4,column=0,sticky='w',pady=12)
        ttk.Combobox(f,textvariable=self.fontsize,values=['11','12','14','16'],state='readonly',width=10).grid(row=4,column=1,sticky='w',padx=30)
        label(f,'译音音量',11).grid(row=5,column=0,sticky='w',pady=12)
        tk.Scale(f,from_=0,to=100,orient='horizontal',variable=self.volume,command=self.volume_changed,bg=WHITE,fg=MUTED,highlightthickness=0,troughcolor=LINE,length=240,relief='flat').grid(row=5,column=1,sticky='w',padx=22)
        self.connection_vars={}
        for row,(key,title) in enumerate([('model','兼容实时翻译模型'),('endpoint','WebSocket 接口'),('enrollment','声音复刻接口'),('protocol','协议版本')],6):
            label(f,title,10).grid(row=row,column=0,sticky='w',pady=4)
            variable=tk.StringVar(value=self.config.get(key,''));self.connection_vars[key]=variable
            widget=ttk.Combobox(f,textvariable=variable,values=['qwen38','qwen35'],state='readonly',width=42) if key=='protocol' else ttk.Entry(f,textvariable=variable,width=42)
            widget.grid(row=row,column=1,sticky='ew',padx=30,pady=3)
        label(f,'替换 API key（留空保持现有）',10).grid(row=10,column=0,sticky='w',pady=4)
        self.key_input=ttk.Entry(f,show='•',width=42);self.key_input.grid(row=10,column=1,sticky='ew',padx=30,pady=3)
        Button(f,'保存设置',self.save_settings,primary=True).grid(row=11,column=0,sticky='w',pady=12)
        Button(f,'刷新音频设备',self.refresh_devices).grid(row=11,column=1,sticky='w',padx=30,pady=12)
        label(parent,'Ctrl + Enter 开始 / 停止    ·    Ctrl + S 导出记录',10,color=MUTED).pack(anchor='w',pady=(22,10))
        label(parent,'数据保存在当前 Windows 用户的 AppData 中，更新软件不会覆盖。\n不保存原始录音；诊断日志仅记录状态与错误，自动控制文件大小。',10,color=MUTED,justify='left').pack(anchor='w',pady=8)
        Button(parent,'打开数据文件夹',lambda:open_folder(DATA)).pack(anchor='w',pady=12)

    def show(self,name):
        for page in self.pages.values():page.pack_forget()
        self.pages[name].pack(fill='both',expand=True);self.page=name;self.heading.configure(text=name)
        self.subtitle.configure(text={'实时同传':'保留声音，让交流跨越语言','声音库':'录制、命名，让每个人拥有自己的译音','术语表':'为专业交流准备准确的词汇','历史记录':'重要的对话，随时回看','设置':'保持轻量，专注稳定的同传体验'}[name])
        for n,b in self.nav.items():b.set(selected=n==name)
        if name=='历史记录':self.refresh_history()

    def refresh_devices(self):
        if self.session:return
        try:
            devices=sd.query_devices();apis=sd.query_hostapis()
            def choices(direction):
                result={'系统默认设备':None}
                for i,d in enumerate(devices):
                    if d['max_'+direction+'_channels']>0 and apis[d['hostapi']]['name'] in ('Windows WASAPI','MME','Core Audio','ALSA','PulseAudio'):
                        result[d['name']+' ['+apis[d['hostapi']]['name']+']']=i
                return result
            self.inputs=choices('input');self.outputs=choices('output')
            for var,widget,values,key in [(self.input,self.input_box,self.inputs,'input'),(self.output,self.output_box,self.outputs,'output')]:
                widget['values']=list(values);saved=var.get() or self.config.get(key)
                var.set(saved if saved in values else '系统默认设备')
        except Exception as error:self.error.set(str(error))

    def refresh_voices(self,identity=None):
        self.profiles=self.library.load();self.voice_box['values']=[p['name'] for p in self.profiles]
        selected=next((p for p in self.profiles if p['id']==(identity or self.config['voice'])),self.profiles[0]);self.voice.set(selected['name'])
        self.voice_tree.delete(*self.voice_tree.get_children())
        for i,p in enumerate(self.profiles):self.voice_tree.insert('',tk.END,iid=p['id'],values=(p['name'],'保存的声音' if p['mode']=='never' else '实时复刻' if p['mode'] else '预设音色'),tags=('alternate',) if i%2 else ())

    def use_voice(self):
        if self.session:messagebox.showinfo('正在同传','请停止同传后切换声音。');return
        chosen=self.voice_tree.selection()
        if chosen:self.refresh_voices(chosen[0]);self.show('实时同传')
    def rename_voice(self):
        if self.session:return
        chosen=self.voice_tree.selection()
        if not chosen:return
        profile=next(p for p in self.profiles if p['id']==chosen[0]);name=simpledialog.askstring('声音命名','新的声音名称：',initialvalue=profile['name'],parent=self.root)
        if name is not None:
            try:self.library.rename(profile['id'],name);self.refresh_voices(profile['id'])
            except Exception as error:messagebox.showerror('无法保存',str(error))
    def add_voice(self):
        if self.session:return
        self.voice_dialog=VoiceDialog(self.root,self.inputs[self.input.get()],self.library,lambda p:self.refresh_voices(p['id']),resample_pcm)

    def save_terms(self):
        try:
            pairs={}
            for line in self.term_text.get('1.0','end').splitlines():
                if not line.strip():continue
                if '=' not in line:raise ValueError('每行需要使用 = 分隔原词和译法。')
                key,value=(p.strip() for p in line.split('=',1))
                if not key or not value or len(key)>100 or len(value)>200:raise ValueError('术语不能为空；原词最多 100 字，译法最多 200 字。')
                pairs[key]=value
            if len(pairs)>100:raise ValueError('最多保存 100 条术语。')
            self.config.update(terms=pairs,doc=self.doc.get());write_json('settings.json',self.config);self.status.set('术语已保存，下次开始时生效。')
            messagebox.showinfo('已保存','术语已保存，下次开始同传时生效。')
        except Exception as error:messagebox.showerror('无法保存',str(error))
    def save_settings(self):
        try:
            proposed={**self.config,**{k:v.get().strip() for k,v in self.connection_vars.items()}}
            endpoint_url(proposed)
            if self.key_input.get().strip():set_key(self.key_input.get())
            self.config.update(proposed);self.key_input.delete(0,'end')
        except Exception as error:
            messagebox.showerror('无法保存',str(error));return
        self.config.update(autosave=self.auto.get(),reconnect=self.reconnect.get(),rotate_seconds=int(self.rotate.get())*60,font_size=int(self.fontsize.get()),volume=self.volume.get())
        write_json('settings.json',self.config)
        for box in self.boxes.values():box.configure(font=(FONT,self.config['font_size']))
        messagebox.showinfo('已保存','设置已保存；连接和续接策略在下次开始时生效。')
    def volume_changed(self,value):
        if self.session:self.session.volume=float(value)/100

    def lock(self,active):
        for widget in (self.input_box,self.output_box,self.voice_box,self.target_box):widget.configure(state='disabled' if active else 'readonly')
        self.speak_toggle.enabled=not active
        for button in (self.test_button,self.start_button,self.add_button):button.set(enabled=not active)
        self.stop_button.set(enabled=active,text='停止');self.pause_button.set(enabled=active and not self.session.local_only if self.session else False)

    def start(self,local_only=False):
        if self.session:return
        try:
            self.error.set('');self.lines={};self.dirty=True;self.captured=self.sent=0;self.started=time.monotonic()
            profile=next(p for p in self.profiles if p['name']==self.voice.get())
            self.config.update(target=languages.code(self.target.get()),voice=profile['id'],input=self.input.get(),output=self.output.get(),speak=self.speak.get(),doc=self.doc.get(),volume=self.volume.get())
            if not languages.audio(self.config['target']):self.config['speak']=False;self.speak.set(False)
            write_json('settings.json',self.config)
            self.session_id=self.history.start(self.config['target'],profile['name']) if not local_only and self.config['autosave'] else None
            self.save_hint.configure(text='✓  自动保存至本机' if self.session_id else '仅在本次窗口保留，可手动导出')
            self.session=AudioSession(self.events,self.inputs[self.input.get()],self.outputs[self.output.get()],self.config,profile,local_only)
            self.lock(True);self.status.set('正在打开麦克风…');self.state.set('连接中');self.segment.set('第 0 段');self.show('实时同传');self.session.worker.start()
        except Exception as error:
            self.error.set(str(error));self.session=None;self.lock(False)
            if self.session_id:self.history.end(self.session_id,'启动失败')

    def stop(self):
        if not self.session:return
        if self.session.stop.is_set():self.session.abort.set();self.status.set('正在立即结束…');return
        self.session.stop.set();self.stop_button.set(text='立即结束');self.pause_button.set(enabled=False)
        self.status.set('停止采集，接收剩余译文；再次点击可立即结束。')
    def pause(self):
        if self.session:
            self.session.paused=not self.session.paused;self.pause_button.set(text='恢复输入' if self.session.paused else '暂停输入')
            self.status.set('输入已暂停，期间的讲话不会上传。' if self.session.paused else '已恢复输入。')

    def draw_wave(self):
        c=self.wave_canvas;c.delete('all');width=c.winfo_width();step=max(3,(width-25)/len(self.wave))
        for i,db in enumerate(self.wave):
            height=px(3+min(40,max(0,db+58)))
            center=c.winfo_height()/2
            c.create_line(12+i*step,center-height/2,12+i*step,center+height/2,fill=BLUE if db>-50 else '#DDE5F7',width=px(4),capstyle='round')

    def add_line(self,kind,item,text,append):
        key=(kind,item);old=self.lines.get(key)
        at=old[1] if old else max(0,time.monotonic()-self.started)
        value=(old[2] if old else '')+text if append else text
        self.lines[key]=(kind,at,value);self.dirty=True
        if self.session_id:self.history.put(self.session_id,item,kind,at,value)

    def render_lines(self):
        for kind,box in self.boxes.items():
            rows=[r for r in self.lines.values() if r[0]==kind][-200:]
            at_bottom=box.yview()[1]>=.98
            box.configure(state='normal');box.delete('1.0','end')
            if not rows:box.insert('end','等待讲话…','time')
            for _,at,text in rows:box.insert('end',timestamp(at)+'\n','time');box.insert('end',text+'\n\n')
            if at_bottom:box.see('end')
            box.configure(state='disabled')
        self.dirty=False

    def poll(self):
        newest_level=None
        for _ in range(500):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='level':newest_level=value
            elif kind=='sent':self.sent,backlog=value;self.counter.set(f'已发送 {self.sent:.1f}s · 待发送 {backlog:.1f}s')
            elif kind=='state':self.state.set(value);self.badge.configure(text='● '+value,fg=GREEN if value=='已连接' else MUTED)
            elif kind=='status':self.status.set(value)
            elif kind=='segment':self.segment.set(f'第 {value} 段')
            elif kind in ('source','translation'):self.add_line(kind,*value)
            elif kind in ('warning','error','notice'):
                self.error.set(value)
                if kind in ('error','notice'):self.add_line('notice',str(time.monotonic_ns()),value,False)
            elif kind=='done':
                if self.session_id:self.history.end(self.session_id)
                self.session=None;self.lock(False);self.pause_button.set(text='暂停输入');self.state.set('已结束');self.badge.configure(text='● 已结束',fg=MUTED);self.status.set('已结束。可以导出记录或开始新的同传。')
        if newest_level:
            db,self.captured=newest_level;self.wave.append(db);self.db.set(f'{db:.0f} dBFS' if db>-100 else '静音');self.draw_wave()
        if self.session:self.clock.set(timestamp(time.monotonic()-self.started))
        if self.dirty:self.render_lines()
        if time.monotonic()-self.last_commit>2:self.history.flush();self.last_commit=time.monotonic()
        if not self.closing:self.root.after(80,self.poll)

    def copy(self,kind):
        text='\n\n'.join(r[2] for r in self.lines.values() if r[0]==kind)
        self.root.clipboard_clear();self.root.clipboard_append(text);self.status.set('已复制'+('原文' if kind=='source' else '译文')+'。')
    def export(self,rows=None):
        rows=list(self.lines.values()) if rows is None else rows
        if not rows:messagebox.showinfo('暂无记录','开始同传后即可导出。');return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.txt',initialfile='声桥同传记录.txt',filetypes=[('双语文字','*.txt'),('字幕（按译文到达时间）','*.srt'),('结构化记录','*.json')])
        if path:
            try:
                suffix=Path(path).suffix.lower();text=export_srt(rows) if suffix=='.srt' else json.dumps([dict(kind=k,seconds=s,text=t) for k,s,t in rows],ensure_ascii=False,indent=2) if suffix=='.json' else export_text(rows)
                Path(path).write_text(text,encoding='utf-8');self.status.set('记录已导出。')
            except Exception as error:messagebox.showerror('导出失败',str(error))
    def refresh_history(self):
        self.history.flush();self.history_tree.delete(*self.history_tree.get_children())
        for identity,created,target,voice,state in self.history.list(self.search.get()):self.history_tree.insert('',tk.END,iid=identity,values=(created.replace('T',' '),languages.name(target),voice,state))
    def history_selected(self,event=None):
        choice=self.history_tree.selection()
        if choice:
            self.history_preview.configure(state='normal');self.history_preview.delete('1.0','end');self.history_preview.insert('end',export_text(self.history.lines(choice[0])));self.history_preview.configure(state='disabled')
    def export_history(self):
        choice=self.history_tree.selection()
        if choice:self.export(self.history.lines(choice[0]))

    def close(self):
        if self.voice_dialog and not self.voice_dialog.closed:
            self.voice_dialog.close()
            if not self.voice_dialog.closed:return
        self.closing=True
        if self.session:
            self.session.stop.set();self.session.abort.set()
            if self.session_id:self.history.end(self.session_id,'关闭窗口')
        self.history.flush();self.history.db.close();self.root.destroy()

def main():
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    root=tk.Tk()
    try:App(root);root.mainloop()
    except Exception as error:
        messagebox.showerror('声桥无法启动',str(error),parent=root);root.destroy();raise

if __name__=='__main__':main()
