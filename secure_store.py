"""Local configuration. Secrets are protected by the current Windows user's DPAPI."""
import base64
import copy
import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path

from app_paths import DATA_DIR
BASE = DATA_DIR
CONFIG = BASE / 'config.json'
VAULT = BASE / 'secrets.dpapi'
DEFAULT = dict(wechat_dir='',
    proxy_url='', model='gemini-3.5-flash-lite', enabled=False,
    schedule_times='17:50, 21:30', selected_groups={}, enable_image_ocr=False,
    completed_slots=[], last_run_status='等待离线密钥初始化', max_api_calls=100,
    min_request_interval_seconds=6, enable_voice_asr=False, export_dir='',
    gemini_daily_limits={}, pushplus_daily_limit=200)

class Blob(ctypes.Structure):
    _fields_ = [('size', wt.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def protect(raw, decrypt=False):
    buf = ctypes.create_string_buffer(raw)
    src = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    lib = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = lib.CryptUnprotectData if decrypt else lib.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wt.BOOL
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(dst.data, dst.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(dst.data)

def atomic_bytes(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.new')
    with tmp.open('wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)

def load_config():
    cfg = copy.deepcopy(DEFAULT)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding='utf-8')))
    return cfg

def save_config(cfg):
    atomic_bytes(CONFIG, json.dumps(cfg, ensure_ascii=False, indent=2).encode('utf-8'))

def load_secrets():
    return json.loads(protect(VAULT.read_bytes(), True)) if VAULT.exists() else {}

def save_secrets(values):
    atomic_bytes(VAULT, protect(json.dumps(values).encode('utf-8')))

def safe_error(exc, secrets=None):
    text = str(exc)
    def values(data):
        if isinstance(data,dict):
            for child in data.values():
                yield from values(child)
        elif isinstance(data,(list,tuple)):
            for child in data:
                yield from values(child)
        elif isinstance(data,str):
            yield data
    for value in values(secrets or {}):
        if isinstance(value, str) and len(value) > 8:
            text = text.replace(value, '[已隐藏]')
    import re
    text = re.sub(r'AIza[\w-]+|[a-fA-F0-9]{64,}', '[已隐藏]', text)
    return text[:1200]
