"""Responsive presentation layer. Existing App methods own every operation."""
from datetime import datetime, timedelta
import re
import tkinter as tk
from tkinter import ttk
import webbrowser
import customtkinter as ctk
from macos_theme import MACOS_THEME, family, font, frame, label, button, entry, search_entry, native_styles, PercentProgress, Tooltip, fitted_label, apply_window_icon
from motion_ui import (PhaseDots, QuotaMeter, TabUnderline, bind_clear_undo,
                       copy_log, motion_enabled, show_commands, toggle_focus)
from task_manager_ui import show_tasks

PAGES=['日常汇总','历史与人物查询','基础配置与初始化']

class PageStack(ctk.CTkFrame):
    def __init__(self,parent):
        super().__init__(parent,fg_color='transparent',corner_radius=0)
        self.grid_rowconfigure(0,weight=1)
        self.grid_columnconfigure(0,weight=1)
        self.pages={}
        self.current=None
        self.selector=None
        self.underline=None

    def select(self,page):
        name=page if isinstance(page,str) and page in self.pages else next(n for n,p in self.pages.items() if p==page)
        if self.current: self.pages[self.current].grid_remove()
        self.pages[name].grid(row=0,column=0,sticky='nsew')
        self.current=name
        if self.selector: self.selector.set(name)
        if self.underline: self.underline.select(name)

def action(app,parent,name,text,command,**kwargs):
    widget=button(parent,text,command,**kwargs)
    app.ui_controls[name]=widget
    return widget

