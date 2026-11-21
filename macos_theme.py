"""Presentation-only design tokens and widgets. No settings or data mutations."""
import tkinter as tk
from tkinter import ttk, font as tkfont
import customtkinter as ctk

MACOS_THEME = {
    'bg_window':'#F0F4F8','bg_card':'#FFFFFF','border_card':'#DCE5EF',
    'bg_input':'#F1F5FA','border_input':'#CCD9E6','primary':'#007AFF',
    'primary_hover':'#0062CC','secondary_hover':'#E3EDF8','text':'#172A40',
    'muted':'#52647C','hint':'#65758B','success_bg':'#E8F8EE','success':'#248A3D',
    'footer':'#E7EEF6','log':'#F7FAFD','white':'#FFFFFF',
    'nav_surface':'#E2EBF5','selected_bg':'#DDEEFF','selected_text':'#174A76',
    'quota_track':'#D8E5F2','focus_surface':'#F6FAFF','disabled':'#77879A',
    'fonts':('PingFang SC','Microsoft YaHei UI','SF Pro Text'),
    # CustomTkinter sizes are logical pixels: 20/15/13/12 correspond to about 15/11/10/9 pt.
    'title_size':20,'section_size':15,'body_size':13,'small_size':12,'tiny_size':11,
    'search_size':15,
    'card_radius':15,'button_radius':9,'pill_radius':12,'border_width':1,
    'control_height':30,'top_height':60,'nav_height':48,'footer_height':32,
    'dialog_body_size':14,'dialog_label_size':13,'dialog_title_size':20,
    'dialog_row_height':36,'dialog_control_height':34,
    'progress_running':'#E5484D','progress_done':'#248A3D','progress_idle':'#A1A1AA',
    'attention':'#D70015','attention_soft':'#FF6961',
    'help_wheel_step':72,
}

def family(root):
    installed=set(tkfont.families(root))
    return next((name for name in MACOS_THEME['fonts'] if name in installed),'TkDefaultFont')

def font(size='body_size',bold=False):
    return ctk.CTkFont(family=family(tk._default_root),size=MACOS_THEME[size],weight='bold' if bold else 'normal')

def frame(parent,card=False,**kwargs):
    opts=dict(fg_color=MACOS_THEME['bg_card'] if card else 'transparent',
              corner_radius=MACOS_THEME['card_radius'] if card else 0,
              border_width=MACOS_THEME['border_width'] if card else 0,
              border_color=MACOS_THEME['border_card'])
    opts.update(kwargs)
    return ctk.CTkFrame(parent,**opts)

def label(parent,text='',size='body_size',muted=False,bold=False,**kwargs):
    opts=dict(text=text,font=font(size,bold),text_color=MACOS_THEME['muted'] if muted else MACOS_THEME['text'],height=20,anchor='w')
    opts.update(kwargs)
    return ctk.CTkLabel(parent,**opts)

def button(parent,text,command,primary=False,width=90,**kwargs):
    opts=dict(text=text,command=command,width=width,height=MACOS_THEME['control_height'],
        font=font(),corner_radius=MACOS_THEME['button_radius'],
        fg_color=MACOS_THEME['primary'] if primary else MACOS_THEME['bg_input'],
        hover_color=MACOS_THEME['primary_hover'] if primary else MACOS_THEME['secondary_hover'],
        text_color=MACOS_THEME['white'] if primary else MACOS_THEME['text'],
        text_color_disabled=MACOS_THEME['disabled'],
        border_width=0 if primary else MACOS_THEME['border_width'],border_color=MACOS_THEME['border_input'])
    opts.update(kwargs)
    return ctk.CTkButton(parent,**opts)

def entry(parent,var,width=140,**kwargs):
    opts=dict(textvariable=var,width=width,height=MACOS_THEME['control_height'],font=font(),
        fg_color=MACOS_THEME['bg_input'],text_color=MACOS_THEME['text'],
        placeholder_text_color=MACOS_THEME['hint'],border_color=MACOS_THEME['border_input'],
        border_width=MACOS_THEME['border_width'],corner_radius=MACOS_THEME['button_radius'])
    opts.update(kwargs)
    widget=ctk.CTkEntry(parent,**opts)
    widget.bind('<FocusIn>',lambda _:widget.configure(border_color=MACOS_THEME['primary'],
        fg_color=MACOS_THEME['focus_surface']),add='+')
    widget.bind('<FocusOut>',lambda _:widget.configure(border_color=opts['border_color'],
        fg_color=opts['fg_color']),add='+')
    return widget


def search_entry(parent, var, **kwargs):
    from ime_font import set_chinese_composition_font

    face = font('search_size')
    field = entry(parent, var, font=face, **kwargs)
    set_chinese_composition_font(field._entry, face.cget('family'),
                                 lambda: face.cget('size') * field._get_widget_scaling())
    return field

