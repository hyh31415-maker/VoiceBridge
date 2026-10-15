from .platform_support import FONT,com_start,com_end,open_folder
"""Record, audition and explicitly save a named speaker voice."""
import asyncio
import ctypes
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .audio import level
import sounddevice as sd
from .service import create_voice, wav_bytes
from .widgets import px

READING = ('大家好，这是我的声音样本。我正在用自然的语速录制一段清晰的语音。'
           '今天我们一起讨论新的研究计划，希望通过这次交流，让不同语言之间的沟通更加顺畅。')


class VoiceDialog:
    def __init__(self, parent, device, library, on_saved, resample):
        self.device, self.library, self.on_saved, self.resample = device, library, on_saved, resample
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = None
        self.pcm = None
        self.rate = int(sd.query_devices(device, kind='input')['default_samplerate'])
        self.closed = False
        self.window = tk.Toplevel(parent)
        self.window.title('新增声音 · 录音并命名')
        self.window.geometry(f'{px(700)}x{px(560)}')
        self.window.transient(parent)
        self.window.grab_set()
        panel = ttk.Frame(self.window, padding=22)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='保存一个人的声音', font=(FONT, 18, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='每个人单独录制一段，使用自己的或已获授权的声音。').pack(anchor='w', pady=8)
        line = ttk.Frame(panel); line.pack(fill='x', pady=8)
        ttk.Label(line, text='声音名称').pack(side='left')
        self.name = ttk.Entry(line, width=35)
        self.name.pack(side='left', padx=12)
        self.name.focus_set()
        ttk.Label(panel, text='麦克风：' + sd.query_devices(device, kind='input')['name'], wraplength=650).pack(anchor='w', pady=5)
        ttk.Label(panel, text='点击录制后，按平时说话的声音连续朗读约 15 秒：').pack(anchor='w', pady=(10, 5))
        ttk.Label(panel, text=READING, wraplength=640, font=(FONT, 12)).pack(anchor='w')
        self.level = ttk.Progressbar(panel, maximum=60)
        self.level.pack(fill='x', pady=12)
        self.status = tk.StringVar(value='等待录制；录音暂存内存，点击保存前不会上传。')
        ttk.Label(panel, textvariable=self.status, wraplength=640).pack(anchor='w', pady=5)
        buttons = ttk.Frame(panel); buttons.pack(fill='x', pady=15)
        self.record = ttk.Button(buttons, text='录制 15 秒', command=self.start_record)
        self.record.pack(side='left')
        self.stop = ttk.Button(buttons, text='停止录音', command=self.stop_record, state='disabled')
        self.stop.pack(side='left', padx=8)
        self.listen = ttk.Button(buttons, text='试听录音', command=self.preview, state='disabled')
        self.listen.pack(side='left')
        self.save = ttk.Button(buttons, text='上传并保存声音', command=self.upload, state='disabled')
        self.save.pack(side='right')
        ttk.Label(panel, text='保存时录音会发送至千问声音复刻 API，创建可重复使用的音色（按平台规则计费）。'
                  '本地保存名称和音色 ID，不保存原始录音。', wraplength=640).pack(anchor='w', pady=8)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.after(80, self.poll)

    def controls(self):
        active = self.busy is not None
        self.record.configure(state='disabled' if active else 'normal')
        self.name.configure(state='disabled' if active else 'normal')
        self.stop.configure(state='normal' if self.busy == 'record' else 'disabled')
        state = 'normal' if self.pcm and not active else 'disabled'
        self.listen.configure(state=state); self.save.configure(state=state)

    def start_record(self):
        self.busy = 'record'; self.pcm = None; self.cancel.clear(); self.controls()
        self.status.set('正在录音，请开始朗读…')
        threading.Thread(target=self.record_worker, daemon=True).start()

    def record_worker(self):
        hr = com_start()
        try:
            if hr not in (0, 1):
                raise RuntimeError('音频线程初始化失败。')
            chunks = []; voiced = 0
            with sd.RawInputStream(device=self.device, channels=1, dtype='int16', samplerate=self.rate,
                                   blocksize=self.rate // 10) as recorder:
                for step in range(150):
                    if self.cancel.is_set(): break
                    data, overflow = recorder.read(self.rate // 10)
                    if overflow: raise RuntimeError('录音出现丢帧，请关闭占用麦克风的程序后重新录制。')
                    pcm = bytes(data); chunks.append(pcm)
                    db = level(pcm)
                    if db > -55: voiced += .1
                    self.events.put(('level', (db, (step + 1) / 10)))
            if len(chunks) < 50 or voiced < 3:
                raise ValueError('有效录音不足，请至少录制 5 秒并连续清晰讲话；推荐完整录制 15 秒。')
            self.events.put(('recorded', b''.join(chunks)))
        except Exception as error:
            self.events.put(('error', str(error)))
        finally:
            if hr in (0, 1): com_end(hr)

    def stop_record(self):
        self.cancel.set(); self.stop.configure(state='disabled')

    def preview(self):
        self.busy = 'preview'; self.cancel.clear(); self.controls()
        self.status.set('正在播放原始录音…')
        threading.Thread(target=self.preview_worker, daemon=True).start()

    def preview_worker(self):
        hr = com_start()
        try:
            output_rate = int(sd.query_devices(kind='output')['default_samplerate'])
            audio = self.resample(self.pcm, self.rate, output_rate)
            with sd.RawOutputStream(channels=1, dtype='int16', samplerate=output_rate) as player:
                for offset in range(0, len(audio), output_rate // 5):
                    if self.cancel.is_set(): break
                    player.write(audio[offset:offset + output_rate // 5])
            self.events.put(('previewed', None))
        except Exception as error:
            self.events.put(('error', str(error)))
        finally:
            if hr in (0, 1): com_end(hr)

    def upload(self):
        try:
            name = self.library.check_name(self.name.get())
        except ValueError as error:
            self.status.set(str(error)); return
        self.busy = 'upload'; self.controls()
        self.status.set('正在上传并创建音色，请稍候…')
        audio = wav_bytes(self.resample(self.pcm, self.rate, 24000), 24000)
        threading.Thread(target=self.upload_worker, args=(name, audio), daemon=True).start()

    def upload_worker(self, name, audio):
        try:
            voice = asyncio.run(create_voice(audio))
            try:
                profile = self.library.add(name, voice)
            except Exception as error:
                # Preserve the successfully created ID even if local naming/persistence fails.
                raise RuntimeError(f'云端已创建音色，但本地保存失败：{error}。音色 ID：{voice}') from error
            self.events.put(('saved', profile))
        except Exception as error:
            self.events.put(('error', str(error)))

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'level':
                db, seconds = value; self.level['value'] = max(0, min(60, db + 60))
                self.status.set(f'录制 {seconds:.1f} / 15 秒 · 输入 {db:.1f} dBFS')
            elif kind == 'recorded':
                self.pcm = value; self.busy = None; self.controls()
                self.status.set('录音完成，可以试听；满意后填写名称，点击“上传并保存声音”。')
            elif kind == 'previewed':
                self.busy = None; self.controls(); self.status.set('试听结束，可以保存或重新录制。')
            elif kind == 'saved':
                self.busy = None; self.on_saved(value); self.close(); return
            elif kind == 'error':
                self.busy = None; self.controls(); self.status.set(value)
        if not self.closed: self.window.after(80, self.poll)

    def close(self):
        if self.busy == 'upload':
            self.status.set('正在创建云端音色，请等待结果后关闭，避免丢失音色 ID。'); return
        self.closed = True; self.cancel.set(); self.pcm = None
        self.window.grab_release(); self.window.destroy()
