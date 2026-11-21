"""Live view of the worker and the saved daily report schedule."""
from datetime import datetime
import time
from tkinter import messagebox

from macos_dialogs import dialog, reveal, wrapped
from macos_theme import MACOS_THEME as T, button, frame, label
from scheduler import next_due
from secure_store import safe_error


TASK_NAMES = {
    'job': '手动导出 / 汇总',
    'scheduled': '定时汇总',
    'groups': '刷新群列表',
    'health': '检查运行状态',
    'push': '测试手机推送',
    'quota': '查询 API 额度',
}


def show_tasks(app):
    existing = getattr(app, 'task_window', None)
    if existing and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        return existing

    window = app.task_window = dialog(app.root, '任务管理', 640, 420, (530, 390))
    window.grid_rowconfigure(3, weight=1)
    label(window, '任务管理', size='dialog_title_size', bold=True).grid(
        row=0, column=0, sticky='w', padx=18, pady=(14, 10))

    current = frame(window, card=True)
    current.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 8))
    current.grid_columnconfigure(0, weight=1)
    label(current, '当前任务', size='section_size', bold=True).grid(
        row=0, column=0, sticky='w', padx=12, pady=(8, 0))
    task_status = wrapped(current, size='dialog_body_size')
    task_status.grid(row=1, column=0, sticky='ew', padx=12, pady=(2, 0))
    detail = wrapped(current, muted=True)
    detail.grid(row=2, column=0, columnspan=2, sticky='ew', padx=12, pady=(4, 0))
    cancel_button = button(current, '取消当前任务', app.cancel_task, width=116)
    cancel_button.grid(row=0, column=1, rowspan=2, sticky='ne', padx=12, pady=(8, 0))
    last_result = wrapped(current, muted=True, size='small_size')
    last_result.grid(row=3, column=0, columnspan=2, sticky='ew', padx=12, pady=(6, 9))

    schedule = frame(window, card=True)
    schedule.grid(row=2, column=0, sticky='ew', padx=16)
    schedule.grid_columnconfigure(0, weight=1)
    label(schedule, '定时计划', size='section_size', bold=True).grid(
        row=0, column=0, sticky='w', padx=12, pady=(8, 0))
    schedule_status = wrapped(schedule, size='dialog_body_size')
    schedule_status.grid(row=1, column=0, columnspan=2, sticky='ew', padx=12, pady=(2, 0))
    next_time = wrapped(schedule, muted=True)
    next_time.grid(row=2, column=0, columnspan=2, sticky='ew', padx=12, pady=(4, 0))
    pending_status = wrapped(schedule, muted=True)
    pending_status.grid(row=3, column=0, sticky='ew', padx=12, pady=(4, 0))
    schedule_actions = frame(schedule)
    schedule_actions.grid(row=4, column=0, columnspan=2, sticky='ew', padx=12, pady=(8, 9))
    toggle = button(schedule_actions, '暂停定时计划', app.pause, width=116)
    toggle.pack(side='left', padx=(0, 6))

    def open_daily():
        close()
        app.tabs.select('日常汇总')

    edit = button(schedule_actions, '修改群聊或时间', open_daily, width=116)
    edit.pack(side='left')

    def discard_pending():
        pending = app.scheduler.state.get('pending')
        if not pending or pending['id'] == app.active_schedule:
            return
        try:
            if app.scheduler.cancel(pending['id']):
                app.status.set('该次待重试的定时任务已撤销')
        except OSError as exc:
            messagebox.showerror('撤销失败', safe_error(exc, app.secrets), parent=window)

    discard_pending_button = button(schedule, '撤销这一轮', discard_pending, width=100, height=26)
    discard_pending_button.grid(row=3, column=1, sticky='e', padx=(0, 12), pady=(4, 0))

    def revoke_plan():
        accepted = messagebox.askokcancel(
            '撤销定时计划',
            '撤销后会移除计划里的群聊，并停止后续定时汇总及待重试任务。'
            '如果本轮定时汇总正在运行，也会停止。已生成的报告和聊天记录会保留。',
            parent=window,
        )
        if not accepted:
            return
        try:
            app.revoke_daily_plan()
        except OSError as exc:
            messagebox.showerror('撤销失败', safe_error(exc, app.secrets), parent=window)
            return
        set_text(schedule_status, '定时计划已撤销')
        discard.configure(state='disabled')

    discard = button(schedule_actions, '撤销定时计划', revoke_plan, width=126,
                     text_color=T['attention'])
    discard.pack(side='right')
    timer = None

    def close():
        window.destroy()

    def clear_timer(event):
        if event.widget is window and timer is not None:
            app.root.after_cancel(timer)

    def set_text(widget, value):
        if widget.cget('text') != value:
            widget.configure(text=value)

    def refresh():
        nonlocal timer
        now = datetime.now()
        is_cancelling = app.busy and app.cancel.is_set()
        if app.busy:
            name = TASK_NAMES.get(app.task_kind, '任务')
            seconds = max(0, int(time.monotonic()-(app.task_started or time.monotonic())))
            state = '正在取消' if is_cancelling else '运行中'
            set_text(task_status, f'{state} · {name} · 已运行 {seconds} 秒')
            set_text(detail, app.status.get() if is_cancelling else app.progress_text.get())
        else:
            set_text(task_status, '空闲 · 当前没有正在运行的任务')
            set_text(detail, '任务启动后，这里会显示正在执行的步骤。')
        set_text(cancel_button, '正在取消…' if is_cancelling else '取消当前任务')
        cancel_button.configure(state='normal' if app.busy and not is_cancelling else 'disabled')
        previous = getattr(app, 'last_task', None)
        recent = f'上次任务 · {previous[0]} · {previous[1]}' if previous else '本次启动后暂无任务结果'
        set_text(last_result, recent if len(recent) <= 170 else recent[:169]+'…')

        enabled = app.cfg['enabled']
        count = len(app.cfg['selected_groups'])
        hours = app.cfg['schedule_times']
        if count:
            set_text(schedule_status, f'{"已启用" if enabled else "已暂停"} · {count} 个群 · 每天 {hours}')
        else:
            set_text(schedule_status, '暂无定时计划')
        if enabled and count:
            try:
                following = next_due(now, hours).strftime('%m-%d %H:%M')
                set_text(next_time, f'下一个计划时间 · {following}')
            except ValueError:
                set_text(next_time, '请检查每日运行时间的格式。')
        elif count:
            set_text(next_time, '定时汇总已暂停。')
        else:
            set_text(next_time, '如需创建计划，请选择群聊、保存并启用。')
        set_text(toggle, '暂停定时计划' if enabled else '恢复定时计划')
        toggle.configure(state='normal' if enabled or count else 'disabled')
        set_text(edit, '修改群聊或时间' if count else '设置定时计划')
        pending = app.scheduler.state.get('pending')
        if pending and pending['id'] != app.active_schedule:
            due = str(pending.get('due', '')).replace('T', ' ')[:16]
            set_text(pending_status, f'有一项未完成的定时汇总 · {due}')
            discard_pending_button.grid()
        elif pending:
            set_text(pending_status, '本轮定时汇总正在运行')
            discard_pending_button.grid_remove()
        else:
            set_text(pending_status, '暂无待执行或待重试的定时任务')
            discard_pending_button.grid_remove()
        discard.configure(state='normal' if count or enabled or pending else 'disabled')
        timer = app.root.after(400, refresh)

    footer = frame(window)
    footer.grid(row=4, column=0, sticky='ew', padx=16, pady=10)
    button(footer, '关闭', close, width=72).pack(side='right')
    window.protocol('WM_DELETE_WINDOW', close)
    window.bind('<Destroy>', clear_timer, add='+')
    window.bind('<Escape>', lambda _: close())
    refresh()
    reveal(window)
    return window
