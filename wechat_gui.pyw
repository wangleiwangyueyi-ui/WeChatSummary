"""Windows desktop entry point. Daily execution never imports the bootstrap scanner."""
import copy
import ctypes
from datetime import datetime, timedelta
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import customtkinter as ctk
from macos_theme import MACOS_THEME
import macos_ui
from tkinter import ttk, messagebox, filedialog
from secure_store import BASE, load_config, save_config, load_secrets, save_secrets, safe_error, load_database_key_backup
from db_reader import contacts, latest_update, verify_database_keys
from group_search import group_catalog, matching_groups, month_before
from jobs import times, due_slots, extract, push, Cancelled, export_directory, plan_text
from scheduler import Scheduler
from app_info import APP_NAME, TAGLINE
from ui_extras import build_usage_panel, refresh_usage, show_quota_settings, show_help, show_author
from credentials import accounts, bucket
from credential_ui import show_credentials, show_image_key_help, GEMINI_KEYS_URL, PUSHPLUS_KEYS_URL
from quota_service import sync_pushplus
from task_control import check_cancel
from task_manager_ui import TASK_NAMES, show_tasks
from app_paths import APP_DIR
import webbrowser

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.secrets = load_secrets()
        self.offline_export_keys = None
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.tray = None
        self.scheduler = Scheduler()
        self.active_schedule = None
        self.startup_ready = time.monotonic()+45
        self.next_wechat_check = 0
        self.wechat_running = False
        self.closing = False
        self.show_event = None
        self.groups = {}
        self.group_aliases = {}
        self.selected = {}
        self.group_layout_task = None
        self.scroll_targets = []
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_text = tk.StringVar(value='等待任务')
        self.task_kind = None
        self.task_started = None
        self.last_task = None
        self.discard_on_cancel = False
        self.progress_stage = '等待任务'
        self.next_usage_refresh = 0
        self.next_quota_sync = time.monotonic()+15
        self.next_health = time.monotonic()+30
        tabs = macos_ui.build_shell(self)
        self.refresh_banner()
        self.root.after(150,self.poll)
        self.root.after(1000,self.tick)
        if self.secrets.get('db_keys'):
            self.root.after(300,self.refresh_groups)
        else:
            tabs.select(self.config)

    def build_daily(self):
        macos_ui.build_daily(self)

    def build_history(self):
        macos_ui.build_history(self)

    def build_config(self):
        macos_ui.build_config(self)

    def choose_export_dir(self):
        selected = filedialog.askdirectory(parent=self.root,title='选择聊天记录和复盘保存目录',
                                          initialdir=self.fields['export_dir'].get(),mustexist=False)
        if selected:
            self.fields['export_dir'].set(selected)

    def choose_wechat_dir(self):
        selected = filedialog.askdirectory(parent=self.root,title='选择包含 db_storage 的微信账号文件夹')
        if selected:
            self.fields['wechat_dir'].set(selected)

    def check_updates(self):
        from update_ui import show_updates
        show_updates(self)

    def optional_components(self):
        from update_ui import show_updates
        show_updates(self, components=True)

    def refresh_banner(self):
        enabled = self.cfg['enabled']
        count = len(self.cfg['selected_groups'])
        self.toggle.configure(text='暂停定时计划' if enabled else '恢复定时计划' if count else '启用定时计划')
        if count:
            state = '定时计划已启用' if enabled else '定时计划已暂停'
            self.banner.set(f'{state}  ·  {count} 个群  ·  {self.cfg["schedule_times"]}')
        else:
            self.banner.set('未设置定时计划')

    def pause(self):
        enabling = not self.cfg['enabled']
        if enabling and (not self.cfg['selected_groups'] or not self.secrets.get('db_keys') or not any(a.get('enabled',True) for a in accounts(self.cfg,self.secrets,'gemini'))):
            messagebox.showinfo('尚未配置完成','请先完成数据库初始化、填写 Gemini Key，并选择群聊保存。')
            return
        self.cfg['enabled'] = enabling
        if enabling:
            self.scheduler.activate(datetime.now())
        save_config(self.cfg)
        self.refresh_banner()

    def revoke_daily_plan(self):
        """Remove the saved recurring plan and cancel an active scheduled run."""
        previous_groups = self.cfg['selected_groups']
        cfg = dict(self.cfg, enabled=False, selected_groups={})
        previous_state = self.scheduler.state
        self.scheduler.clear_plan()
        try:
            save_config(cfg)
        except OSError:
            self.scheduler.replace_state(previous_state)
            raise

        self.cfg = cfg
        if self.task_kind == 'scheduled' and self.busy:
            self.cancel_task()
        for group_id in previous_groups:
            if group_id in self.selected:
                self.selected[group_id].set(False)
        macos_ui.refresh_selection(self)
        self.refresh_banner()
        self.status.set('定时计划已撤销，正在停止本轮定时汇总' if self.busy and self.task_kind == 'scheduled'
                        else '定时计划已撤销')

    def save_daily(self):
        try:
            self.cfg['schedule_times'] = ', '.join(times(self.schedule.get()))
            self.cfg['selected_groups'] = {rid:self.groups[rid] for rid,var in self.selected.items() if var.get() and rid in self.groups}
            self.cfg['enable_image_ocr'] = self.ocr.get()
            self.cfg['enable_voice_asr'] = self.asr.get()
            self.schedule.set(self.cfg['schedule_times'])
            save_config(self.cfg)
            self.refresh_banner()
            self.status.set('日常设置已保存')
        except Exception as exc:
            messagebox.showerror('保存失败',safe_error(exc,self.secrets))

    def save_base(self):
        if self.busy:
            messagebox.showinfo('任务运行中','请等待任务结束再修改基础参数。')
            return
        try:
            newcfg, secret = copy.deepcopy(self.cfg), load_secrets()
            for key,var in self.fields.items():
                (secret if key in ('gemini_api_key','pushplus_token','image_key_hex') else newcfg)[key] = var.get().strip()
            if secret.get('image_key_hex'):
                if len(bytes.fromhex(secret['image_key_hex'])) != 16:
                    raise ValueError('V2 图片密钥必须是 32 位十六进制字符串')
            if not newcfg['model']:
                raise ValueError('模型名称不能为空')
            folder = export_directory(newcfg)
            folder.mkdir(parents=True,exist_ok=True)
            import tempfile
            with tempfile.TemporaryFile(dir=folder):
                pass
            save_secrets(secret)
            save_config(newcfg)
            if newcfg['wechat_dir'] != self.cfg['wechat_dir']:
                self.offline_export_keys = None
            self.cfg,self.secrets = newcfg,secret
            self.status.set('基础参数已保存。可点击“刷新群列表”验证。')
            self.key_status.set(f'本机已保存数据库密钥：{len(secret.get("db_keys",{}))} 个')
            refresh_usage(self)
        except Exception as exc:
            messagebox.showerror('保存失败',safe_error(exc,self.secrets))

    def open_wizard(self):
        self.import_export_keys()

    def import_export_keys(self):
        path = filedialog.askopenfilename(parent=self.root, title='选择本机的 WeChatSummary 凭据备份',
                                         filetypes=[('WeChatSummary 凭据备份', '*.dpapi')])
        if not path:
            return
        self.offline_export_keys = None
        try:
            backup = load_database_key_backup(path)
            self.offline_export_keys = verify_database_keys(self.cfg, self.secrets.get('db_keys', {}), backup)
        except (OSError, ValueError) as exc:
            messagebox.showerror('凭据验证失败', safe_error(exc, self.secrets), parent=self.root)
            return
        messagebox.showinfo('数据库凭据已验证',
                            '请选择群聊与时间范围，再点击“仅导出记录”。凭据将用于下一次本地导出，并随任务结束清除。',
                            parent=self.root)

    def check_export_sources(self):
        keys = self.offline_export_keys or self.secrets.get('db_keys', {})
        try:
            verify_database_keys(self.cfg, keys)
        except (OSError, ValueError) as exc:
            messagebox.showerror('分库校验未通过', safe_error(exc, self.secrets), parent=self.root)
            return
        messagebox.showinfo('分库校验通过', '联系人数据库及全部消息分库均通过凭据校验。可以尝试仅导出记录。',
                            parent=self.root)

    def open_image_wizard(self):
        if not (APP_DIR/'image_key_once.py').is_file():
            messagebox.showinfo('图片初始化已完成','本机的一次性图片提取组件已清理；当前密钥可继续使用。重新初始化请联系作者。')
            return
        subprocess.Popen([sys.executable,str(APP_DIR/'initialize_images.pyw')],cwd=APP_DIR)

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if not self.busy:
            self.secrets = load_secrets()
            self.fields['image_key_hex'].set(self.secrets.get('image_key_hex',''))
            self.key_status.set(f'数据库密钥：{len(self.secrets.get("db_keys",{}))} 个；图片密钥：'+('已保存' if self.secrets.get('image_key_hex') else '尚未初始化'))

    def hide(self):
        if self.tray is None:
            self.status.set('托盘尚未就绪，暂时最小化；可从任务栏恢复')
            self.root.iconify()
        else:
            self.root.withdraw()

    def start_tray(self):
        import pystray
        from PIL import Image, ImageDraw
        picture = Image.new('RGBA',(64,64),(0,0,0,0))
        draw = ImageDraw.Draw(picture)
        draw.rounded_rectangle((4,5,60,53),radius=14,fill='#23885b')
        draw.polygon([(15,48),(14,61),(30,50)],fill='#23885b')
        for y in (19,29,39):
            draw.rounded_rectangle((17,y,47,y+4),radius=2,fill='white')
        def event(name):
            return lambda icon,item:self.events.put((name,None))
        menu = pystray.Menu(pystray.MenuItem('打开设置',event('ui_show'),default=True),
            pystray.MenuItem('任务管理',event('ui_tasks')),
            pystray.MenuItem(lambda item:'暂停自动运行' if self.cfg['enabled'] else '恢复自动运行',event('ui_pause')),
            pystray.MenuItem('退出软件',event('ui_exit')))
        self.tray = pystray.Icon('WeChatSummary',picture,APP_NAME,menu)
        self.tray.run_detached()

    def launch(self, task, kind='job'):
        if self.busy:
            self.status.set('已有任务运行，请等待或取消当前任务')
            return False
        self.busy = True
        self.discard_on_cancel = False
        self.progress_bar.set_state('running')
        self.task_kind = kind
        self.task_started = time.monotonic()
        self.progress_value.set(0)
        self.progress_stage = {'job':'本地预检','export':'本地导出','scheduled':'定时任务本地预检','groups':'刷新群列表',
                               'health':'检查运行状态','push':'测试手机推送','quota':'查询 API 额度'}.get(kind,'正在执行')
        self.progress_text.set(self.progress_stage+' · 约 0%')
        determinate = kind in ('job','export','scheduled')
        self.progress_bar.configure(mode='determinate' if determinate else 'indeterminate')
        if not determinate:
            self.progress_bar.start(12)
        self.cancel.clear()
        self.status.set('正在执行…')
        def run():
            try:
                result = task()
                check_cancel(self.cancel)
                self.events.put(('done',(kind,result)))
            except Cancelled as exc:
                self.events.put(('cancel',str(exc)))
            except Exception as exc:
                if self.cancel.is_set():
                    self.events.put(('cancel','任务已取消；当前请求已结束，未继续重试或推送'))
                    return
                error = safe_error(exc,self.secrets)
                if kind not in ('export','health','quota') and accounts(self.cfg,self.secrets,'pushplus'):
                    try:
                        push(self.secrets.get('pushplus_token',''),'⚠️ 运行异常提醒',error,self.cfg,self.progress,self.cancel,secrets=self.secrets)
                        self.events.put(('error_sent',error))
                        return
                    except Cancelled as stopped:
                        self.events.put(('cancel',str(stopped)))
                        return
                    except Exception:
                        error += '；异常推送未成功，将在自动运行启用时重试'
                self.events.put(('error',error))
        threading.Thread(target=run,daemon=True).start()
        return True

    def cancel_task(self, discard=True):
        if not self.busy:
            self.status.set('当前没有正在运行的任务')
            return
        self.discard_on_cancel = self.discard_on_cancel or discard
        if self.cancel.is_set():
            return
        self.cancel.set()
        self.status.set('正在取消：停止后续处理、重试和推送；等待当前本地操作或网络请求返回')
        self.progress_text.set('正在取消 · 等待当前操作结束')
        self.progress_bar.set_state('running')

    def progress(self, value):
        self.events.put(('progress',value))

    def approve_plan(self, plan):
        ready,decision = threading.Event(),{}
        self.events.put(('plan',(plan,ready,decision)))
        while not ready.wait(.2):
            if self.cancel.is_set() or self.closing:
                return False
        return decision.get('approved',False) and not self.cancel.is_set()

    def refresh_groups(self):
        self.secrets = load_secrets()
        cfg,secret = copy.deepcopy(self.cfg),copy.deepcopy(self.secrets)
        self.launch(lambda:group_catalog(contacts(cfg,secret,self.cancel)), 'groups')

    def set_groups(self, catalog):
        self.groups, self.group_aliases = catalog
        for rid in self.groups:
            if rid not in self.selected:
                self.selected[rid] = tk.BooleanVar(value=rid in self.cfg['selected_groups'])
        self.draw_groups()
        self.filter_history_groups()

    def group_label(self, rid, name):
        other_names = [value for value in self.group_aliases.get(rid, []) if value != name]
        return name + ('（群名：' + ' / '.join(other_names) + '）' if other_names else '')

    def draw_groups(self):
        if self.group_search_task is not None:
            self.root.after_cancel(self.group_search_task)
            self.group_search_task = None
        matches = matching_groups(self.groups,self.group_aliases,self.search.get())
        visible_ids = {rid for rid, _ in matches}
        for rid in self.group_rows.keys() - visible_ids:
            self.group_rows.pop(rid).destroy()
        if matches and self.group_placeholder is not None:
            self.group_placeholder.destroy()
            self.group_placeholder = None
        rows = []
        for rid, name in matches:
            text = f'{self.group_label(rid,name)}  ({rid})'
            row = self.group_rows.get(rid)
            if row is None:
                row = self.group_rows[rid] = macos_ui.group_row(self,text,self.selected[rid])
                row.pack(fill='x',padx=4,pady=4)
            elif row.cget('text') != text:
                row.configure(text=text)
            rows.append(row)
        if rows != self.group_frame.pack_slaves():
            for index in range(len(rows)-2, -1, -1):
                rows[index].pack_configure(before=rows[index+1])
        self.group_count.set(f'显示 {len(matches)} / {len(self.groups)} 个群；搜索不会取消已勾选的群')
        if not matches:
            text = '没有匹配的群，请换个关键词或刷新群列表。' if self.groups else '尚未读取群聊，请点击“刷新群列表”。'
            if self.group_placeholder is None:
                self.group_placeholder = macos_ui.empty_groups(self,text)
            else:
                self.group_placeholder.configure(text=text)
        # Recompute after Tk has laid out the shorter list, then reset the old scroll position.
        if self.group_layout_task is not None:
            self.root.after_cancel(self.group_layout_task)
        self.group_layout_task = self.root.after_idle(self.reset_group_scroll)

    def reset_group_scroll(self):
        self.group_layout_task = None
        self.group_canvas.configure(scrollregion=self.group_canvas.bbox('all'))
        self.group_canvas.yview_moveto(0)

    def scroll_groups(self, event):
        target = self.root.winfo_containing(event.x_root,event.y_root)
        while target is not None:
            for canvas,scrollbar in self.scroll_targets:
                if target in (canvas,scrollbar):
                    if event.delta:
                        steps = max(1,abs(int(event.delta))//120)
                        canvas.yview_scroll(-3*steps if event.delta > 0 else 3*steps,'units')
                    return 'break'
            target = getattr(target,'master',None)

    def filter_history_groups(self):
        matches = matching_groups(self.groups,self.group_aliases,self.history_search.get())
        labels = [self.group_label(rid,name)+' | '+rid for rid,name in matches]
        previous = self.group_choice.get()
        self.group_choice.configure(values=labels)
        if previous not in labels:
            self.group_choice.set(labels[0] if len(labels) == 1 else '')
        if not labels:
            self.history_count.set('无匹配，请修改关键词或刷新群列表')
        elif len(labels) == 1:
            self.history_count.set('匹配 1 个群，已选中')
        else:
            self.history_count.set(f'匹配 {len(labels)} 个群，请从右侧“目标群聊”选择 →')
        macos_ui.history_attention(self,flash=bool(self.history_search.get().strip()) and len(labels)>1)

    def quick(self, years=0, months=0):
        end = datetime.now()
        if months:
            start = month_before(end)
        elif years:
            try:
                start = end.replace(year=end.year-years)
            except ValueError:
                start = end.replace(year=end.year-years,day=28)
        else:
            start = end-timedelta(days=7)
        self.start.set(start.strftime('%Y-%m-%d 00:00'))
        self.end.set(end.strftime('%Y-%m-%d %H:%M'))

    def daily_job(self):
        end = datetime.now()
        return self.run_extract(list(self.cfg['selected_groups']),end-timedelta(hours=24),end,'',True)

    def custom(self, summarize):
        try:
            selection = self.group_choice.get()
            if not selection:
                raise ValueError('请先刷新并选择目标群聊')
            room = selection.rsplit(' | ',1)[1]
            if room not in self.groups or selection not in self.group_choice['values']:
                raise ValueError('请选择搜索结果中的目标群聊')
            start = datetime.strptime(self.start.get().strip(),'%Y-%m-%d %H:%M')
            end = datetime.strptime(self.end.get().strip(),'%Y-%m-%d %H:%M')+timedelta(seconds=59)
            self.run_extract([room],start,end,self.person.get().strip(),summarize)
        except Exception as exc:
            messagebox.showerror('输入有误',str(exc))

    def run_extract(self, rooms, start, end, person, summarize):
        cfg,secret = copy.deepcopy(self.cfg),copy.deepcopy(self.secrets)
        kind = 'job' if summarize else 'export'
        if not summarize and self.offline_export_keys is not None:
            secret['db_keys'] = self.offline_export_keys
        started = self.launch(lambda:extract(cfg,secret,rooms,start,end,person,summarize,self.cancel,self.progress,self.approve_plan),kind)
        if started and not summarize:
            self.offline_export_keys = None
        return started

    def test_push(self):
        token = self.secrets.get('pushplus_token','')
        if messagebox.askokcancel('调用次数提示','本次测试：Gemini 0 次；PushPlus 1 次。继续发送？'):
            self.launch(lambda:push(token,APP_NAME+' 测试','这是一条由本机配置界面发起的测试消息。',self.cfg,self.progress,self.cancel,secrets=self.secrets),'push')

    def health(self):
        cfg,secret = copy.deepcopy(self.cfg),copy.deepcopy(self.secrets)
        def check():
            check_cancel(self.cancel)
            pending = cfg.get('pending_alert')
            if pending:
                push(secret.get('pushplus_token',''),'⚠️ 运行异常提醒',pending,cfg,self.progress,self.cancel,secrets=secret)
                return 'alert_sent'
            last = latest_update(cfg)
            if last and time.time()-last > 18*3600 and time.time()-cfg.get('last_stale_alert',0)>6*3600:
                hours = (time.time()-last)/3600
                warning = f'消息数据库及 WAL 已约 {hours:.1f} 小时未更新，可能未同步或无新消息；仅凭文件时间不能确认微信掉线。'
                push(secret.get('pushplus_token',''),'⚠️ 运行异常提醒',warning,cfg,self.progress,self.cancel,secrets=secret)
                return ('stale',warning)
            return 'health_ok'
        self.launch(check,'health')

    def tick(self):
        if not self.busy and time.monotonic() >= self.next_quota_sync:
            self.next_quota_sync = time.monotonic()+1800
            candidates = [a for a in accounts(self.cfg,self.secrets,'pushplus')
                          if a.get('enabled',True) and a.get('auto_sync',True) and a.get('secret_key')]
            candidates = list({bucket(a):a for a in reversed(candidates)}.values())
            if candidates:
                secret = copy.deepcopy(self.secrets)
                self.launch(lambda:[sync_pushplus(secret,self.usage,a,self.cancel) for a in candidates],'quota')
        if self.cfg['enabled'] and not self.busy and time.monotonic() >= self.startup_ready:
            if time.monotonic() >= self.next_wechat_check:
                try:
                    result = subprocess.run(['tasklist','/FI','IMAGENAME eq Weixin.exe','/FO','CSV','/NH'],
                        capture_output=True,text=True,timeout=8,creationflags=subprocess.CREATE_NO_WINDOW)
                    self.wechat_running = result.returncode == 0 and 'weixin.exe' in result.stdout.lower()
                except (OSError,subprocess.TimeoutExpired):
                    self.wechat_running = False
                self.next_wechat_check = time.monotonic()+30
            if not self.wechat_running:
                self.status.set('等待微信启动和同步；错过的定时任务已保留')
                self.root.after(10000,self.tick)
                return
            job = self.scheduler.prepare(datetime.now(),self.cfg['schedule_times'],self.cfg['selected_groups'])
            if job:
                cfg,secret = copy.deepcopy(self.cfg),load_secrets()
                cfg['scheduled_job_id'] = job['id']
                self.active_schedule = job['id']
                self.launch(lambda:extract(cfg,secret,job['rooms'],datetime.fromisoformat(job['start']),
                    datetime.fromisoformat(job['end']),'',True,self.cancel,self.progress),'scheduled')
            elif time.monotonic() >= self.next_health:
                self.next_health = time.monotonic()+900
                self.health()
        self.root.after(10000,self.tick)

    def poll(self):
        if time.monotonic() >= self.next_usage_refresh:
            refresh_usage(self)
            self.next_usage_refresh = time.monotonic()+10
        if self.show_event and ctypes.windll.kernel32.WaitForSingleObject(self.show_event,0) == 0:
            self.show()
        while not self.events.empty():
            kind,value = self.events.get()
            if kind == 'plan':
                plan,ready,decision = value
                if self.cancel.is_set():
                    decision['approved'] = False
                else:
                    self.progress_stage = '等待确认调用预估'
                    self.progress_text.set('等待确认调用预估 · 约 55%（本地预检已完成）')
                    balances = '\n'+self.usage_vars['gemini'].get()+'\n'+self.usage_vars['pushplus'].get()
                    decision['approved'] = messagebox.askyesno('本次任务 API 调用预估',plan_text(plan)+balances+'\n\n是否继续？',parent=self.root)
                ready.set()
                continue
            if kind.startswith('ui_'):
                if kind == 'ui_tasks':
                    self.show()
                    show_tasks(self)
                else:
                    {'ui_show':self.show,'ui_pause':self.pause,'ui_exit':self.exit}[kind]()
                if self.closing:
                    return
                continue
            if kind == 'progress':
                if isinstance(value,dict):
                    if value.get('model_version'):
                        self.generated_model.set('本次实际模型：'+value['model_version'])
                    if value.get('usage_changed'):
                        refresh_usage(self)
                if self.cancel.is_set():
                    continue
                if isinstance(value,dict):
                    if 'percent' in value:
                        self.progress_bar.stop()
                        self.progress_bar.configure(mode='determinate')
                        self.progress_value.set(max(self.progress_value.get(),min(99,float(value['percent']))))
                    self.progress_stage = value.get('stage',self.progress_stage)
                    if value.get('usage_changed'):
                        refresh_usage(self)
                    value = value.get('text','')
                value = value or self.progress_stage
                self.status.set(value.splitlines()[0])
                self.progress_text.set(f'{self.progress_stage} · 约 {self.progress_value.get():.0f}% · {value.splitlines()[0][:75]}')
                self.log.insert('end',value+'\n')
                self.log.see('end')
                continue
            self.busy = False
            self.progress_bar.stop()
            self.progress_bar.configure(mode='determinate')
            if kind == 'done':
                task,result = value
                if task == 'groups':
                    self.set_groups(result)
                    msg = f'群列表读取成功：{len(self.groups)} 个群'
                elif task == 'health':
                    if result == 'alert_sent':
                        self.cfg.pop('pending_alert',None)
                        msg = '上次异常提醒已提交 PushPlus'
                    elif isinstance(result,tuple):
                        self.cfg['last_stale_alert'] = time.time()
                        msg = result[1]
                    else:
                        msg = '数据库更新时间检查正常'
                elif task in ('job','scheduled'):
                    if task == 'scheduled':
                        self.scheduler.finish(self.active_schedule)
                        self.active_schedule = None
                    msg = f'任务完成，生成 {len(result)} 个本地文件；推送状态见运行记录'
                elif task == 'export':
                    msg = f'导出完成，生成 {len(result)} 个本地文件'
                elif task == 'quota':
                    values = result if isinstance(result,list) else [result]
                    for info in values:
                        if info.get('group','default') == 'default':
                            self.cfg['pushplus_daily_limit'] = info['limit']
                        else:
                            for account in self.secrets.get('pushplus_accounts',[]):
                                if account.get('group','default').casefold() == info['group'].casefold():
                                    account['limit'] = info['limit']
                            save_secrets(self.secrets)
                    self.next_quota_sync = time.monotonic()+1800
                    msg = f'PushPlus 官网校准完成：{len(values)} 组；用量来源和时间见额度面板'
                else:
                    msg = str(result)
            elif kind == 'cancel':
                msg = value
            else:
                msg = '执行失败：'+value
                if kind != 'error_sent' and self.task_kind not in ('export','quota'):
                    self.cfg['pending_alert'] = msg
                if self.task_kind != 'export':
                    self.next_health = min(self.next_health,time.monotonic()+20)
            if kind == 'done':
                self.progress_bar.set_state('done')
                self.progress_value.set(100)
                completed = {'groups':'群列表读取完成','health':'状态检查完成','push':'测试推送已提交','quota':'额度查询完成'}.get(task,'任务已完成')
                self.progress_text.set(completed+' · 100%')
            else:
                self.progress_bar.set_state('idle' if kind == 'cancel' else 'error')
                self.progress_text.set(('已取消' if kind == 'cancel' else '未完成')+f' · 停止于约 {self.progress_value.get():.0f}%')
            refresh_usage(self)
            if self.active_schedule:
                if kind == 'cancel' and self.discard_on_cancel:
                    try:
                        if self.scheduler.cancel(self.active_schedule):
                            msg += '。该次定时任务已撤销，不再重试。'
                    except OSError as exc:
                        msg += '。无法保存撤销状态：'+safe_error(exc,self.secrets)
                else:
                    self.scheduler.failed(datetime.now())
                self.active_schedule = None
            self.last_task = (TASK_NAMES.get(self.task_kind,'任务'), msg)
            status = f'{datetime.now():%m-%d %H:%M} {msg}'
            if self.task_kind != 'export':
                self.cfg['last_run_status'] = status
                save_config(self.cfg)
            self.status.set(status)
            self.log.insert('end',status+'\n')
            self.log.see('end')
        self.root.after(150,self.poll)

    def open_exports(self):
        try:
            folder = export_directory(self.cfg)
            folder.mkdir(parents=True,exist_ok=True)
            os.startfile(folder)
        except Exception as exc:
            messagebox.showerror('打开目录失败',str(exc))

    def exit(self):
        if self.busy:
            self.cancel_task(discard=False)
            messagebox.showinfo('正在停止','已请求取消。请等待当前复制或 API 请求结束，再退出软件。')
            return
        if self.tray:
            self.tray.stop()
        self.closing = True
        self.root.destroy()

def main():
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateEventW.restype = ctypes.c_void_p
    kernel.CreateEventW.argtypes = [ctypes.c_void_p,ctypes.c_bool,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.SetEvent.argtypes = [ctypes.c_void_p]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None,False,'Local\\WeChatSummaryDesktop')
    existing = ctypes.get_last_error() == 183
    show_event = kernel.CreateEventW(None,False,False,'Local\\WeChatSummaryShow')
    if existing:
        if '--background' not in sys.argv:
            kernel.SetEvent(show_event)
        kernel.CloseHandle(show_event)
        kernel.CloseHandle(mutex)
        return
    root = ctk.CTk()
    root.withdraw()
    try:
        app = App(root)
        app.show_event = show_event
        try:
            app.start_tray()
        except Exception as exc:
            app.tray = None
            app.status.set('托盘初始化失败：'+safe_error(exc))
        if '--background' not in sys.argv or app.tray is None:
            root.deiconify()
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('启动失败',safe_error(exc))
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)
        kernel.CloseHandle(show_event)

if __name__ == '__main__':
    main()
