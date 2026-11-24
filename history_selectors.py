"""Local calendar and searchable history participant selectors."""
import calendar
from datetime import datetime
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from macos_dialogs import dialog, reveal
from macos_theme import frame, label, button, entry, search_entry, family
from db_reader import contacts, message_sources, snapshot, storage, display
from secure_store import safe_error
from task_control import Cancelled, check_cancel
import hashlib


def calendar_dialog(parent, variable, title):
    try:
        initial = datetime.strptime(variable.get(), '%Y-%m-%d %H:%M')
    except ValueError:
        initial = datetime.now()
    window = dialog(parent, title, 510, 510, (490, 490))
    header = frame(window)
    header.pack(fill='x', padx=16, pady=12)
    year = tk.StringVar(value=str(initial.year))
    month = tk.StringVar(value=str(initial.month))
    day = tk.IntVar(value=initial.day)
    face = (family(window), -round(16 * window._get_window_scaling()))
    window.option_add('*TCombobox*Listbox.font', face)
    def spin(container, variable, start, end, width=5):
        group = frame(container)
        group.pack(side='left', padx=4)
        def adjust(amount):
            try:
                value = int(variable.get())
            except ValueError:
                return
            variable.set(str(max(start, min(end, value + amount))))
            draw()
        button(group, '−', lambda: adjust(-1), width=32, height=34).pack(side='left')
        widget = entry(group, variable, width=width*13, height=34)
        widget.pack(side='left', padx=3)
        button(group, '＋', lambda: adjust(1), width=32, height=34).pack(side='left')
        return widget
    year_field = spin(header, year, 1, 9999)
    label(header, '年').pack(side='left')
    month_field = spin(header, month, 1, 12, 3)
    label(header, '月').pack(side='left')
    grid = frame(window)
    grid.pack(fill='both', expand=True, padx=16)
    days = []
    for col, name in enumerate(('一', '二', '三', '四', '五', '六', '日')):
        grid.grid_columnconfigure(col, weight=1)
        label(grid, name).grid(row=0, column=col)
    def selected_date():
        return datetime(int(year.get()), int(month.get()), 1)
    def choose(value):
        day.set(value)
        draw()
    def draw(_=None):
        try:
            current = selected_date()
        except ValueError:
            return
        day.set(min(day.get(), calendar.monthrange(current.year, current.month)[1]))
        for widget in days:
            widget.destroy()
        days.clear()
        for row, week in enumerate(calendar.monthcalendar(current.year, current.month), 1):
            for col, value in enumerate(week):
                if value:
                    widget = button(grid, str(value), lambda n=value: choose(n), width=44, height=32, primary=value==day.get())
                    widget.grid(row=row, column=col, padx=2, pady=3, sticky='ew')
                    days.append(widget)
    def shift(amount):
        try:
            current = selected_date()
            new_year, new_month = divmod(current.year*12+current.month-1+amount, 12)
            if 1 <= new_year <= 9999:
                year.set(str(new_year))
                month.set(str(new_month+1))
                draw()
        except ValueError:
            pass
    navigation = frame(window)
    navigation.pack(fill='x', padx=20, pady=(0, 6), before=grid)
    button(navigation, '上一月', lambda: shift(-1), width=90).pack(side='left')
    button(navigation, '下一月', lambda: shift(1), width=90).pack(side='right')
    for field in (year_field, month_field):
        field.bind('<Return>', draw)
        field.bind('<FocusOut>', draw)
    clock = frame(window)
    clock.pack(fill='x', padx=16, pady=8)
    hour = tk.StringVar(value=f'{initial.hour:02d}')
    minute = tk.StringVar(value=f'{initial.minute:02d}')
    for text, value, count in (('时', hour, 24), ('分', minute, 60)):
        ttk.Combobox(clock, textvariable=value, values=[f'{n:02d}' for n in range(count)], state='readonly', width=4, font=face).pack(side='left', padx=4)
        label(clock, text).pack(side='left')
    def apply():
        draw()
        try:
            value = datetime(int(year.get()), int(month.get()), day.get(), int(hour.get()), int(minute.get()))
        except ValueError:
            messagebox.showerror('日期无效', '请输入 1 至 9999 的年份和有效月份，再选择日期。', parent=window)
            return
        variable.set(f'{value.year:04d}-{value.month:02d}-{value.day:02d} {value.hour:02d}:{value.minute:02d}')
        window.destroy()
    button(clock, '确定', apply, primary=True, width=76).pack(side='right')
    draw()
    reveal(window)
    return window


