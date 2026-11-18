"""Explicit offline handoff for the independent image key."""
import importlib.util
import json
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from app_paths import APP_DIR
from secure_store import BASE, load_config, load_secrets, save_secrets, safe_error, atomic_bytes

class ImageWizard:
    def __init__(self, root):
        self.root,self.busy,self.events = root,False,queue.Queue()
        root.title('微信图片密钥 · 一次性断网初始化')
        root.geometry('790x570')
        root.protocol('WM_DELETE_WINDOW', self.close)
        ttk.Label(root,text='图片密钥初始化',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w',padx=20,pady=15)
        ttk.Label(root,text=('1. 联网登录微信，点开两张近期普通聊天图片，保留其中一张的大图窗口。\n'
            '2. 暂停总结管家的自动运行；关闭 Wi-Fi、拔掉网线，保持微信运行。\n'
            '3. 点击“断网提取图片密钥”。最多等待 3 分钟，密钥只加密保存在本机。\n'
            '4. 显示校验成功后，从微信菜单退出微信，再点击“清理日志与临时组件”。\n'
            '5. 保存其他工作并重启电脑，联网后打开本软件。\n\n'
            '仅在此按钮触发的一次性步骤读取微信内存，不注入、不写入进程。\n'
            '断网不能保证零风险；日常运行不调用此提取组件。'),
            wraplength=740,justify='left',font=('Microsoft YaHei UI',10)).pack(anchor='w',padx=20)
        bar = ttk.Frame(root)
        bar.pack(fill='x',padx=20,pady=16)
        ttk.Button(bar,text='断网提取图片密钥',command=lambda:self.run(self.extract)).pack(side='left',padx=4)
        ttk.Button(bar,text='清理日志与临时组件',command=lambda:self.run(self.cleanup)).pack(side='left',padx=4)
        self.log = tk.Text(root,wrap='word',font=('Microsoft YaHei UI',10))
        self.log.pack(fill='both',expand=True,padx=20,pady=(0,20))
        self.root.after(100,self.poll)

    def module(self):
        path = APP_DIR/'image_key_once.py'
        if not path.is_file():
            raise RuntimeError('一次性提取组件已移除。图片密钥已保存时无需重复初始化。')
        spec = importlib.util.spec_from_file_location('image_key_once',path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run(self, operation):
        if self.busy:
            return
        self.busy = True
        def worker():
            try:
                operation()
            except Exception as exc:
                self.events.put('失败：'+safe_error(exc))
            finally:
                self.events.put(None)
        threading.Thread(target=worker,daemon=True).start()

    def extract(self):
        module = self.module()
        cfg = load_config()
        if cfg.get('enabled'):
            raise RuntimeError('请先在总结管家中暂停自动运行。')
        key,xor,count = module.extract(cfg['wechat_dir'],self.events.put)
        module.require_offline()
        secrets = load_secrets()
        secrets.update(image_key_hex=key,image_xor_key=xor)
        save_secrets(secrets)
        atomic_bytes(BASE/'image_initialization_status.json',json.dumps(
            {'success':True,'validated_images':count,'temporary_tool_removed':False}).encode('utf-8'))
        self.events.put(f'成功：{count} 张真实图片解密通过，图片密钥已加密保存。请退出微信后点击清理。')

    def cleanup(self):
        module = self.module()
        module.require_offline()
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            '@(Get-Process Weixin,WeChat -ErrorAction SilentlyContinue).Count'],capture_output=True,
            text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or result.stdout.strip() != '0':
            raise RuntimeError('请从微信菜单退出微信。仅关闭聊天窗口不算退出。')
        receipt_file = BASE/'image_initialization_status.json'
        receipt = json.loads(receipt_file.read_text(encoding='utf-8')) if receipt_file.exists() else {}
        if not receipt.get('success'):
            raise RuntimeError('图片密钥尚未校验成功，暂不移除提取组件。')
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(APP_DIR/'clear_wechat_logs.ps1')],capture_output=True,text=True,timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('指定日志目录清理失败，请保持断网并联系作者。')
        receipt['log_cleanup'] = result.stdout.strip()
        target = (APP_DIR/'image_key_once.py').resolve()
        if target.parent != APP_DIR.resolve() or target.is_symlink():
            raise RuntimeError('临时组件路径验证失败')
        target.unlink()
        for cached in (APP_DIR/'__pycache__').glob('image_key_once.*.pyc'):
            if cached.resolve().parent == (APP_DIR/'__pycache__').resolve() and not cached.is_symlink():
                cached.unlink()
        receipt['temporary_tool_removed'] = True
        atomic_bytes(receipt_file,json.dumps(receipt,ensure_ascii=False,indent=2).encode('utf-8'))
        self.events.put(('指定日志目录不存在，已核查无可删文件。' if 'NOT_PRESENT' in result.stdout else '指定日志目录已清空。')+
                       '临时图片提取组件已移除。请保存工作并重启，联网后打开本软件。')

    def poll(self):
        while not self.events.empty():
            value = self.events.get()
            if value is None:
                self.busy = False
            else:
                self.log.insert('end',value+'\n')
                self.log.see('end')
        self.root.after(100,self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('正在执行','请等待当前步骤结束。')
        else:
            self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    ImageWizard(root)
    root.mainloop()
