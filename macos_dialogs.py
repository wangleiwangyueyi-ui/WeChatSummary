"""DPI-aware dialog presentation. Credential storage and operations stay in CredentialEditor."""
import tkinter as tk
from tkinter import ttk,font as tkfont
import webbrowser
import sys
import customtkinter as ctk
from macos_theme import MACOS_THEME as T, font, family, frame, label, button, entry, Tooltip


def work_area(parent):
    """Physical monitor work area; Tk can cache virtual screen sizes before DPI setup."""
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
        user32=ctypes.WinDLL('user32',use_last_error=True)
        user32.MonitorFromWindow.argtypes=[wintypes.HWND,wintypes.DWORD]
        user32.MonitorFromWindow.restype=wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        user32.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
        previous=user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            monitor=user32.MonitorFromWindow(parent.winfo_id(),2)
            info=MonitorInfo()
            info.size=ctypes.sizeof(info)
            if user32.GetMonitorInfoW(monitor,ctypes.byref(info)):
                rect=info.work
                return rect.left,rect.top,rect.right,rect.bottom
        finally:
            if previous: user32.SetThreadDpiAwarenessContext(previous)
    return 0,0,parent.winfo_screenwidth(),parent.winfo_screenheight()


def dialog(parent,title,width=900,height=680,minimum=(760,540)):
    window=ctk.CTkToplevel(parent,fg_color=T['bg_window'])
    window.withdraw()
    window.title(title)
    window.transient(parent)
    scale=window._get_window_scaling()
    left,top,right,bottom=work_area(parent)
    available_w=int((right-left)/scale)-32
    available_h=int((bottom-top)/scale)-52
    width,height=min(width,available_w),min(height,available_h)
    window.minsize(min(minimum[0],width),min(minimum[1],height))
    x=max(left+16,min(parent.winfo_rootx()+(parent.winfo_width()-int(width*scale))//2,right-int(width*scale)-16))
    y=max(top+24,min(parent.winfo_rooty()+24,bottom-int(height*scale)-int(40*scale)))
    window.geometry(f'{width}x{height}{x:+d}{y:+d}')
    window.grid_columnconfigure(0,weight=1)
    return window


def reveal(window):
    window.update_idletasks()
    window.deiconify()
    window.lift()


def wrapped(parent,text='',variable=None,**kwargs):
    """Wrap against current logical width, including mixed Chinese/Latin text."""
    opts=dict(justify='left',anchor='w',height=1,size='dialog_label_size',wraplength=600)
    opts.update(kwargs)
    if variable is not None: opts['textvariable']=variable
    widget=label(parent,text,**opts)
    def resize(event):
        width=max(40,int(event.width/widget._get_widget_scaling())-4)
        if widget.cget('wraplength') != width:
            widget.configure(wraplength=width)
    # Bind the outer frame only. CTkLabel.bind also binds its text child, whose
    # intrinsic width changes when wrapping and would recursively shrink it.
    tk.Misc.bind(widget,'<Configure>',resize,add='+')
    return widget


def reading_dialog(parent,title,text,links=()):
    window=dialog(parent,title,820,620,(650,430))
    window.grid_rowconfigure(1,weight=1)
    label(window,title,size='dialog_title_size',bold=True).grid(row=0,column=0,sticky='w',padx=20,pady=(18,12))
    card=frame(window,card=True)
    card.grid(row=1,column=0,sticky='nsew',padx=16)
    card.grid_rowconfigure(0,weight=1)
    card.grid_columnconfigure(0,weight=1)
    scale=card._get_widget_scaling()
    body=tk.Text(card,wrap='word',font=(family(window),-round(T['dialog_body_size']*scale)),
        bg=T['bg_card'],fg=T['text'],borderwidth=0,highlightthickness=0,
        padx=round(16*scale),pady=round(14*scale),spacing1=round(3*scale),spacing3=round(6*scale),width=1,height=1)
    body.grid(row=0,column=0,sticky='nsew',padx=6,pady=6)
    scroll=ctk.CTkScrollbar(card,command=body.yview,fg_color='transparent',button_color=T['border_input'])
    scroll.grid(row=0,column=1,sticky='ns',padx=(0,5),pady=8)
    body.configure(yscrollcommand=scroll.set)
    body.insert('1.0',text)
    body.configure(state='disabled')
    actions=frame(window)
    actions.grid(row=2,column=0,sticky='ew',padx=16,pady=12)
    for caption,url in links:
        button(actions,caption,lambda u=url:webbrowser.open(u),width=150).pack(side='left',padx=(0,8))
    button(actions,'关闭',window.destroy,width=80).pack(side='right')
    window.text_body=body
    reveal(window)
    return window


def author_dialog(app,email):
    window=dialog(app.root,'联系作者 · Boyce',490,240,(430,230))
    card=frame(window,card=True)
    card.pack(fill='both',expand=True,padx=16,pady=16)
    label(card,'Boyce',size='dialog_title_size',bold=True).pack(anchor='w',padx=20,pady=(18,4))
    label(card,'联系邮箱 · 可选中复制',muted=True).pack(anchor='w',padx=20,pady=(0,10))
    value=tk.StringVar(window,value=email)
    field=entry(card,value,font=font('dialog_body_size'),height=36)
    field.configure(state='readonly')
    field.pack(fill='x',padx=20)
    actions=frame(card)
    actions.pack(fill='x',padx=20,pady=16)
    button(actions,'打开邮件软件',lambda:webbrowser.open('mailto:'+email),primary=True,width=120).pack(side='left')
    button(actions,'关闭',window.destroy,width=76).pack(side='right')
    reveal(window)
    return window


def credentials_dialog(app,service,editor_class,refresh):
    from macos_ui import PageStack
    window=dialog(app.root,'Key / Token 管理与额度校准',900,700)
    window.grid_rowconfigure(2,weight=1)
    header=frame(window)
    header.grid(row=0,column=0,sticky='ew',padx=20,pady=(16,8))
    label(header,'凭据与额度管理',size='dialog_title_size',bold=True).pack(side='left')
    label(header,'密钥仅在本机加密保存',muted=True,size='small_size').pack(side='right')
    stack=PageStack(window)
    stack.grid(row=2,column=0,sticky='nsew',padx=16,pady=(8,0))
    selector=ctk.CTkSegmentedButton(window,values=['Gemini Key','PushPlus Token'],command=stack.select,
        font=font('dialog_label_size',True),height=34,fg_color=T['border_card'],
        selected_color=T['bg_card'],selected_hover_color=T['bg_card'],text_color=T['text'],
        unselected_color=T['border_card'],unselected_hover_color=T['bg_input'])
    selector.grid(row=1,column=0,padx=16,sticky='w')
    stack.selector=selector
    views={}
    for kind,title in [('gemini','Gemini Key'),('pushplus','PushPlus Token')]:
        page=frame(stack)
        stack.pages[title]=page
        views[kind]=editor_class(app,window,page,kind,refresh)
    footer=frame(window)
    footer.grid(row=3,column=0,sticky='ew',padx=20,pady=10)
    footer.grid_columnconfigure(0,weight=1)
    wrapped(footer,'修改后点击保存生效；切换凭据不会清零已有用量。',muted=True,size='small_size').grid(row=0,column=0,sticky='ew',padx=(0,12))
    button(footer,'关闭',window.destroy,width=76).grid(row=0,column=1)
    window.credential_editors=views
    window.credential_pages=stack
    stack.select('PushPlus Token' if service=='pushplus' else 'Gemini Key')
    reveal(window)
    return window


def build_credential_editor(editor,page):
    from credential_ui import GEMINI_KEYS_URL,PUSHPLUS_KEYS_URL,GEMINI_LIMIT_URL,show_pushplus_setup,NEW_GROUP_OPTION
    app,window,service=editor.app,editor.window,editor.service
    page.grid_columnconfigure(0,weight=1)
    page.grid_rowconfigure(1,weight=1)
    editor.controls={}
    def control(parent,name,text,command,**opts):
        widget=button(parent,text,command,**opts)
        editor.controls[name]=widget
        return widget
    card=frame(page,card=True)
    card.grid(row=0,column=0,sticky='ew',pady=(0,8))
    card.grid_columnconfigure(0,weight=1)
    head=frame(card)
    head.grid(row=0,column=0,sticky='ew',padx=12,pady=(10,6))
    label(head,'1  选择要管理的凭据',size='section_size',bold=True).pack(side='left')
    label(head,'同项目共用额度' if service=='gemini' else '不同账号对应不同接收人',size='small_size',muted=True).pack(side='right')
    table=frame(card,height=1)
    table.grid(row=1,column=0,sticky='ew',padx=10,pady=(0,10))
    table.grid_columnconfigure(0,weight=1)
    scale=card._get_widget_scaling()
    face=(family(window),-round(T['dialog_body_size']*scale))
    heading=(family(window),-round(T['dialog_label_size']*scale),'bold')
    style=ttk.Style(window)
    style.configure('Credential.Treeview',font=face,rowheight=max(round(T['dialog_row_height']*scale),tkfont.Font(window,font=face).metrics('linespace')+round(12*scale)),
        background=T['bg_card'],fieldbackground=T['bg_card'],foreground=T['text'],borderwidth=0)
    style.configure('Credential.Treeview.Heading',font=heading,padding=(round(8*scale),round(7*scale)),background=T['bg_input'],foreground=T['muted'])
    style.map('Credential.Treeview',background=[('selected',T['primary'])],foreground=[('selected',T['white'])])
    editor.tree=ttk.Treeview(table,columns=('name','scope','used','state'),show='headings',height=3,selectmode='browse',style='Credential.Treeview')
    for key,title in [('name','名称'),('scope','额度组'),('used','今日用量 / 剩余'),('state','状态')]:
        editor.tree.heading(key,text=title,anchor='w')
        editor.tree.column(key,width=20,minwidth=20,stretch=False,anchor='w')
    editor.tree.grid(row=0,column=0,sticky='ew')
    scrollbar=ctk.CTkScrollbar(table,command=editor.tree.yview,width=12,height=1,fg_color='transparent',button_color=T['border_input'])
    scrollbar.grid(row=0,column=1,sticky='ns')
    editor.tree.configure(yscrollcommand=scrollbar.set)
    def columns(event):
        width=max(80,event.width-4)
        for key,fraction in [('name',.19),('scope',.18),('used',.53),('state',.10)]:
            editor.tree.column(key,width=int(width*fraction))
    editor.tree.bind('<Configure>',columns)
    editor.tree.bind('<<TreeviewSelect>>',editor.select)
    outer=editor.form_scroll=ctk.CTkScrollableFrame(page,fg_color=T['bg_window'],corner_radius=0,
        scrollbar_button_color=T['border_input'],scrollbar_button_hover_color=T['hint'])
    outer.grid(row=1,column=0,sticky='nsew')
    outer.grid_columnconfigure(0,weight=1)
    form=frame(outer,card=True)
    form.grid(row=0,column=0,sticky='ew',padx=2,pady=(2,8))
    form.grid_columnconfigure((0,1),weight=1,uniform='credential_fields')
    label(form,'2  编辑凭据与额度',size='section_size',bold=True).grid(row=0,column=0,columnspan=2,sticky='w',padx=12,pady=(10,6))
    editor.vars={key:tk.StringVar(window) for key in ('label','key','group','limit','used','secret_key','maximum')}
    editor.field_entries={}
    specs=[('名称','label',1,0,1),('额度组','group',1,1,1),
        ('API Key' if service=='gemini' else '用户 Token','key',2,0,2),
        ('每日总额度 · 空白表示未知','limit',3,0,1),('官网今日已用 · 选填校准','used',3,1,1),
        ('单任务最多调用次数 · 含重试','maximum',4,0,2) if service=='gemini' else ('secretKey · 官网同步使用','secret_key',4,0,2)]
    for title,key,row,col,span in specs:
        cell=frame(form)
        cell.grid(row=row,column=col,columnspan=span,sticky='ew',padx=(12,12),pady=(0,8))
        cell.grid_columnconfigure(0,weight=1)
        captions=frame(cell)
        captions.grid(row=0,column=0,sticky='ew',pady=(0,4))
        label(captions,title,size='dialog_label_size',muted=True).pack(side='left')
        if key in ('key','secret_key'):
            command=(lambda:show_pushplus_setup(app)) if key=='secret_key' else (lambda u=GEMINI_KEYS_URL if service=='gemini' else PUSHPLUS_KEYS_URL:webbrowser.open(u))
            control(captions,'get_'+key,'设置方法 ↗' if key=='secret_key' else '获取 ↗',command,width=90 if key=='secret_key' else 60,height=24,
                fg_color='transparent',border_width=0,text_color=T['primary'],font=font('small_size')).pack(side='right')
        if key=='group':
            style.configure('Credential.TCombobox',padding=round(6*scale),arrowsize=round(14*scale),fieldbackground=T['bg_input'],background=T['bg_input'],foreground=T['text'])
            widget=ttk.Combobox(cell,textvariable=editor.vars[key],font=face,style='Credential.TCombobox',width=15)
            widget.bind('<<ComboboxSelected>>',editor.choose_group)
            editor.group_entry=widget
            Tooltip(widget,'同一项目选择已有额度组；独立项目选择“'+NEW_GROUP_OPTION+'”。')
        else:
            widget=entry(cell,editor.vars[key],font=font('dialog_body_size'),height=T['dialog_control_height'],show='•' if key in ('key','secret_key') else '')
        widget.grid(row=1,column=0,sticky='ew')
        editor.field_entries[key]=widget
    flags=frame(form)
    flags.grid(row=5,column=0,columnspan=2,sticky='ew',padx=12,pady=(0,12))
    editor.enabled,editor.auto_sync=tk.BooleanVar(window),tk.BooleanVar(window)
    for i,(text,var) in enumerate([('启用此凭据 · 按列表顺序使用',editor.enabled)]+([('保存 secretKey 后自动同步额度',editor.auto_sync)] if service=='pushplus' else [])):
        ctk.CTkCheckBox(flags,text=text,variable=var,font=font('dialog_label_size'),height=26,
            checkbox_width=18,checkbox_height=18,corner_radius=5,border_width=1,border_color=T['border_input'],
            fg_color=T['primary'],hover_color=T['primary_hover'],text_color=T['text']).grid(row=i,column=0,sticky='w',pady=3)
    editor.detail=tk.StringVar(window)
    details=frame(outer,card=True)
    details.grid(row=1,column=0,sticky='ew',padx=2,pady=(0,8))
    details.grid_columnconfigure(0,weight=1)
    label(details,'3  用量与填写说明',size='section_size',bold=True).grid(row=0,column=0,sticky='w',padx=12,pady=(10,6))
    wrapped(details,variable=editor.detail,muted=True).grid(row=1,column=0,sticky='ew',padx=12,pady=(0,10))
    notes=['① 同一项目或账号选择已有额度组；独立项目选择“＋ 新建独立额度组”，填写每日额度后保存。',
           '② 同组凭据共用计数，独立组才累计到总额度；用完后自动切换至后续可用组。',
           '③ Gemini Key 仅适用于 Gemini，其他模型服务的 Key 不能代填。' if service=='gemini' else '③ 不同 PushPlus 账号的 Token 对应不同接收账号，请核对接收人。']
    for row,text in enumerate(notes,2):
        wrapped(details,text).grid(row=row,column=0,sticky='ew',padx=12,pady=(0,8))
    bottom=frame(page)
    bottom.grid(row=2,column=0,sticky='ew',pady=(10,2))
    control(bottom,'save','保存当前凭据 / 校准',editor.save,primary=True,width=168,height=34).pack(side='left')
    control(bottom,'add','＋ 新增',editor.add,width=82,height=34).pack(side='left',padx=8)
    control(bottom,'remove','删除备用项',editor.remove,width=104,height=34).pack(side='left')
    control(bottom,'sync' if service=='pushplus' else 'official','同步官网额度' if service=='pushplus' else '打开模型额度',
            editor.sync if service=='pushplus' else lambda:webbrowser.open(GEMINI_LIMIT_URL),width=120,height=34).pack(side='right')
    editor.render()
    editor.tree.selection_set('primary')
    editor.load('primary')
