"""Non-blocking update and optional-media installer dialog."""
import importlib.util
import queue
import subprocess
import threading
import webbrowser
import customtkinter as ctk
from tkinter import messagebox
from app_paths import APP_DIR, DATA_DIR, INSTALLED, MODEL_DIR
from version import VERSION
from update_service import read_release, choose_asset, download_verified, RELEASES_URL
from macos_dialogs import dialog, reveal, frame, label, button
from macos_theme import font, MACOS_THEME as T


def show_updates(app, components=False):
    existing = getattr(app, '_updates_window', None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        return existing
    window = dialog(app.root, '图片 / 语音组件' if components else '检查软件更新', 660, 500, (580, 430))
    app._updates_window = window
    window.grid_rowconfigure(2, weight=1)
    window.grid_columnconfigure(0, weight=1)
    title = '可选本地识别组件' if components else f'软件更新 · 当前 v{VERSION}'
    label(window, title, size='dialog_title_size', bold=True).grid(row=0,column=0,sticky='w',padx=20,pady=(18,8))
    status = label(window, '正在检查 GitHub 发布版本…', muted=True)
    status.grid(row=1,column=0,sticky='w',padx=20,pady=(0,8))
    body = ctk.CTkTextbox(window,font=font('dialog_body_size'),fg_color=T['bg_card'],text_color=T['text'],wrap='word')
    body.grid(row=2,column=0,sticky='nsew',padx=20,pady=4)
    bar = ctk.CTkProgressBar(window,height=6,progress_color=T['primary'])
    bar.grid(row=3,column=0,sticky='ew',padx=20,pady=10)
    bar.set(0)
    actions=frame(window)
    actions.grid(row=4,column=0,sticky='ew',padx=20,pady=(0,16))
    button(actions,'发布页面 ↗',lambda:webbrowser.open(RELEASES_URL),width=110).pack(side='left')
    state = {'asset':None,'path':None,'working':True}
    events, stop = queue.Queue(), threading.Event()

    def close():
        stop.set()
        window.destroy()

    def run(fn, kind):
        state['working']=True
        action.configure(state='disabled')
        def worker():
            try:
                events.put((kind,fn()))
            except Exception as exc:
                events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def install():
        if app.busy:
            messagebox.showinfo('任务正在运行','请等待当前任务结束后再安装。下载的文件会保留。',parent=window)
            return
        if not messagebox.askokcancel('安装更新','将退出本软件并打开安装向导。你的配置与密钥会保留。',parent=window):
            return
        try:
            args=[str(state['path']), '/NORESTART']
            if INSTALLED:
                args.append('/DIR='+str(APP_DIR))
            subprocess.Popen(args, cwd=state['path'].parent)
        except OSError as exc:
            messagebox.showerror('无法打开安装包',str(exc),parent=window)
            return
        stop.set()
        app.exit()

    def download():
        if state['path']:
            install()
            return
        status.configure(text='正在下载；关闭窗口可取消。')
        run(lambda:download_verified(state['asset'],DATA_DIR/'updates',
            lambda n,total:events.put(('progress',(n,total))),stop.is_set), 'downloaded')

    action=button(actions,'下载并校验',download,width=128,primary=True)
    action.pack(side='right')
    action.configure(state='disabled')
    button(actions,'关闭',close,width=72).pack(side='right',padx=8)
    window.protocol('WM_DELETE_WINDOW',close)

    def poll():
        if stop.is_set() or not window.winfo_exists():
            return
        while not events.empty():
            kind,value=events.get_nowait()
            if kind=='release':
                state['working']=False
                state['asset']=choose_asset(value,INSTALLED,components)
                size=state['asset']['size']/1024**2
                info = f'最新版本：v{value["version"]}\n下载大小：{size:.1f} MB\n\n'
                if components:
                    ocr=importlib.util.find_spec('rapidocr_onnxruntime') is not None
                    voice=importlib.util.find_spec('sherpa_onnx') is not None and (MODEL_DIR/'model.int8.onnx').is_file()
                    info += f'图片 OCR：{"已安装" if ocr else "未安装"}；本地语音：{"已安装" if voice else "未安装"}\n\n'
                    info += '组件只需安装一次。安装后重新打开软件，勾选“本地图片 OCR / 本地语音转写”并保存。识别在本机完成，不消耗 Gemini 调用。\n\n'
                else:
                    info += '更新保留个人配置、密钥和群聊选择。相同运行环境优先下载小型程序更新包。\n\n'
                info += value['notes']
                body.configure(state='normal');body.delete('1.0','end');body.insert('end',info);body.configure(state='disabled')
                status.configure(text='发现新版本' if value['newer'] else '当前已是最新正式版本')
                action.configure(state='normal' if value['newer'] or components else 'disabled')
            elif kind=='progress':
                n,total=value;bar.set(n/total)
                status.configure(text=f'下载中 {n/total:.0%} · {n/1024**2:.1f}/{total/1024**2:.1f} MB')
            elif kind=='downloaded':
                state.update(path=value,working=False)
                bar.set(1);status.configure(text='SHA-256 校验通过；点击安装后退出软件。')
                action.configure(text='退出并安装',state='normal')
            elif kind=='error':
                state['working']=False
                status.configure(text='检查或下载未完成')
                body.configure(state='normal');body.delete('1.0','end')
                body.insert('end',value+'\n\n可点击“发布页面”手动下载；GitHub 连接失败不会影响日常汇总。')
                body.configure(state='disabled')
                if state['asset']:action.configure(state='normal')
        window.after(100,poll)

    # Choose/validate the component in the worker so malformed releases cannot
    # break Tk's event loop.
    def check():
        value=read_release()
        choose_asset(value,INSTALLED,components)
        return value
    run(check,'release')
    window.after(100,poll)
    reveal(window)
    return window
