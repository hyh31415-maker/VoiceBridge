from .platform_support import FONT,com_start,com_end,open_folder
import tkinter as tk
from tkinter import ttk
import tkinter.font as font

BG='#F4F6FA';WHITE='#FFFFFF';INK='#192B50';MUTED='#7B89A6';BLUE='#3864ED';LINE='#E4EAF3';GREEN='#0FB98B'
SCALE=1.0
def px(value):return round(value*SCALE)

def rounded(canvas,x,y,w,h,r=12,**options):
    return canvas.create_polygon(x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y,smooth=True,**options)

def label(parent,text='',size=11,color=INK,bold=False,**kw):
    return tk.Label(parent,text=text,font=(FONT,size,'bold' if bold else 'normal'),fg=color,bg=parent.cget('bg'),**kw)

class Card(tk.Canvas):
    def __init__(self,parent,padding=18,**kw):
        padding=px(padding)
        if 'height' in kw:kw['height']=px(kw['height'])
        super().__init__(parent,bg=BG,highlightthickness=0,bd=0,**kw)
        self.padding=padding;self.body=tk.Frame(self,bg=WHITE)
        self.shape=rounded(self,1,1,100,100,fill=WHITE,outline=LINE)
        self.window=self.create_window(padding,padding,window=self.body,anchor='nw')
        self.bind('<Configure>',self.resize)
    def resize(self,event):
        w,h=event.width,event.height;r=13
        self.coords(self.shape,r,1,w-r,1,w-1,1,w-1,r,w-1,h-r,w-1,h-1,w-r,h-1,r,h-1,1,h-1,1,h-r,1,r,1,1)
        self.itemconfigure(self.window,width=max(1,w-2*self.padding),height=max(1,h-2*self.padding))

class Button(tk.Canvas):
    def __init__(self,parent,text,command=None,primary=False,width=None,height=40,**kw):
        self.text=text;self.command=command;self.primary=primary;self.enabled=True;self.selected=False
        self.font=font.Font(family=FONT,size=10)
        super().__init__(parent,width=px(width) if width else self.font.measure(text)+px(32),height=px(height),bg=parent.cget('bg'),highlightthickness=0,bd=0,cursor='hand2',takefocus=True,**kw)
        self.bind('<Configure>',lambda e:self.draw());self.bind('<Enter>',lambda e:self.draw(True));self.bind('<Leave>',lambda e:self.draw())
        self.bind('<Button-1>',self.invoke);self.bind('<Return>',self.invoke);self.bind('<space>',self.invoke)
        self.bind('<FocusIn>',lambda e:self.draw());self.bind('<FocusOut>',lambda e:self.draw())
    def draw(self,hover=False):
        self.delete('all');w=self.winfo_width();h=self.winfo_height()
        strong=self.primary or self.selected
        fill=('#2D56D7' if hover else BLUE) if strong else ('#EAF0FF' if hover else '#F5F7FC')
        if not self.enabled:fill='#F0F2F7'
        rounded(self,1,1,w-2,h-2,9,fill=fill,outline=BLUE if self.focus_get()==self and self.enabled else (fill if strong else LINE))
        self.create_text(w/2,h/2,text=self.text,font=self.font,fill=('#FFFFFF' if strong else '#536788') if self.enabled else '#AEB8C9')
    def invoke(self,event=None):
        if self.enabled and self.command:self.command()
    def set(self,enabled=None,text=None,selected=None):
        if enabled is not None:self.enabled=enabled
        if text is not None:self.text=text
        if selected is not None:self.selected=selected
        self.configure(cursor='hand2' if self.enabled else 'arrow');self.draw()

class Toggle(tk.Canvas):
    def __init__(self,parent,variable,command=None):
        super().__init__(parent,width=px(42),height=px(24),bg=parent.cget('bg'),highlightthickness=0,cursor='hand2',takefocus=True)
        self.var=variable;self.command=command;self.enabled=True
        self.bind('<Button-1>',self.flip);self.bind('<space>',self.flip);self.var.trace_add('write',lambda *a:self.draw());self.draw()
    def flip(self,event=None):
        if self.enabled:
            self.var.set(not self.var.get())
            if self.command:self.command()
    def draw(self):
        self.delete('all');rounded(self,0,px(1),px(42),px(22),px(11),fill=BLUE if self.var.get() else '#C6CFDE',outline='')
        x=px(22 if self.var.get() else 2);self.create_oval(x,px(3),x+px(18),px(21),fill=WHITE,outline='')

def theme(root):
    global SCALE
    SCALE=max(1,root.winfo_fpixels('1i')/96)
    root.configure(bg=BG)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=(FONT,10))
    style.configure('TFrame',background=BG);style.configure('TLabel',background=BG,foreground=INK)
    style.configure('TButton',padding=(12,8),background='#EEF2FB',foreground=INK,borderwidth=0)
    style.configure('TCombobox',fieldbackground=WHITE,background=WHITE,foreground=INK,arrowcolor=MUTED,padding=8,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.map('TCombobox',fieldbackground=[('readonly',WHITE)],selectbackground=[('readonly',WHITE)],selectforeground=[('readonly',INK)])
    style.configure('TEntry',padding=7,fieldbackground=WHITE,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.configure('Treeview',background=WHITE,fieldbackground=WHITE,foreground=INK,rowheight=px(44),borderwidth=0,relief='flat')
    style.configure('Treeview.Heading',background='#F4F6FA',foreground=MUTED,font=(FONT,10),padding=9,relief='flat',borderwidth=0)
    style.map('Treeview',background=[('selected','#E8EEFF')],foreground=[('selected',BLUE)])
    style.configure('Horizontal.TProgressbar',background=BLUE,troughcolor=LINE)
