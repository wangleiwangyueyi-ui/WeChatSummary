"""Visual offline help: shared tables, workflow, and local report previews."""
from pathlib import Path
import webbrowser
import customtkinter as ctk
import tkinter as tk
import sys
from tkinter import filedialog,messagebox,ttk
from macos_theme import MACOS_THEME as T,frame,label,button,font,family
from macos_dialogs import dialog,reveal
from help_content import PAGES,paragraphs,URL_PATTERN
from report_format import save_reading_copy


def open_asset(filename):
    webbrowser.open(Path(__file__).with_name(filename).resolve().as_uri())


def reformat_existing(parent):
    path=filedialog.askopenfilename(parent=parent,title='选择已有的摘要 Markdown（不调用 API）',filetypes=[('Markdown 摘要','*.md')])
    if not path:return
    try:
        result=save_reading_copy(path)
        webbrowser.open(result.resolve().as_uri())
        messagebox.showinfo('本地重排完成',f'已另存阅读副本：\n{result}\n\nGemini：0 次；PushPlus：0 次。原文未修改。',parent=parent)
    except Exception as exc:
        messagebox.showerror('无法生成阅读版',str(exc),parent=parent)


class HelpScrollFrame(ctk.CTkScrollableFrame):
    """One DPI-aware wheel path for text, cards, whitespace and scrollbar."""
    def __init__(self,*args,**kwargs):
        self._wheel_remainder=0.0
        super().__init__(*args,**kwargs)

    def _set_scroll_increments(self):
        self._parent_canvas.configure(xscrollincrement=1,yscrollincrement=1)

    def scroll_wheel(self,event):
        canvas=self._parent_canvas
        if canvas.yview()==(0.0,1.0):
            self._wheel_remainder=0.0
            return 'break'
        number=getattr(event,'num',None)
        if number in (4,5):
            notches=1 if number==4 else -1
        else:
            notches=getattr(event,'delta',0)/(120 if sys.platform.startswith('win') else 1)
        self._wheel_remainder-=notches*T['help_wheel_step']*self._get_widget_scaling()
        pixels=int(self._wheel_remainder)
        self._wheel_remainder-=pixels
        if pixels:canvas.yview_scroll(pixels,'units')
        return 'break'

    def _mouse_wheel_all(self,event):
        if self._check_if_valid_scroll(event.widget):
            return self.scroll_wheel(event)


class HelpParagraph(tk.Text):
    """Native full-width text avoids CTk's double-scaled wraplength; URLs are live."""
    def __init__(self,parent,text,scroll_page,size='dialog_body_size',bold=False,muted=False,**_):
        scale=parent._get_widget_scaling()
        color=parent.cget('fg_color')
        if color=='transparent':color=T['bg_card']
        if isinstance(color,(tuple,list)):color=color[0]
        super().__init__(parent,width=1,height=1,wrap='char',borderwidth=0,highlightthickness=0,
            background=color,foreground=T['muted'] if muted else T['text'],cursor='arrow',
            font=(family(parent),-round(T[size]*scale),'bold' if bold else 'normal'),
            padx=0,pady=0,spacing1=2,spacing3=2,exportselection=False)
        self.insert('1.0',text)
        for i,match in enumerate(URL_PATTERN.finditer(text)):
            url=match[0].rstrip('.,;')
            tag=f'url_{i}'
            self.tag_add(tag,f'1.0+{match.start()}c',f'1.0+{match.start()+len(url)}c')
            self.tag_configure(tag,foreground=T['primary'],underline=True)
            self.tag_bind(tag,'<Enter>',lambda _:self.configure(cursor='hand2'))
            self.tag_bind(tag,'<Leave>',lambda _:self.configure(cursor='arrow'))
            self.tag_bind(tag,'<Button-1>',lambda _,target=url:webbrowser.open(target))
        self.configure(state='disabled')
        self._reflow_job=None
        self.bind('<Configure>',self.schedule_reflow)
        self.bind('<Map>',self.schedule_reflow)
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):
            self.bind(event,scroll_page.scroll_wheel)

    def schedule_reflow(self,event=None):
        if self._reflow_job is None:self._reflow_job=self.after_idle(self.reflow)

    def reflow(self):
        self._reflow_job=None
        if not self.winfo_exists() or self.winfo_width()<20:return
        lines=self.count('1.0','end-1c','displaylines')
        height=max(1,(lines[0] if lines else 0)+1)
        if int(self.cget('height'))!=height:self.configure(height=height)