def native_styles(root,scale=1):
    """Match the high-volume native list and combobox to the CTk shell."""
    t=MACOS_THEME
    style=ttk.Style(root)
    style.theme_use('clam')
    face=(family(root),-round(t['body_size']*scale))
    style.configure('.',font=face,background=t['bg_window'],foreground=t['text'])
    style.configure('Card.TFrame',background=t['bg_card'])
    style.configure('Group.TCheckbutton',background=t['bg_card'],foreground=t['text'],padding=(8,4),font=face)
    style.configure('Group.TCheckbutton',indicatorsize=round(15*scale),
                    upperbordercolor=t['border_input'],lowerbordercolor=t['border_input'],
                    indicatorforeground=t['white'],indicatormargin=round(5*scale))
    style.map('Group.TCheckbutton',background=[('active',t['bg_window'])],indicatorbackground=[('selected',t['primary']),('!selected',t['white'])])
    # The clam theme draws a cross. Supply a crisp tick while keeping native rows fast.
    from PIL import Image,ImageDraw,ImageTk
    size=max(16,round(18*scale))
    icons=[]
    for selected in (False,True):
        bitmap=Image.new('RGBA',(size*3,size*3),(0,0,0,0))
        pen=ImageDraw.Draw(bitmap)
        pen.rounded_rectangle((1,1,size*3-2,size*3-2),radius=round(size*.65),
            fill=t['primary'] if selected else t['white'],outline=t['primary'] if selected else t['border_input'],width=3)
        if selected:pen.line([(size*.65,size*1.5),(size*1.25,size*2.1),(size*2.35,size*.8)],fill=t['white'],width=max(4,round(size*.24)),joint='curve')
        icons.append(ImageTk.PhotoImage(bitmap.resize((size,size),Image.Resampling.LANCZOS),master=root))
    if not hasattr(root,'_group_check_icons'):
        root._group_check_icons=icons
    else:
        icons=root._group_check_icons
    if 'Group.indicator' not in style.element_names():
        style.element_create('Group.indicator','image',icons[0],('selected',icons[1]),border=0,sticky='')
    style.layout('Group.TCheckbutton',[('Checkbutton.padding',{'sticky':'nswe','children':[
        ('Group.indicator',{'side':'left','sticky':''}),('Checkbutton.focus',{'side':'left','sticky':'w','children':[
            ('Checkbutton.label',{'sticky':'nswe'})]})]})])
    style.configure('Card.TLabel',background=t['bg_card'],foreground=t['muted'],font=face)
    style.configure('Mac.TCombobox',fieldbackground=t['bg_input'],background=t['bg_input'],
                    bordercolor=t['border_input'],arrowcolor=t['muted'],padding=round(5*scale),font=face)
    style.map('Mac.TCombobox',fieldbackground=[('readonly',t['bg_input'])],foreground=[('readonly',t['text'])],selectbackground=[('readonly',t['bg_input'])],selectforeground=[('readonly',t['text'])])
    root.option_add('*TCombobox*Listbox.font',face)
    root.option_add('*TCombobox*Listbox.background',t['white'])
    root.option_add('*TCombobox*Listbox.selectBackground',t['primary'])
    style.configure('Treeview',background=t['bg_card'],fieldbackground=t['bg_card'],rowheight=round(29*scale))
    style.configure('Treeview.Heading',background=t['bg_input'],font=face)
    style.map('Treeview',background=[('selected',t['primary'])],foreground=[('selected',t['white'])])

class PercentProgress(ctk.CTkProgressBar):
    """Keep the existing 0..100 DoubleVar and start(interval)/stop contract."""
    def __init__(self,parent,variable,**kwargs):
        self.percent_variable=variable
        self.fraction=tk.DoubleVar(parent,value=variable.get()/100)
        super().__init__(parent,variable=self.fraction,**kwargs)
        self.trace=variable.trace_add('write',lambda *_:self.fraction.set(variable.get()/100))

    def start(self,interval=None):
        super().start()

    def set_state(self,state):
        self.configure(progress_color=MACOS_THEME['progress_done' if state=='done' else 'progress_running' if state in ('running','error') else 'progress_idle'])
        if hasattr(self,'milestones'):
            self.milestones.set_state(state)

    def destroy(self):
        self.percent_variable.trace_remove('write',self.trace)
        super().destroy()

class Tooltip:
    def __init__(self,widget,text):
        self.widget,self.text,self.window,self.job=widget,text,None,None
        widget.bind('<Enter>',self.schedule,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')

    def schedule(self,_=None):
        self.hide()
        self.job=self.widget.after(600,self.show)

    def show(self):
        self.job=None
        if not self.widget.winfo_exists(): return
        self.window=tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.attributes('-topmost',True)
        self.window.geometry(f'+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty()+self.widget.winfo_height()+4}')
        text=self.text() if callable(self.text) else self.text
        tk.Label(self.window,text=text,background=MACOS_THEME['bg_card'],foreground=MACOS_THEME['text'],
            font=(family(self.widget),10),padx=10,pady=7,justify='left',wraplength=600,relief='solid',borderwidth=1).pack()

    def hide(self,_=None):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job=None
        if self.window is not None:
            self.window.destroy()
            self.window=None

def fitted_label(parent,var,width=100,transform=None,**kwargs):
    """Ellipsize display only; the source StringVar remains complete."""
    display=tk.StringVar(parent)
    widget=label(parent,textvariable=display,width=width,**kwargs)
    def refresh(_=None,*args):
        value=var.get()
        if transform: value=transform(value)
        room=max(10,widget.winfo_width()-8)
        measure=tkfont.Font(font=widget._label.cget('font')).measure
        if measure(value)>room:
            while value and measure(value+'…')>room: value=value[:-1]
            value+='…'
        display.set(value)
    token=var.trace_add('write',refresh)
    widget.bind('<Configure>',refresh,add='+')
    removed=False
    def cleanup(_=None):
        nonlocal removed
        if not removed:
            removed=True
            var.trace_remove('write',token)
    widget.bind('<Destroy>',cleanup,add='+')
    Tooltip(widget,var.get)
    refresh()
    return widget
