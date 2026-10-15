"""Bounded, thread-safe PCM buffers; no numpy/scipy dependency."""
import audioop
from collections import deque
import math
import threading
import time

class PCMBuffer:
    def __init__(self,limit=16000*2*60):
        self.limit=limit;self.chunks=deque();self.size=0;self.dropped=0;self.lock=threading.Lock()
    def put(self,data,front=False):
        if not data:return
        with self.lock:
            if front:self.chunks.appendleft(data)
            else:self.chunks.append(data)
            self.size+=len(data)
            while self.size>self.limit and self.chunks:
                old=self.chunks.popleft();self.size-=len(old);self.dropped+=len(old)
    def get(self):
        with self.lock:
            if not self.chunks:return None
            data=self.chunks.popleft();self.size-=len(data);return data
    def clear(self):
        with self.lock:self.chunks.clear();self.size=0
    def take(self,n):
        with self.lock:
            pieces=[];count=0
            while count<n and self.chunks:
                data=self.chunks.popleft();length=min(n-count,len(data));pieces.append(data[:length]);count+=length;self.size-=length
                if length<len(data):self.chunks.appendleft(data[length:])
            return b''.join(pieces)+bytes(n-count)

class Resampler:
    def __init__(self,source,target):self.source=source;self.target=target;self.state=None
    def process(self,data):
        if self.source==self.target:return bytes(data)
        converted,self.state=audioop.ratecv(data,2,1,self.source,self.target,self.state)
        return converted

def level(data):return 20*math.log10(max(1e-6,audioop.rms(data,2)/32768))

def resample_pcm(data,source,target):return Resampler(source,target).process(data)
