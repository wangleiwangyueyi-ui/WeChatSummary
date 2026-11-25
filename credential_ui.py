"""Local credential manager; values are never sent to the assistant or written as plaintext."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
import uuid
import webbrowser
from credentials import accounts, account_limit, bucket, store_accounts
from secure_store import load_secrets, save_secrets, save_config, safe_error
from quota_service import sync_pushplus
from app_info import GEMINI_LIMIT_URL

GEMINI_KEYS_URL = 'https://aistudio.google.com/api-keys'
PUSHPLUS_KEYS_URL = 'https://www.pushplus.plus/'
PUSHPLUS_SETUP_URL = 'https://www.pushplus.plus/doc/guide/openApi.html'
NEW_GROUP_OPTION = '＋ 新建独立额度组'

PUSHPLUS_SETUP = '''1. 用自己的微信登录 PushPlus 官网，在“我的 → 开发设置”中开启开放接口。
2. 按官网要求设置 secretKey（建议至少 32 位随机大小写字母和数字），保存到本机输入框。
3. 把本机请求所用的公网出口 IP 加入安全 IP。不是 127.0.0.1、192.168.x.x 或代理端口。
4. 同步接口使用“用户 Token”，不支持消息 Token；填写对应账号的 secretKey 后保存。
5. 点击“同步官网额度”。若返回 403 / IP 未授权，核对本机请求出口与该账号已保存的白名单是否一致；“已启用”不代表出口已经匹配。401 常见于未开启开放接口。
本软件的 PushPlus 请求不走 Gemini 代理；若使用全局/TUN 代理，出口 IP 可能仍受影响。浏览器查到的 IP 可能与软件不同，代理分流也可能让不同网站使用不同出口。
不用提供账号密码，也不要把密钥发到聊天里。开启自动同步后，启动及空闲时约每 30 分钟刷新；每次最多 3 次查询，不推送消息。
官网页面和软件的本机统计来源不同。手工填官网“今日已用”可立即校准；官网同步后会标记同步时间，后续请求继续累加。'''


def show_pushplus_setup(app):
    from macos_dialogs import reading_dialog
    return reading_dialog(app.root,'PushPlus 自动校准设置步骤',PUSHPLUS_SETUP,
        [('打开 PushPlus 官网',PUSHPLUS_KEYS_URL),('查看官方设置说明',PUSHPLUS_SETUP_URL)])


def show_image_key_help(app):
    exists = bool(app.secrets.get('image_key_hex'))
    messagebox.showinfo('V2 图片密钥 · 本机获取',
        ('当前图片密钥已保存。\n\n' if exists else '当前尚未保存图片密钥。\n\n')+
        '读取微信 V2 加密图片需要该账号的图片密钥及 XOR 参数，不能用 Gemini Key 代替。\n'
        '点击“数据库 / 图片密钥”，在统一向导中选择“提取图片密钥”。\n'
        '提取前需打开两张近期普通聊天图片，保留大图窗口，然后断网。\n'
        '本机已初始化时无需重复提取；临时组件清理后，如需重新初始化请联系作者。',parent=app.root)


def show_credentials(app, service='gemini'):
    from ui_extras import refresh_usage
    from macos_dialogs import credentials_dialog
    return credentials_dialog(app,service,CredentialEditor,refresh_usage)


class CredentialEditor:
    def __init__(self, app, window, page, service, refresh):
        self.app,self.window,self.service,self.refresh = app,window,service,refresh
        self.model = app.cfg.get('model','') if service == 'gemini' else ''
        self.items = accounts(app.cfg,app.secrets,service,include_empty=True)
        self.current_id = 'primary'
        from macos_dialogs import build_credential_editor
        build_credential_editor(self,page)

    def render(self):
        from usage_tracker import format_usage
        self.tree.delete(*self.tree.get_children())
        current = self.app.usage.active(self.service)
        for index,item in enumerate(self.items,1):
            info = self.app.usage.summary(self.service,bucket(item,self.model),account_limit(self.app.cfg,item,self.service,self.model))
            state = '未填写' if not item.get('key') else '停用' if not item.get('enabled',True) else '当前' if item['id']==current else '备用'
            self.tree.insert('', 'end',iid=item['id'],values=(f'{index}. {item["label"]}',item.get('group','default'),format_usage('',info).lstrip('：'),state))
        self.group_entry.configure(values=list(dict.fromkeys(['default',NEW_GROUP_OPTION]+[item.get('group','default') for item in self.items])))

    def choose_group(self, _=None):
        if self.vars['group'].get()!=NEW_GROUP_OPTION:
            return
        existing={item.get('group','default').casefold() for item in self.items}
        number=1
        while f'独立组 {number}' in existing:
            number+=1
        name=f'独立组 {number}'
        self.vars['group'].set(name)
        self.group_entry.configure(values=tuple(self.group_entry.cget('values'))+(name,))
        self.detail.set(f'已创建“{name}”草稿，与主项分开计数。请核对每日额度，点击“保存当前凭据/校准”后生效。')

    def load(self, account_id):
        self.current_id = account_id
        item = next(a for a in self.items if a['id']==account_id)
        for key in ('label','key','group','secret_key'):
            self.vars[key].set(item.get(key,''))
        value = account_limit(self.app.cfg,item,self.service,self.model)
        self.vars['limit'].set('' if value is None else str(value))
        self.vars['used'].set('')
        self.vars['maximum'].set(str(self.app.cfg.get('max_api_calls',100)))
        self.enabled.set(item.get('enabled',True))
        self.auto_sync.set(item.get('auto_sync',True))
        self.group_entry.configure(state='disabled' if account_id=='primary' else 'normal')
        info = self.app.usage.summary(self.service,bucket(item,self.model),value)
        self.detail.set(f'统计日 {info["day"]} · {info["source"]} · 本机请求 {info["local"]} 次 · 返回 Token {info["tokens"]:,}\n'
                        '未校准时仅统计安装此功能后的请求；“本次任务预估”与“官网今日已用”不是同一个数。')

    def select(self, _=None):
        selected = self.tree.selection()
        if selected:
            self.load(selected[0])

    def add(self):
        item = dict(id=uuid.uuid4().hex,label=f'备用 {len(self.items)}',key='',group='default',enabled=True,auto_sync=True)
        self.items.append(item)
        self.render()
        self.tree.selection_set(item['id'])
        self.load(item['id'])

    def save(self):
        if self.app.busy:
            messagebox.showinfo('任务运行中','请等待任务完成后保存。',parent=self.window)
            return False
        try:
            self.choose_group()
            items = copy.deepcopy(self.items)
            item = next(a for a in items if a['id']==self.current_id)
            for key in ('label','key','group','secret_key'):
                item[key] = self.vars[key].get().strip()
            if not item['label'] or not item['group']:
                raise ValueError('请填写名称和额度组')
            if item['id']=='primary':
                item['group']='default'
            item['group']=item['group'].casefold()
            if item['id']!='primary' and not item['key']:
                raise ValueError('请填写新增的 Key/Token')
            item['enabled'],item['auto_sync'] = self.enabled.get(),self.auto_sync.get()
            raw = self.vars['limit'].get().strip()
            limit = None if not raw else int(raw)
            if limit is not None and limit<0:
                raise ValueError('额度不能为负数')
            used = self.vars['used'].get().strip()
            if used and int(used)<0:
                raise ValueError('已用次数不能为负数')
            cfg,secrets = copy.deepcopy(self.app.cfg),load_secrets()
            if self.service=='gemini':
                maximum = int(self.vars['maximum'].get())
                if maximum<1:
                    raise ValueError('单任务上限至少为 1')
                cfg['max_api_calls']=maximum
            if item['group']=='default':
                if self.service=='gemini':
                    cfg.setdefault('gemini_daily_limits',{})[self.model]=limit
                else:
                    cfg['pushplus_daily_limit']=limit
            else:
                for other in items:
                    if other.get('group','default').casefold()==item['group'].casefold():
                        if self.service=='gemini':
                            other.setdefault('limits',{})[self.model]=limit
                        else:
                            other['limit']=limit
            store_accounts(cfg,secrets,self.service,items)
            save_secrets(secrets)
            save_config(cfg)
            self.app.cfg,self.app.secrets = cfg,secrets
            self.items=items
            if used:
                self.app.usage.calibrate(self.service,int(used),bucket(item,self.model))
            keyname = 'gemini_api_key' if self.service=='gemini' else 'pushplus_token'
            self.app.fields[keyname].set(secrets.get(keyname,''))
            self.app.status.set('凭据和额度已保存')
            self.render()
            self.tree.selection_set(item['id'])
            self.load(item['id'])
            self.refresh(self.app)
            return True
        except Exception as exc:
            messagebox.showerror('保存失败',safe_error(exc,self.app.secrets),parent=self.window)
            return False

    def remove(self):
        if self.current_id=='primary':
            messagebox.showinfo('主项保留','主项可清空或停用，不能删除。',parent=self.window)
            return
        if self.app.busy:
            return
        self.items=[a for a in self.items if a['id']!=self.current_id]
        self.current_id='primary'
        self.load('primary')
        self.save()

    def sync(self):
        if not self.vars['secret_key'].get().strip():
            show_pushplus_setup(self.app)
            return
        if self.save():
            item=copy.deepcopy(next(a for a in self.items if a['id']==self.current_id))
            self.window.destroy()
            self.app.launch(lambda:sync_pushplus(self.app.secrets,self.app.usage,item,self.app.cancel),'quota')
