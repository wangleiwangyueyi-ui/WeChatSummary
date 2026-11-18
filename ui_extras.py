"""Quota dashboard and product help dialogs."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from app_info import APP_NAME, AUTHOR_EMAIL, HELP_TEXT, GEMINI_LIMIT_URL, PUSHPLUS_LIMIT_URL
from usage_tracker import UsageTracker, daily_limit, format_usage
from secure_store import load_secrets, save_secrets, save_config, safe_error
from credentials import active_account, account_limit, bucket, accounts, CredentialPool


def build_usage_panel(app, parent):
    from macos_ui import build_usage_badges
    build_usage_badges(app,parent)


def refresh_usage(app):
    try:
        sources,current = [],[]
        for service,label,model in [('gemini','Gemini',app.cfg['model']),('pushplus','PushPlus','')]:
            account = active_account(app.cfg,app.secrets,service,app.usage)
            info = app.usage.summary(service,bucket(account,model),account_limit(app.cfg,account,service,model))
            total = CredentialPool(app.cfg,app.secrets,service,app.usage).summary()
            title = f'{label} 合计（{total["groups"]} 组）'
            app.usage_vars[service].set(format_usage(title,total) if total['groups'] else label+'：未配置已启用凭据')
            limit = '待确认' if info['limit'] is None else str(info['limit'])
            current.append(f'当前 {label} · {account["label"][:12]}：{info["used"]}/{limit} 次')
            source = info['source']
            brief = '官网同步' if source.startswith('官网同步') else '截图校准' if source.startswith('截图校准') else '手动校准' if source.startswith('手动') else '本机估算'
            sources.append(('G' if service=='gemini' else 'P')+': '+brief)
        app.current_usage.set('\n'.join(current))
        app.usage_source.set('；'.join(sources)+' ｜本地 OCR/语音：0 次 API')
    except Exception:
        for var in app.usage_vars.values():
            var.set('用量统计读取失败，请查看额度设置')


def show_quota_settings(app):
    from credential_ui import show_credentials
    show_credentials(app)


def show_help(app):
    from help_ui import show_guide
    return show_guide(app)


def show_author(app):
    from macos_dialogs import author_dialog
    return author_dialog(app,AUTHOR_EMAIL)
