"""Launch the explicit, offline database setup from the desktop application."""
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox

from app_paths import APP_DIR
from secure_store import load_secrets, safe_error

REQUIRED_FILES = ('initialize_offline.pyw', 'bootstrap/__init__.py',
                  'bootstrap/key.py', 'bootstrap/common.py',
                  'initialize_images.pyw', 'image_key_once.py', 'clear_wechat_logs.ps1')


def open_setup(app):
    if app.busy:
        messagebox.showinfo('任务运行中', '请先等待当前任务结束，再初始化数据库或图片密钥。', parent=app.root)
        return
    previous = getattr(app, 'database_setup_process', None)
    if previous is not None and previous.poll() is None:
        messagebox.showinfo('向导已打开', '请在任务栏打开“首次离线初始化”窗口。', parent=app.root)
        return
    missing = [name for name in REQUIRED_FILES if not (APP_DIR / name).is_file()]
    if missing:
        messagebox.showerror('初始化组件缺失',
                             '请重新安装包含初始化组件的完整安装包。缺少文件：\n' + '\n'.join(missing),
                             parent=app.root)
        return
    if not app.save_base():
        return
    if app.cfg.get('enabled'):
        messagebox.showinfo('请先暂停自动运行', '请先暂停自动运行，再打开密钥初始化向导。', parent=app.root)
        return
    if not app.cfg.get('wechat_dir', '').strip():
        messagebox.showinfo('请选择微信目录', '请先选择包含 db_storage 的微信账号目录。', parent=app.root)
        return
    interpreter = Path(sys.executable).with_name('pythonw.exe')
    if not interpreter.is_file():
        interpreter = Path(sys.executable)
    try:
        process = subprocess.Popen([str(interpreter), str(APP_DIR / 'initialize_offline.pyw')], cwd=APP_DIR)
    except OSError as exc:
        messagebox.showerror('向导启动失败', safe_error(exc), parent=app.root)
        return
    app.database_setup_process = process
    app.status.set('离线初始化向导已打开，请按向导中的步骤操作。')

    def finished():
        if app.closing:
            return
        if process.poll() is None:
            app.root.after(500, finished)
            return
        app.database_setup_process = None
        if app.busy:
            app.root.after(500, finished)
            return
        try:
            app.secrets = load_secrets()
            count = len(app.secrets.get('db_keys', {}))
            image_key = app.secrets.get('image_key_hex', '')
            if 'image_key_hex' in app.fields:
                app.fields['image_key_hex'].set(image_key)
            image_status = '已保存' if image_key else '尚未初始化'
            app.key_status.set(f'本机数据库密钥：{count} 个；图片密钥：{image_status}')
            app.status.set(f'密钥向导已关闭：数据库 {count} 个，图片{image_status}。')
        except Exception as exc:
            messagebox.showerror('读取密钥状态失败', safe_error(exc), parent=app.root)

    app.root.after(500, finished)
