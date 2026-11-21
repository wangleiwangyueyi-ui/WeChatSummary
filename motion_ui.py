"""Native transitions and shortcuts for the desktop workspace."""
import ctypes
import sys
import tkinter as tk

import customtkinter as ctk
from macos_theme import MACOS_THEME as T, button, entry, family, frame, label


def motion_enabled(widget):
    root = widget._root()
    if not hasattr(root, '_motion_enabled'):
        permitted = ctypes.c_int(1)
        if sys.platform == 'win32':
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(permitted), 0)
        root._motion_enabled = bool(permitted.value)
    return root._motion_enabled


class Transition:
    """A short, interruptible animation owned by a single Tk widget."""

    def __init__(self, widget):
        self.widget = widget
        self.timer = widget._root()
        self.pending = None
        tk.Misc.bind(widget, '<Destroy>', self.stop, add='+')

    def stop(self, _=None):
        if self.pending is not None:
            self.timer.after_cancel(self.pending)
            self.pending = None

    def play(self, draw):
        self.stop()
        if not motion_enabled(self.widget):
            draw(1)
            return

        def step(index):
            self.pending = None
            draw(1 - (1 - index / 8) ** 3)
            if index < 8:
                self.pending = self.timer.after(16, step, index + 1)

        step(1)


class TabUnderline(tk.Canvas):
    def __init__(self, parent, selector, pages):
        super().__init__(parent, bg=T['nav_surface'], height=3, highlightthickness=0, bd=0)
        self.pages, self.selector = pages, selector
        self.target = 0
        self.position = 0
        self.transition = Transition(self)
        self.mark = self.create_line(0, 1, 0, 1, width=3, capstyle='round', fill=T['primary'])
        self.bind('<Configure>', lambda _: self.paint())

    def paint(self):
        buttons = {child.cget('text'):child for child in self.selector.winfo_children()
                   if isinstance(child, ctk.CTkButton)}
        left_index = int(self.position)
        right_index = min(len(self.pages)-1, left_index+1)
        items = [buttons.get(self.pages[index]) for index in (left_index,right_index)]
        if not all(item is not None and item.winfo_width()>1 for item in items):
            return
        left, right = items
        fraction = self.position-left_index
        center = (left.winfo_rootx()+left.winfo_width()/2)*(1-fraction)
        center += (right.winfo_rootx()+right.winfo_width()/2)*fraction - self.winfo_rootx()
        half = (left.winfo_width()*(1-fraction)+right.winfo_width()*fraction)*.32
        self.coords(self.mark, center-half, 1, center+half, 1)

    def select(self, name):
        self.target = self.pages.index(name)
        start = self.position

        def draw(fraction):
            self.position = start + (self.target-start)*fraction
            self.paint()

        self.transition.play(draw)


class QuotaMeter(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=T['quota_track'], height=3, highlightthickness=0, bd=0)
        self.value = 0
        self.target = None
        self.transition = Transition(self)
        self.fill = self.create_rectangle(0, 0, 0, 3, width=0)
        self.bind('<Configure>', lambda _: self.paint())

    def paint(self):
        self.coords(self.fill, 0, 0, self.winfo_width()*self.value, self.winfo_height())

    def set(self, used, limit):
        target = min(1, used/limit) if limit else 0
        if self.target == target:
            return
        self.target = target
        self.itemconfigure(self.fill, fill=T['attention'] if target >= .9 else T['primary'])
        start = self.value

        def draw(fraction):
            self.value = start+(target-start)*fraction
            self.paint()

        self.transition.play(draw)


class PhaseDots(tk.Canvas):
    """Show three milestones without assigning a fake percentage to a task."""

    def __init__(self, parent, percent):
        super().__init__(parent, bg=T['footer'], width=36, height=14, highlightthickness=0)
        self.percent = percent
        self.state = 'idle'
        self.dots = [self.create_oval(2+i*12, 4, 8+i*12, 10, width=0) for i in range(3)]
        self.trace = percent.trace_add('write', self.paint)
        self.bind('<Destroy>', lambda _: percent.trace_remove('write', self.trace))
        self.paint()

    def set_state(self, state):
        self.state = state
        self.paint()

    def paint(self, *_):
        active = {'running': 2 if self.percent.get() > 0 else 1, 'done': 3, 'error': 1}.get(self.state, 0)
        color = {'running': T['progress_running'], 'done': T['progress_done'],
                 'error': T['progress_running']}.get(self.state, T['progress_idle'])
        for index, dot in enumerate(self.dots):
            self.itemconfigure(dot, fill=color if index < active else T['border_input'])


def toggle_focus(app):
    if app.top_bar.winfo_manager():
        app.top_bar.grid_remove()
        app.focus_button.configure(text='退出专注')
    else:
        app.top_bar.grid()
        app.focus_button.configure(text='专注')