def history_participants(cfg, secrets, room, cancel):
    people = contacts(cfg, secrets, cancel)
    table = 'Msg_' + hashlib.md5(room.encode()).hexdigest()
    members = set()
    missing = []
    for source in message_sources(storage(cfg)):
        check_cancel(cancel)
        try:
            with snapshot(source, secrets.get('db_keys', {}), cancel) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if table in tables and 'Name2Id' not in tables:
                    missing.append(source.name)
                elif table in tables:
                    members.update(row[0] for row in connection.execute(
                        f'SELECT DISTINCT n.user_name FROM "{table}" m JOIN Name2Id n ON n.rowid=m.real_sender_id') if row[0])
        except Cancelled:
            raise
        except (KeyError, ValueError, RuntimeError, OSError, sqlite3.Error):
            missing.append(source.name)
    rows = [(uid, display(people, uid), str(people.get(uid, {}).get('nick_name') or ''), str(people.get(uid, {}).get('remark') or '')) for uid in members]
    return sorted(rows, key=lambda row: (row[1].casefold(), row[0])), missing


def participant_dialog(app):
    selection = app.group_choice.get()
    if ' | ' not in selection:
        messagebox.showinfo('选择群聊', '请先选择目标群聊。', parent=app.root)
        return
    if app.busy:
        messagebox.showinfo('任务进行中', '请等当前任务结束后加载发言人。', parent=app.root)
        return
    existing = getattr(app, 'participant_window', None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return
    room = selection.rsplit(' | ', 1)[1]
    window = app.participant_window = dialog(app.root, '选择群内发言人', 760, 530, (600, 430))
    window.grid_rowconfigure(2, weight=1)
    query = tk.StringVar()
    search = search_entry(window, query, placeholder_text='搜索昵称、备注或微信标识')
    search.grid(row=0, column=0, sticky='ew', padx=16, pady=12)
    status = label(window, '正在读取本地聊天记录中的发言人…', size='small_size', muted=True)
    status.grid(row=1, column=0, sticky='w', padx=16, pady=4)
    listing = ttk.Treeview(window, columns=('name', 'nickname', 'id'), show='headings', selectmode='browse')
    scale = window._get_window_scaling()
    ttk.Style(window).configure('Participants.Treeview', font=(family(window), -round(14*scale)), rowheight=round(30*scale))
    listing.configure(style='Participants.Treeview')
    for name, title, width in (('name', '显示名称 / 备注', 200), ('nickname', '昵称', 180), ('id', '微信标识', 220)):
        listing.heading(name, text=title)
        listing.column(name, width=width)
    listing.grid(row=2, column=0, sticky='nsew', padx=(16, 0))
    scroll = ttk.Scrollbar(window, command=listing.yview)
    scroll.grid(row=2, column=1, sticky='ns', padx=(0, 12))
    listing.configure(yscrollcommand=scroll.set)
    controls = frame(window)
    controls.grid(row=3, column=0, sticky='ew', padx=16, pady=12)
    stop = threading.Event()
    result = queue.Queue()
    rows = []
    def close():
        stop.set()
        window.destroy()
    def use_all():
        app.person.set('')
        close()
    def use_selected(_=None):
        chosen = listing.selection()
        if chosen:
            if app.group_choice.get() != selection:
                messagebox.showinfo('群聊已切换', '请重新打开当前群聊的发言人列表。', parent=window)
                close()
                return
            name, nickname, uid = listing.item(chosen[0], 'values')
            names = ' / '.join(dict.fromkeys(n for n in (name, nickname) if n and n != uid))
            caption = f'{names} | {uid}' if names else uid
            app.selected_participant = (caption, uid)
            app.person.set(caption)
            close()
    button(controls, '全部发言人', use_all, width=110).pack(side='left')
    button(controls, '选择此人', use_selected, primary=True, width=100).pack(side='right')
    listing.bind('<Double-1>', use_selected)
    def filter_rows(*_):
        listing.delete(*listing.get_children())
        needle = query.get().strip().casefold()
        for uid, name, nickname, remark in rows:
            if not needle or needle in ' '.join((uid, name, nickname, remark)).casefold():
                listing.insert('', 'end', iid=uid, values=(name, nickname, uid))
    query.trace_add('write', filter_rows)
    import copy
    cfg, secrets = copy.deepcopy(app.cfg), copy.deepcopy(app.secrets)
    if app.offline_export_keys is not None:
        secrets['db_keys'] = dict(app.offline_export_keys)
    def work():
        try:
            result.put((True, history_participants(cfg, secrets, room, stop)))
        except Exception as exc:
            result.put((False, safe_error(exc, secrets)))
    def poll():
        if not window.winfo_exists():
            return
        try:
            ok, value = result.get_nowait()
        except queue.Empty:
            window.after(120, poll)
            return
        if not ok:
            status.configure(text=value)
            return
        found, missing = value
        rows.extend(found)
        status.configure(text=f'历史记录中出现过 {len(rows)} 位发言人' + (f' · {len(missing)} 个分库未能读取，列表不完整' if missing else ''))
        filter_rows()
    window.protocol('WM_DELETE_WINDOW', close)
    threading.Thread(target=work, daemon=True).start()
    window.after(120, poll)
    reveal(window)
    return window


def participant_filter(app):
    """Keep the readable selection separate from the exact query identity."""
    value = app.person.get().strip()
    selected = getattr(app, 'selected_participant', None)
    return 'id=' + selected[1] if selected and value == selected[0] else value
