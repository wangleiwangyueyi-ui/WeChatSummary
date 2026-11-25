"""One-time offline setup. Explicit button click is required before process reads."""
import ctypes
import json
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from app_paths import APP_DIR
from secure_store import BASE, load_config, load_secrets, save_secrets, safe_error


def image_wizard_class():
    # Loading the legacy image helper does not read any process memory.
    from importlib.machinery import SourceFileLoader
    return SourceFileLoader('image_setup_helper', str(APP_DIR/'initialize_images.pyw')).load_module().ImageWizard

def ps(command):
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Windows 网络/进程检查失败，请保持网络状态不变并联系开发助手')
    return result.stdout.strip()

def require_offline():
    code = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); @(Get-NetAdapter -Physical -ErrorAction Stop | Where-Object Status -eq 'Up').Count"
    count = ps(code)
    if not count.isdigit() or int(count) != 0:
        raise RuntimeError('尚有物理网络适配器处于连接状态。请关闭 Wi-Fi、拔掉网线后再试。')

class Wizard:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        root.title('微信群聊总结管家 · 数据库与图片密钥初始化')
        root.geometry('850x650')
        root.protocol('WM_DELETE_WINDOW', self.close)
        ttk.Label(root,text='数据库与图片密钥 · 离线初始化',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w',padx=22,pady=16)
        text = ('1. 暂停总结助手自动运行；保持微信登录，先浏览需要汇总的群。\n'
                '   如需图片密钥，先打开两张近期普通聊天图片，保留一张大图窗口。\n'
                '2. 关闭 Wi-Fi、拔掉网线，保持微信运行。\n'
                '3. 可单独提取，或依次提取两类密钥；成功的结果分别加密保存在本机。\n'
                '4. 两类操作完成后，从微信菜单退出微信，再清理日志与临时组件。\n'
                '5. 保存其他工作，自行重启电脑，再联网打开本软件。\n\n'
                '此步骤只读取本机微信进程，不注入、不写入进程；断网不等于零风险。\n'
                '两类密钥互不替代，兼容性以实际数据库和图片校验结果为准。')
        ttk.Label(root,text=text,justify='left',wraplength=710).pack(anchor='w',padx=22)
        self.key_state = tk.StringVar()
        ttk.Label(root,textvariable=self.key_state,font=('Microsoft YaHei UI',11,'bold')).pack(anchor='w',padx=22,pady=10)
        self.refresh_state()
        buttons = ttk.Frame(root)
        buttons.pack(fill='x',padx=20,pady=18)
        ttk.Button(buttons,text='提取数据库密钥',command=lambda:self.run(self.extract)).pack(side='left',padx=4)
        ttk.Button(buttons,text='提取图片密钥',command=lambda:self.run(self.extract_images)).pack(side='left',padx=4)
        ttk.Button(buttons,text='依次提取两类密钥',command=lambda:self.run(self.extract_both)).pack(side='left',padx=4)
        ttk.Button(buttons,text='清理日志与临时组件',command=lambda:self.run(self.cleanup)).pack(side='left',padx=4)
        self.log = tk.Text(root,wrap='word',font=('Microsoft YaHei UI',10))
        self.log.pack(fill='both',expand=True,padx=20,pady=(0,20))
        self.root.after(100,self.poll)

    def refresh_state(self):
        saved = load_secrets()
        self.key_state.set(f'已保存数据库密钥：{len(saved.get("db_keys", {}))} 个    图片密钥：'+('已保存' if saved.get('image_key_hex') else '未保存'))

    def module(self):
        return image_wizard_class().module(self)

    def extract_images(self):
        image_wizard_class().extract(self)

    def extract_both(self):
        failed = []
        for name, operation in (('数据库', self.extract), ('图片', self.extract_images)):
            require_offline()
            self.events.put(f'开始提取{name}密钥…')
            try:
                operation()
            except Exception as exc:
                failed.append(name)
                self.events.put(f'{name}步骤失败：'+safe_error(exc))
        if failed:
            raise RuntimeError('未完成：'+'、'.join(failed)+'。已成功的结果已单独保存，可单独重试失败项。')

    def close(self):
        if self.busy:
            messagebox.showinfo('正在执行','请等待当前步骤结束再关闭。')
        else:
            self.root.destroy()

    def poll(self):
        while not self.events.empty():
            value = self.events.get()
            if value is None:
                self.busy = False
                self.refresh_state()
            else:
                self.log.insert('end',value+'\n')
                self.log.see('end')
        self.root.after(100,self.poll)

    def run(self, fn):
        if self.busy:
            return
        self.busy = True
        def worker():
            try:
                require_offline()
                if load_config().get('enabled'):
                    raise RuntimeError('请先在总结助手中暂停自动运行。')
                fn()
            except Exception as exc:
                self.events.put('失败：'+safe_error(exc))
            finally:
                self.events.put(None)
        threading.Thread(target=worker,daemon=True).start()

    def extract(self):
        if not (APP_DIR/'bootstrap'/'key.py').exists():
            raise RuntimeError('临时提取工具已移除。如需重新初始化，请联系开发助手。')
        from bootstrap.key import KeyExtractor
        from db_reader import storage
        cfg = load_config()
        ex = KeyExtractor(str(storage(cfg)),progress=self.events.put)
        values = ex.extract() # no plaintext file, no key logging
        require_offline()
        essential = [item for item in ex.db_files if Path(item['path']).name == 'contact.db'
                     or re.fullmatch(r'message_\d+\.db',Path(item['path']).name)]
        missing = [Path(i['path']).name for i in essential if i['salt'] not in values]
        saved = load_secrets()
        saved.setdefault('db_keys',{}).update(values)
        if values:
            save_secrets(saved)
        receipt = dict(found=len(values),required=len(essential),missing=missing,success=bool(essential) and not missing)
        (BASE/'initialization_status.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        if missing or not essential:
            raise RuntimeError(f'验证通过 {len(values)} 个密钥；仍缺少必要数据库：{", ".join(missing) or "未发现联系人/消息库"}。保持微信登录，可联系作者提供此错误说明。')
        self.events.put(f'成功：{len(values)} 个数据库密钥已验证并加密保存。如需图片密钥，请先完成图片步骤再退出微信清理。')

    def cleanup(self):
        running = ps("@(Get-Process Weixin,WeChat -ErrorAction SilentlyContinue).Count")
        if running != '0':
            raise RuntimeError('请先从微信菜单选择“退出微信”。关闭微信窗口可能仍在后台运行。')
        image_receipt = BASE/'image_initialization_status.json'
        image_status = json.loads(image_receipt.read_text(encoding='utf-8')) if image_receipt.exists() else {}
        if image_status.get('success') and (APP_DIR/'image_key_once.py').is_file():
            image_wizard_class().cleanup(self)
        receipt_file = BASE/'initialization_status.json'
        receipt = json.loads(receipt_file.read_text(encoding='utf-8')) if receipt_file.exists() else {}
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(APP_DIR/'clear_wechat_logs.ps1')],
            capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('日志清理失败，部分文件可能被占用；没有移除临时工具')
        receipt['log_cleanup'] = result.stdout.strip()
        if 'NOT_PRESENT' in result.stdout:
            self.events.put('已核查：你指定的微信 xlog 目录不存在，没有可删除的文件。')
        else:
            self.events.put('已清空指定的微信 xlog 日志目录。')
        if receipt.get('success') and (APP_DIR/'bootstrap').exists():
            target = (APP_DIR/'bootstrap').resolve()
            if target.parent != APP_DIR.resolve() or target.is_symlink():
                raise RuntimeError('临时工具路径验证失败')
            if any(p.is_symlink() or p.is_junction() for p in target.rglob('*')):
                raise RuntimeError('临时工具目录含链接，停止清理')
            shutil.rmtree(target)
            receipt['temporary_tool_removed'] = True
            self.events.put('一次性提取组件已移除。请保存其他工作并手动重启，然后联网打开本软件。')
        else:
            self.events.put('数据库初始化尚未成功，临时工具保留供排查。')
        receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    root = tk.Tk()
    Wizard(root)
    root.mainloop()