def bind_clear_undo(field, variable, control):
    """Keep the last explicitly cleared query, even while the list is rebuilt."""
    last = ''

    def update(*_):
        control.configure(text='撤销' if last and not variable.get() else '清空')

    def clear_or_undo():
        nonlocal last
        value = variable.get()
        if value:
            last = value
            variable.set('')
        elif last:
            restored, last = last, ''
            variable.set(restored)
        field.focus_set()

    variable.trace_add('write', update)
    control.configure(command=clear_or_undo)


def copy_log(app, control):
    text = app.log.get('1.0', 'end-1c')
    if not text.strip():
        return
    app.root.clipboard_clear()
    app.root.clipboard_append(text)
    control.configure(text='✓ 已复制')
    if not hasattr(control, 'copy_reset'):
        control.copy_reset = None
        def cancel(_=None):
            if control.copy_reset:
                app.root.after_cancel(control.copy_reset)
                control.copy_reset = None
        tk.Misc.bind(control, '<Destroy>', cancel, add='+')
    if control.copy_reset:
        app.root.after_cancel(control.copy_reset)
    def reset():
        control.copy_reset = None
        control.configure(text='复制日志')
    control.copy_reset = app.root.after(1400, reset)


def show_commands(app, _=None):
    from macos_dialogs import dialog, reveal

    existing = getattr(app, 'command_window', None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        existing.command_search.focus_set()
        return 'break'
    window = app.command_window = dialog(app.root, '快捷指令', 530, 376, (420, 300))
    window.grid_rowconfigure(2, weight=1)
    label(window, '快捷指令', size='dialog_title_size', bold=True).grid(
        row=0, column=0, sticky='w', padx=16, pady=(14, 8))
    query = tk.StringVar(window)
    search = window.command_search = entry(window, query, placeholder_text='搜索页面、额度、更新、导出目录…')
    search.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 8))
    card = frame(window, card=True)
    card.grid(row=2, column=0, sticky='nsew', padx=16)
    commands = [(name, lambda page=name: app.tabs.select(page)) for name in app.tabs.pages]
    commands.extend((caption, app.ui_controls[key].invoke) for caption, key in (
        ('任务管理', 'tasks'), ('刷新群列表', 'refresh_groups'), ('打开导出目录', 'open_exports'),
        ('检查更新', 'check_updates'), ('额度管理', 'quota'),
        ('图片 / 语音组件', 'optional_components'), ('使用说明', 'help'),
        ('切换专注模式', 'focus_mode')))
    scale = card._get_widget_scaling()
    listing = tk.Listbox(card, exportselection=False, font=(family(window), -round(14*scale)),
                         bg=T['bg_card'], fg=T['text'], selectbackground=T['selected_bg'],
                         selectforeground=T['selected_text'], relief='flat', highlightthickness=0,
                         activestyle='none', height=6)
    bar = ctk.CTkScrollbar(card, command=listing.yview, width=12)
    bar.pack(side='right', fill='y', padx=(0, 5), pady=5)
    listing.configure(yscrollcommand=bar.set)
    listing.pack(fill='both', expand=True, padx=(8, 4), pady=6)
    matching = []

    def redraw(*_):
        criteria = query.get().strip().casefold()
        matching[:] = [item for item in commands if criteria in item[0].casefold()]
        listing.delete(0, 'end')
        for caption, _callback in matching:
            listing.insert('end', '  '+caption)
        if matching:
            listing.selection_set(0)

    def move(amount):
        if matching:
            selection = listing.curselection()
            index = max(0, min(len(matching)-1, (selection[0] if selection else 0)+amount))
            listing.selection_clear(0, 'end')
            listing.selection_set(index)
            listing.see(index)
        return 'break'

    def activate(_=None):
        selection = listing.curselection()
        if selection and matching:
            callback = matching[selection[0]][1]
            window.destroy()
            callback()
        return 'break'

    footer = frame(window)
    footer.grid(row=3, column=0, sticky='ew', padx=16, pady=10)
    label(footer, '↑ ↓ 选择   Enter 执行   Esc 关闭', size='small_size', muted=True).pack(side='left')
    button(footer, '打开', activate, primary=True, width=70).pack(side='right')
    query.trace_add('write', redraw)
    window.bind('<Escape>', lambda _: window.destroy())
    for widget in (search, listing):
        widget.bind('<Up>', lambda _: move(-1))
        widget.bind('<Down>', lambda _: move(1))
        widget.bind('<Return>', activate)
    listing.bind('<Double-Button-1>', activate)
    redraw()
    reveal(window)
    search.focus_set()
    return 'break'