def build_shell(app):
    from app_info import APP_NAME
    from ui_extras import build_usage_panel,show_quota_settings
    t=MACOS_THEME
    root=app.root
    ctk.set_appearance_mode('light')
    apply_window_icon(root)
    # Finish CTk's Windows titlebar setup while the window is still withdrawn.
    # Otherwise its first mainloop can hide a window deiconified before that setup.
    if isinstance(root,ctk.CTk): root.update()
    root.title(APP_NAME)
    root.geometry('980x660')
    root.minsize(840,540)
    if isinstance(root,ctk.CTk):
        from macos_dialogs import work_area
        left,top_edge,right,bottom=work_area(root)
        scale=root._get_window_scaling()
        x=max(left+12,left+(right-left-round(980*scale))//2)
        y=max(top_edge+12,top_edge+(bottom-top_edge-round(690*scale))//2)
        root.geometry(f'980x660{x:+d}{y:+d}')
    root.configure(**({'fg_color':t['bg_window']} if isinstance(root,ctk.CTk) else {'bg':t['bg_window']}))
    root.protocol('WM_DELETE_WINDOW',app.hide)
    for row in range(4): root.grid_rowconfigure(row,weight=1 if row==2 else 0)
    root.grid_columnconfigure(0,weight=1)
    app.ui_controls={}
    app.banner=tk.StringVar(root)
    app.status=tk.StringVar(root,value=app.cfg['last_run_status'])
    app.key_status=tk.StringVar(root,value=f'本机已保存数据库密钥：{len(app.secrets.get("db_keys",{}))} 个')
    top=app.top_bar=frame(root,height=t['top_height'])
    top.grid(row=0,column=0,sticky='ew',padx=16,pady=(6,0))
    top.grid_propagate(False)
    top.grid_columnconfigure(0,weight=1,minsize=260)
    top.grid_columnconfigure(1,weight=0)
    from version import VERSION
    label(top,f'微信聊天总结分析助手 v{VERSION}',size='title_size',bold=True,height=26).grid(row=0,column=0,sticky='w')
    badge=fitted_label(top,app.banner,width=260,size='tiny_size',height=22,
        fg_color=t['success_bg'],text_color=t['success'],corner_radius=t['pill_radius'],
        transform=lambda text:'  ● '+text.replace('已保存 ','').replace('  ·  ',' · ')+'  ')
    badge.grid(row=1,column=0,sticky='w',pady=(2,0))
    def update_badge(*_):
        enabled=app.cfg['enabled']
        badge.configure(fg_color=t['success_bg'] if enabled else t['bg_input'],text_color=t['success'] if enabled else t['muted'])
    app.banner.trace_add('write',update_badge)
    badges=frame(top)
    badges.grid(row=0,column=1,sticky='e')
    build_usage_panel(app,badges)
    app.generated_model=tk.StringVar(root,value='本次模型：尚未生成 · 额度按所选模型统计')
    fitted_label(top,app.generated_model,width=460,size='small_size',muted=True).grid(row=1,column=1,sticky='e',pady=(5,0))
    nav=app.nav_bar=frame(root,height=t['nav_height'])
    nav.grid(row=1,column=0,sticky='ew',padx=16,pady=(6,0))
    nav.grid_propagate(False)
    nav.grid_columnconfigure(0,weight=1)
    app.tabs=PageStack(root)
    app.tabs.grid(row=2,column=0,sticky='nsew',padx=16,pady=8)
    for name,attribute in zip(PAGES,('daily','history','config')):
        page=frame(app.tabs)
        app.tabs.pages[name]=page
        setattr(app,attribute,page)
    tabs_box=frame(nav,fg_color=t['nav_surface'],corner_radius=10)
    tabs_box.grid(row=0,column=0,pady=2,sticky='w')
    app.page_control=ctk.CTkSegmentedButton(tabs_box,values=PAGES,command=app.tabs.select,
        font=font('body_size',True),height=32,corner_radius=8,
        fg_color=t['nav_surface'],selected_color=t['white'],selected_hover_color=t['white'],
        unselected_color=t['nav_surface'],unselected_hover_color=t['bg_input'],text_color=t['text'])
    app.page_control.pack(padx=3,pady=(3,0),fill='x')
    app.tabs.selector=app.page_control
    app.tabs.underline=TabUnderline(tabs_box,app.page_control,PAGES)
    app.tabs.underline.pack(fill='x',padx=4,pady=(0,3))
    utilities=frame(nav)
    utilities.grid(row=0,column=1,sticky='e',padx=(8,0))
    action(app,utilities,'quota','额度管理',lambda:show_quota_settings(app),width=76,height=32).pack(side='left',padx=(0,6))
    app.toggle=action(app,utilities,'toggle','暂停定时计划',app.pause,width=108,height=32)
    app.toggle.pack(side='left',padx=(0,6))
    app.utility_commands={'hide':app.hide,'exit':app.exit}
    action(app,utilities,'tasks','任务管理',lambda:show_tasks(app),width=76,height=32).pack(side='left',padx=(0,6))
    for name,text,width in [('hide','隐藏',52),('exit','退出',52)]:
        action(app,utilities,name,text,app.utility_commands[name],width=width,height=32).pack(side='left',padx=(0,6))
    commands=action(app,utilities,'commands','快捷指令',lambda:show_commands(app),width=76,height=32)
    commands.pack(side='left')
    Tooltip(commands,'搜索页面和常用操作（Ctrl+K）')
    root.bind('<Control-k>',lambda event:show_commands(app,event) if event.widget.winfo_toplevel()==root else None,add='+')
    app.footer=footer=frame(root,fg_color=t['footer'],height=t['footer_height'])
    footer.grid(row=3,column=0,sticky='ew')
    footer.grid_propagate(False)
    footer.grid_columnconfigure(0,weight=1)
    frame(footer,fg_color=t['border_input'],height=1).grid(row=0,column=0,columnspan=5,sticky='ew')
    fitted_label(footer,app.status,width=130,size='tiny_size',height=24).grid(row=1,column=0,sticky='ew',padx=(12,6))
    fitted_label(footer,app.key_status,width=140,size='tiny_size',muted=True,height=24,
        transform=lambda text:text.replace('本机已保存数据库密钥：','本机密钥：')).grid(row=1,column=1,sticky='e',padx=4)
    fitted_label(footer,app.progress_text,width=170,size='tiny_size',height=24).grid(row=1,column=2,padx=6)
    app.progress_bar=PercentProgress(footer,app.progress_value,width=140,height=8,
        corner_radius=4,progress_color=t['progress_idle'],fg_color=t['border_card'])
    app.progress_bar.milestones=PhaseDots(footer,app.progress_value)
    app.progress_bar.milestones.grid(row=1,column=3,padx=(2,5))
    app.progress_bar.grid(row=1,column=4,padx=(2,12))
    native_styles(root,top._get_widget_scaling())
    app.build_daily()
    app.build_history()
    app.build_config()
    app.tabs.select('日常汇总')
    return app.tabs

def build_usage_badges(app,parent):
    from ui_extras import UsageTracker,refresh_usage
    t=MACOS_THEME
    app.usage=UsageTracker()
    app.usage_vars={service:tk.StringVar(parent) for service in ('gemini','pushplus')}
    app.current_usage=tk.StringVar(parent)
    app.usage_source=tk.StringVar(parent)
    app.quota_badges={}
    for service,title in [('gemini','Gemini'),('pushplus','PushPlus')]:
        value=tk.StringVar(parent)
        card=frame(parent,card=True,corner_radius=10)
        card.pack(side='left',padx=(6,0))
        pill=label(card,textvariable=value,size='small_size',height=22)
        pill.pack(fill='x',padx=6,pady=(2,0))
        meter=QuotaMeter(card)
        meter.pack(fill='x',padx=7,pady=(0,4))
        def update(*_,key=service,name=title,display=value,track=meter):
            text=app.usage_vars[key].get()
            match=re.search(r'(\d+)/(\d+).*?（([\d.]+)%）',text)
            display.set(f' {name}: {match[1]}/{match[2]} (余{match[3]}%) ' if match else f' {name}: 待配置/确认 ')
            used, limit = (int(match[1]), int(match[2])) if match else (0, 0)
            track.set(used,limit)
        app.usage_vars[service].trace_add('write',update)
        Tooltip(pill,lambda s=service:('统计模型：'+app.cfg['model']+'\n' if s=='gemini' else '')+app.usage_vars[s].get()+'\n'+app.current_usage.get()+'\n'+app.usage_source.get())
        app.quota_badges[service]=pill
    label(parent,' 本地 OCR/语音：免费 ',size='small_size',height=26,corner_radius=t['pill_radius'],fg_color=t['bg_input']).pack(side='left',padx=(8,0))
    refresh_usage(app)

def build_daily(app):
    t=MACOS_THEME
    page=app.daily
    page.grid_columnconfigure(0,weight=1)
    page.grid_rowconfigure(1,weight=1)
    controls=frame(page,card=True)
    controls.grid(row=0,column=0,sticky='ew',pady=(0,8))
    controls.grid_columnconfigure(0,weight=1)
    row=frame(controls)
    row.grid(row=0,column=0,sticky='ew',padx=12,pady=(10,6))
    label(row,'每日运行时间').pack(side='left',padx=(0,8))
    app.schedule=tk.StringVar(value=app.cfg['schedule_times'])
    from macos_dialogs import schedule_dialog, schedule_caption
    schedule_button=action(app,row,'schedule_times',schedule_caption(app.schedule.get()),
        lambda:schedule_dialog(app.root,app.schedule),width=140)
    schedule_button.pack(side='left')
    app.schedule.trace_add('write',lambda *_:schedule_button.configure(text=schedule_caption(app.schedule.get())))
    Tooltip(schedule_button,'选择小时和分钟，可添加多个每日时间点。')
    app.ocr=tk.BooleanVar(value=app.cfg.get('enable_image_ocr',True))
    app.asr=tk.BooleanVar(value=app.cfg.get('enable_voice_asr',True))
    for variable,title,name in [(app.ocr,'本地图片 OCR','ocr'),(app.asr,'本地语音转写','asr')]:
        checkbox=ctk.CTkCheckBox(row,text=title,variable=variable,font=font(),width=116,
            checkbox_width=18,checkbox_height=18,corner_radius=5,border_width=1,
            fg_color=t['primary'],hover_color=t['primary_hover'],border_color=t['border_input'],text_color=t['text'])
        checkbox.pack(side='left',padx=(12,0))
        app.ui_controls[name]=checkbox
    action(app,row,'save_daily','保存日常设置',app.save_daily,primary=True,width=112).pack(side='right')
    row=frame(controls)
    row.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,10))
    row.grid_columnconfigure(1,weight=1)
    label(row,'搜索群聊').grid(row=0,column=0,padx=(0,10))
    app.search=tk.StringVar()
    app.group_search_task=None
    app.search.trace_add('write',lambda *_:queue_group_search(app))
    app.search_entry=search_box(app,row,app.search,'search_daily',app.draw_groups)
    app.search_entry.master.grid(row=0,column=1,sticky='ew')
    clear=action(app,row,'clear_daily','清空',lambda:None,width=48)
    clear.grid(row=0,column=2,padx=6)
    bind_clear_undo(app.search_entry,app.search,clear)
    app.group_count=tk.StringVar(value='请刷新群列表')
    fitted_label(row,app.group_count,width=160,size='small_size',muted=True,
        transform=lambda text:text.split('；')[0]).grid(row=0,column=3,padx=4)
    action(app,row,'refresh_groups','刷新群列表',app.refresh_groups,width=96).grid(row=0,column=4,padx=(4,0))
    card=frame(page,card=True)
    card.grid(row=1,column=0,sticky='nsew')
    card.grid_rowconfigure(1,weight=1)
    card.grid_columnconfigure(0,weight=1)
    heading=frame(card)
    heading.grid(row=0,column=0,sticky='ew',padx=14,pady=(8,4))
    label(heading,'选择汇总群聊',size='section_size',bold=True).pack(side='left')
    label(heading,'勾选纳入日报 · 取消勾选后保存即可移除',size='small_size',muted=True).pack(side='right')
    content=frame(card)
    content.grid(row=1,column=0,sticky='nsew',padx=8)
    content.grid_columnconfigure(0,weight=1)
    content.grid_rowconfigure(0,weight=1)
    scale=content._get_widget_scaling()
    style=ttk.Style(app.root)
    style.configure('Groups.Treeview',font=(family(app.root),-round(t['body_size']*scale)),
        rowheight=round(30*scale),borderwidth=0,background=t['bg_card'],fieldbackground=t['bg_card'])
    style.layout('Groups.Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    canvas=app.group_canvas=ttk.Treeview(content,show='tree',selectmode='none',style='Groups.Treeview')
    canvas.column('#0',width=400,minwidth=100,stretch=True)
    canvas.grid(row=0,column=0,sticky='nsew')
    scrollbar=app.group_scrollbar=ctk.CTkScrollbar(content,orientation='vertical',command=canvas.yview,
        fg_color=t['bg_card'],button_color=t['border_input'],button_hover_color=t['hint'],width=12)
    scrollbar.grid(row=0,column=1,sticky='ns')
    def toggle_group(event=None):
        rid=canvas.identify_row(event.y) if event is not None and event.type==tk.EventType.ButtonPress else canvas.focus()
        if rid in app.selected and rid in app.groups:
            canvas.focus_set()
            canvas.focus(rid)
            value=app.selected[rid]
            value.set(not value.get())
            canvas.item(rid,image=app.root._group_check_icons[int(value.get())])
            refresh_selection(app)
        return 'break'
    canvas.bind('<Button-1>',toggle_group)
    canvas.bind('<space>',toggle_group)
    canvas.bind('<Double-1>',lambda _: 'break')
    # Stop before the native class/root bindings: each wheel event scrolls once.
    canvas.bind('<MouseWheel>',app.scroll_groups)
    canvas.configure(yscrollcommand=scrollbar.set)
    app.scroll_targets.append((canvas,scrollbar))
    app.root.bind('<MouseWheel>',app.scroll_groups,add='+')
    actions=frame(card)
    actions.grid(row=2,column=0,sticky='ew',padx=12,pady=8)
    app.focus_button=action(app,actions,'focus_mode','专注',lambda:toggle_focus(app),width=76)
    app.focus_button.pack(side='left',padx=(0,8))
    Tooltip(app.focus_button,'收起顶部概览，留出更多空间给群列表')
    app.selection_count=label(actions,'已勾选 0 个群',size='small_size',fg_color=t['selected_bg'],
        text_color=t['selected_text'],corner_radius=t['pill_radius'])
    app.selection_count.pack(side='left',ipadx=8)
    app.group_count.trace_add('write',lambda *_:refresh_selection(app))
    app.daily_button=action(app,actions,'daily_job','立即生成过去 24 小时日报',app.daily_job,primary=True,width=208)
    app.daily_button.pack(side='right')

def build_history(app):
    t=MACOS_THEME
    page=app.history
    page.grid_columnconfigure(0,weight=1)
    page.grid_rowconfigure(1,weight=1)
    card=frame(page,card=True)
    card.grid(row=0,column=0,sticky='ew',pady=(0,8))
    card.grid_columnconfigure(0,weight=1)
    heading=frame(card)
    heading.grid(row=0,column=0,sticky='ew',padx=12,pady=(8,4))
    label(heading,'历史与人物查询',size='section_size',bold=True).pack(side='left')
    app.history_count=tk.StringVar(value='输入群名、备注或群标识')
    row=frame(card)
    row.grid(row=1,column=0,sticky='ew',padx=12,pady=(0,8))
    row.grid_columnconfigure(1,weight=1)
    row.grid_columnconfigure(4,weight=1)
    label(row,'搜索群聊').grid(row=0,column=0,padx=(0,8))
    app.history_search=tk.StringVar()
    app.history_search.trace_add('write',lambda *_:app.filter_history_groups())
    app.history_search_entry=search_box(app,row,app.history_search,'search_history',app.filter_history_groups)
    app.history_search_entry.master.grid(row=0,column=1,sticky='ew')
    clear=action(app,row,'clear_history','清空',lambda:None,width=44)
    clear.grid(row=0,column=2,padx=6)
    bind_clear_undo(app.history_search_entry,app.history_search,clear)
    label(row,'目标群聊').grid(row=0,column=3,padx=(6,8))
    app.group_choice=ttk.Combobox(row,state='readonly',width=20,style='Mac.TCombobox',
        font=(family(app.root),-round(t['body_size']*row._get_widget_scaling())))
    app.group_choice.grid(row=0,column=4,sticky='ew')
    app.history_hint=fitted_label(row,app.history_count,width=180,size='small_size',text_color=t['attention'])
    app.history_hint.grid(row=1,column=1,columnspan=2,sticky='ew',pady=(4,0))
    app.history_hint_job=None
    app.group_choice.bind('<<ComboboxSelected>>',lambda _:history_selected(app))
    row=frame(card)
    row.grid(row=2,column=0,sticky='ew',padx=12,pady=(0,8))
    for col in range(3): row.grid_columnconfigure(col,weight=1,uniform='filters')
    app.start=tk.StringVar(value=(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d 00:00'))
    app.end=tk.StringVar(value=datetime.now().strftime('%Y-%m-%d %H:%M'))
    app.person=tk.StringVar()
    for col,(title,var,placeholder) in enumerate([('起始时间',app.start,'YYYY-MM-DD HH:MM'),('结束时间',app.end,'YYYY-MM-DD HH:MM'),('发言人筛选',app.person,'昵称/备注/微信标识；留空提取全群')]):
        cell=frame(row)
        cell.grid(row=0,column=col,sticky='ew',padx=(0,8 if col<2 else 0))
        cell.grid_columnconfigure(0,weight=1)
        label(cell,title,size='small_size',muted=True).grid(row=0,column=0,sticky='w',pady=(0,3))
        from history_selectors import calendar_dialog, participant_dialog
        if col < 2:
            widget=button(cell, var.get(), lambda v=var,t=title:calendar_dialog(app.root,v,t), width=220, textvariable=var)
            widget.grid(row=1,column=0,sticky='ew')
        else:
            widget=entry(cell,var,width=120,placeholder_text=placeholder)
            widget.grid(row=1,column=0,sticky='ew')
            button(cell,'选择',lambda:participant_dialog(app),width=56).grid(row=1,column=1,padx=(4,0))
        Tooltip(widget,'点击选择年月日和时分；结束时间包含该分钟。' if col<2 else '可搜索历史发言人，选择后按微信标识精确筛选；留空提取全群。')
    row=frame(card)
    row.grid(row=3,column=0,sticky='ew',padx=12,pady=(0,10))
    quick=frame(row)
    quick.pack(side='left')
    for text,years,months in [('近7天',0,0),('近1个月',0,1),('近1年',1,0),('近3年',3,0),('近5年',5,0),('近10年',10,0)]:
        action(app,quick,'quick_'+text,text,lambda y=years,m=months:app.quick(y,m),width=48 if not months else 59,height=28,font=font('small_size')).pack(side='left',padx=(0,4))
    actions=frame(row)
    actions.pack(side='right')
    for name,text,command,width,primary in [
        ('open_exports','打开导出目录',app.open_exports,90,False),
        ('export_only','仅导出记录',lambda:app.custom(False),80,False),
        ('export_summary','导出 + Gemini 复盘 + 手机推送',lambda:app.custom(True),213,True)]:
        action(app,actions,name,text,command,width=width,height=28,primary=primary,font=font('small_size')).pack(side='left',padx=(4,0))
    card=frame(page,card=True)
    card.grid(row=1,column=0,sticky='nsew')
    card.grid_columnconfigure(0,weight=1)
    card.grid_rowconfigure(1,weight=1)
    heading=frame(card)
    heading.grid(row=0,column=0,sticky='ew',padx=14,pady=(8,4))
    label(heading,'运行日志',size='section_size',bold=True).pack(side='left')
    copy=action(app,heading,'copy_log','复制日志',lambda:copy_log(app,copy),width=92,height=26)
    copy.pack(side='right')
    content=frame(card,fg_color=t['log'],corner_radius=8)
    content.grid(row=1,column=0,sticky='nsew',padx=10,pady=(0,10))
    content.grid_columnconfigure(0,weight=1)
    content.grid_rowconfigure(0,weight=1)
    app.log=tk.Text(content,wrap='word',font=(family(app.root),-round(t['body_size']*card._get_widget_scaling())),
        bg=t['log'],fg=t['text'],relief='flat',borderwidth=0,highlightthickness=0,padx=10,pady=8,height=4,width=10)
    app.log.grid(row=0,column=0,sticky='nsew',padx=(4,0),pady=4)
    scroll=ctk.CTkScrollbar(content,command=app.log.yview,fg_color=t['log'],button_color=t['border_input'],width=12)
    scroll.grid(row=0,column=1,sticky='ns',padx=(0,4),pady=4)
    app.log.configure(yscrollcommand=scroll.set)

def build_config(app):
    from jobs import export_directory
    from credential_ui import show_credentials,show_image_key_help,GEMINI_KEYS_URL,PUSHPLUS_KEYS_URL
    from ui_extras import show_help,show_author
    t=MACOS_THEME
    page=app.config
    page.grid_rowconfigure(0,weight=1)
    page.grid_columnconfigure(0,weight=1)
    outer=app.config_scroll=ctk.CTkScrollableFrame(page,fg_color=t['bg_window'],corner_radius=0,
        scrollbar_button_color=t['border_input'],scrollbar_button_hover_color=t['hint'])
    outer.grid(row=0,column=0,sticky='nsew')
    outer.grid_columnconfigure(0,weight=1)
    core=frame(outer,card=True)
    core.grid(row=0,column=0,sticky='ew',padx=2,pady=(10,6))
    core.grid_columnconfigure(1,weight=1)
    label(core,'接口与路径配置',size='section_size',bold=True).grid(row=0,column=0,columnspan=3,sticky='w',padx=12,pady=(8,4))
    app.fields={}
    app.field_entries={}
    specs=[('微信 4.x 账号目录','wechat_dir',False),('Gemini API Key','gemini_api_key',True),
        ('PushPlus Token','pushplus_token',True),('代理地址','proxy_url',False),('Gemini 模型名称','model',False),
        ('V2 图片密钥（必需）','image_key_hex',True),('导出文件保存目录','export_dir',False)]
    for row,(text,key,secret) in enumerate(specs,1):
        caption=frame(core)
        caption.grid(row=row,column=0,sticky='e',padx=(12,8),pady=1)
        label(caption,text,size='small_size').pack(side='left')
        if key in ('gemini_api_key','pushplus_token','image_key_hex'):
            command=(lambda:show_image_key_help(app)) if key=='image_key_hex' else (lambda url=GEMINI_KEYS_URL if key=='gemini_api_key' else PUSHPLUS_KEYS_URL:webbrowser.open(url))
            action(app,caption,'get_'+key,'说明 ↗' if key=='image_key_hex' else '获取 ↗',command,
                width=48,height=24,font=font('tiny_size'),fg_color='transparent',text_color=t['primary'],border_width=0).pack(side='left',padx=(3,0))
        value=str(export_directory(app.cfg)) if key=='export_dir' else (app.secrets if secret else app.cfg).get(key,'')
        app.fields[key]=var=tk.StringVar(value=value)
        if key=='model':
            from model_catalog import FREE_TEXT_MODELS
            widget=ctk.CTkComboBox(core,variable=var,values=list(FREE_TEXT_MODELS),height=28,width=150,
                font=font(),dropdown_font=font(),fg_color=t['bg_input'],border_color=t['border_input'],border_width=1,
                button_color=t['border_card'],button_hover_color=t['secondary_hover'],text_color=t['text'],
                dropdown_fg_color=t['bg_card'],dropdown_text_color=t['text'])
            Tooltip(widget,'官方列有免费层（2026-11-18 核实）；额度按项目/模型分别统计。限流时尝试 3.8 Flash → 3.5 Flash-Lite，跳过重复型号。')
        else:
            widget=entry(core,var,width=150,height=28,show='•' if secret else '')
        app.field_entries[key]=widget
        widget.grid(row=row,column=1,sticky='ew',padx=(0,8),pady=1)
        if key in ('gemini_api_key','pushplus_token'):
            service='gemini' if key=='gemini_api_key' else 'pushplus'
            action(app,core,'manage_'+service,'＋ 管理',lambda s=service:show_credentials(app,s),width=80,height=28).grid(row=row,column=2,padx=(0,12),pady=1)
        elif key=='export_dir':
            action(app,core,'choose_export_dir','选择目录',app.choose_export_dir,width=80,height=28).grid(row=row,column=2,padx=(0,12),pady=1)
        elif key=='wechat_dir':
            action(app,core,'choose_wechat_dir','选择目录',app.choose_wechat_dir,width=80,height=28).grid(row=row,column=2,padx=(0,12),pady=1)
    controls=frame(core)
    controls.grid(row=8,column=0,columnspan=3,sticky='ew',padx=12,pady=(6,8))
    label(controls,'凭据在本机加密保存 · 两个服务均支持备用凭据',size='tiny_size',muted=True).pack(side='left')
    action(app,controls,'save_base','保存参数',app.save_base,primary=True,width=100,height=28).pack(side='right')
    tools=frame(outer,card=True)
    tools.grid(row=1,column=0,sticky='ew',padx=2,pady=(0,8))
    from version import VERSION
    label(tools,f'初始化与维护 · v{VERSION}',size='section_size',bold=True).pack(anchor='w',padx=12,pady=(8,4))
    row=frame(tools)
    row.pack(fill='x',padx=12,pady=(0,10))
    for name,text,command,width in [
        ('open_wizard','提取数据库密钥',app.open_wizard,108),
        ('check_export_sources','重新校验分库',app.check_export_sources,104),
        ('open_image_wizard','初始化图片密钥',app.open_image_wizard,108),
        ('test_push','测试手机推送',app.test_push,88),
        ('help','使用说明',lambda:show_help(app),64),
        ('author','联系作者',lambda:show_author(app),64),
        ('check_updates','检查更新',app.check_updates,76),
        ('optional_components','图片/语音组件',app.optional_components,102)]:
        action(app,row,name,text,command,width=width,height=28,font=font('small_size')).pack(side='left',padx=(0,6))
    backup_row=frame(tools)
    backup_row.pack(fill='x',padx=12,pady=(0,10))
    action(app,backup_row,'import_export_keys','导入已有凭据备份',app.import_export_keys,
           width=132,height=28,font=font('small_size')).pack(side='left')


def queue_group_search(app):
    if app.group_search_task is not None:
        app.root.after_cancel(app.group_search_task)
    app.group_search_task=app.root.after(140,app.draw_groups)


def refresh_selection(app):
    count=sum(var.get() for rid,var in app.selected.items() if rid in app.groups)
    app.selection_count.configure(text=f'已勾选 {count} 个群')

def search_box(app,parent,variable,name,callback):
    box=frame(parent,fg_color=MACOS_THEME['bg_input'],corner_radius=8,border_width=1,border_color=MACOS_THEME['border_input'])
    box.grid_columnconfigure(0,weight=1)
    field=search_entry(box,variable,width=100,border_width=0)
    field.grid(row=0,column=0,sticky='ew',padx=(2,0),pady=1)
    action(app,box,name,'🔍',callback,width=30,height=28,border_width=0,text_color=MACOS_THEME['primary']).grid(row=0,column=1,padx=(0,3))
    field.bind('<Return>',lambda _:callback())
    Tooltip(field,'输入即筛选；也可点击放大镜或按 Enter。')
    return field


def history_attention(app,flash=False):
    if app.history_hint_job is not None:
        app.root.after_cancel(app.history_hint_job)
        app.history_hint_job=None
    def pulse(index=0):
        app.history_hint.configure(text_color=MACOS_THEME['attention_soft'] if index%2 else MACOS_THEME['attention'])
        app.history_hint_job=app.root.after(600,lambda:pulse(index+1)) if index<6 else None
    if flash and motion_enabled(app.root):pulse()
    else:app.history_hint.configure(text_color=MACOS_THEME['attention'])


def history_selected(app):
    history_attention(app)
    count=len(app.group_choice['values'])
    app.history_count.set(f'匹配 {count} 个群，已选择右侧目标群聊')