def show_guide(app):
    from macos_ui import PageStack
    window=dialog(app.root,'软件使用说明',900,700,(720,520))
    window.grid_rowconfigure(2,weight=1)
    head=frame(window)
    head.grid(row=0,column=0,sticky='ew',padx=20,pady=(16,8))
    label(head,'软件使用说明',size='dialog_title_size',bold=True).pack(anchor='w')
    label(head,'从快速上手开始 · 表格查配置 · 流程看步骤',muted=True).pack(anchor='w',pady=(4,0))
    stack=PageStack(window)
    stack.grid(row=2,column=0,sticky='nsew',padx=16,pady=(10,0))
    selector=ctk.CTkSegmentedButton(window,values=[name for name,_ in PAGES],command=stack.select,
        font=font('dialog_label_size',True),height=34,fg_color=T['border_card'],selected_color=T['bg_card'],
        selected_hover_color=T['bg_card'],unselected_color=T['border_card'],text_color=T['text'])
    selector.grid(row=1,column=0,sticky='w',padx=16)
    stack.selector=selector
    for name,items in PAGES:
        page=HelpScrollFrame(stack,fg_color=T['bg_window'],corner_radius=0,
            scrollbar_button_color=T['border_input'],scrollbar_button_hover_color=T['hint'])
        # CTkScrollbar.set calls update_idletasks recursively while a long guide
        # reflows. A native scrollbar avoids nested layout passes on high DPI.
        page._scrollbar.grid_remove()
        scrollbar=ttk.Scrollbar(page._parent_frame,orient='vertical',command=page._parent_canvas.yview)
        scrollbar.grid(row=1,column=1,sticky='ns')
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):
            scrollbar.bind(event,page.scroll_wheel)
        page._parent_canvas.configure(yscrollcommand=scrollbar.set)
        page.grid_columnconfigure(0,weight=1)
        stack.pages[name]=page
        wrappers=[]
        def wrapped(parent,text,scroll_page=page,**options):
            options.setdefault('size','dialog_label_size')
            widget=HelpParagraph(parent,text,scroll_page,**options)
            wrappers.append(widget)
            return widget
        for row,item in enumerate(items):
            card=frame(page,card=True)
            card.grid(row=row,column=0,sticky='ew',padx=2,pady=(2,10))
            card.grid_columnconfigure(0,weight=1)
            label(card,item['title'],size='section_size',bold=True).grid(row=0,column=0,sticky='w',padx=16,pady=(14,10))
            if item['kind']=='table':
                table=frame(card)
                table.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,14))
                for c,weight in enumerate((3,5,5)):table.grid_columnconfigure(c,weight=weight,uniform='help_columns')
                for r,values in enumerate([item['headers']]+item['rows']):
                    for c,text in enumerate(values):
                        cell=frame(table,fg_color=T['bg_input'] if r==0 else T['bg_card'],corner_radius=0,
                            border_width=1,border_color=T['border_card'],height=1)
                        cell.grid(row=r,column=c,sticky='nsew')
                        cell.grid_columnconfigure(0,weight=1)
                        wrapped(cell,text,bold=r==0,size='dialog_label_size',width=1).grid(row=0,column=0,sticky='ew',padx=10,pady=10)
            elif item['kind']=='flow':
                for r,(number,title,body) in enumerate(item['steps']):
                    step=frame(card,fg_color=T['bg_input'],corner_radius=8)
                    step.grid(row=r*2+1,column=0,sticky='ew',padx=16)
                    step.grid_columnconfigure(1,weight=1)
                    label(step,number,size='dialog_title_size',bold=True,text_color=T['primary'],width=42).grid(row=0,column=0,rowspan=2,padx=(12,8))
                    label(step,title,bold=True,size='dialog_body_size').grid(row=0,column=1,sticky='w',pady=(8,0))
                    wrapped(step,body,muted=True).grid(row=1,column=1,sticky='ew',padx=(0,12),pady=(2,8))
                    if r<3:label(card,'↓',text_color=T['primary']).grid(row=r*2+2,column=0,pady=2)
                frame(card,height=12).grid(row=9,column=0)
            else:
                for r,text in enumerate(paragraphs(item['body']),1):
                    line=frame(card)
                    line.grid(row=r,column=0,sticky='ew',padx=16,pady=(0,12))
                    line.grid_columnconfigure(1,weight=1)
                    label(line,f'{r}.',text_color=T['primary'],width=26,size='dialog_body_size').grid(row=0,column=0,sticky='nw')
                    wrapped(line,text,size='dialog_body_size').grid(row=0,column=1,sticky='ew')
        page.help_paragraphs=wrappers
    footer=frame(window)
    footer.grid(row=3,column=0,sticky='ew',padx=16,pady=12)
    button(footer,'模板预览 · 0 次 API',lambda:open_asset('总结模板预览.html'),width=156).pack(side='left')
    button(footer,'已有摘要本地重排',lambda:reformat_existing(window),width=152,primary=True).pack(side='left',padx=8)
    button(footer,'网页版说明',lambda:open_asset('软件使用说明.html'),width=106).pack(side='left')
    button(footer,'关闭',window.destroy,width=76).pack(side='right')
    stack.select('快速上手')
    window.guide_pages=stack
    reveal(window)
    return window
