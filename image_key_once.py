"""One-time, offline-only image key reader. Never imported by daily jobs."""
from collections import Counter
import ctypes
from ctypes import wintypes as wt
import io
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
from Crypto.Cipher import AES

def require_offline():
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        "@(Get-NetAdapter -Physical -ErrorAction Stop | Where-Object Status -eq 'Up').Count"],
        capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or result.stdout.strip() != '0':
        raise RuntimeError('请关闭 Wi-Fi、拔掉网线，保持微信登录后再提取。')

class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress',ctypes.c_uint64),('AllocationBase',ctypes.c_uint64),
        ('AllocationProtect',wt.DWORD),('_pad1',wt.DWORD),('RegionSize',ctypes.c_uint64),
        ('State',wt.DWORD),('Protect',wt.DWORD),('Type',wt.DWORD),('_pad2',wt.DWORD)]

def samples(account):
    root = Path(account)
    if root.name == 'db_storage':
        root = root.parent
    result = []
    with tempfile.TemporaryDirectory(prefix='wechat_image_probe_') as tmp:
        for path in (root/'msg'/'attach').rglob('*_t.dat'):
            if len(result) >= 24:
                break
            if not 31 < path.stat().st_size < 2*1024*1024:
                continue
            try:
                copied = Path(tmp)/'probe.dat'
                shutil.copy2(path,copied)
                data = copied.read_bytes()
                if data.startswith(bytes.fromhex('070856320807')):
                    result.append(data)
            except OSError:
                continue
    if len(result) < 2:
        raise RuntimeError('本机 V2 图片样本不足。请联网打开两张聊天图片，再断网重试。')
    return result

def validate(key, probes):
    cipher = AES.new(key,AES.MODE_ECB)
    matches = 0
    for data in probes[:6]:
        first = cipher.decrypt(data[15:31])
        if first.startswith((b'\xff\xd8\xff',b'\x89PNG',b'GIF8',b'wxgf',b'RIFF')):
            matches += 1
    return matches >= 2

def find_xor(key, probes):
    from message_parser import decode_image, ocr_image
    from PIL import Image
    votes = Counter()
    for data in probes:
        if not AES.new(key,AES.MODE_ECB).decrypt(data[15:31]).startswith(b'\xff\xd8\xff'):
            continue
        for offset in (2,26):
            a,b = data[-offset:-offset+2] if offset>2 else data[-2:]
            if a^0xff == b^0xd9:
                votes[a^0xff] += 1
    # Verify the entire JPEG, not only an apparent marker at the tail.
    for value,_ in votes.most_common():
        good = 0
        for data in probes[:8]:
            try:
                plain = ocr_image(decode_image(data,key.hex(),value))
                with Image.open(io.BytesIO(plain)) as img:
                    img.load()
                good += 1
            except Exception:
                continue
        if good >= 2:
            return value,good
    raise RuntimeError('AES 候选已找到，但图片尾部密钥未通过校验。请打开两张普通聊天图片后重试。')

def extract(account, progress):
    require_offline()
    probes = samples(account)
    result = subprocess.run(['tasklist','/FI','IMAGENAME eq Weixin.exe','/FO','CSV','/NH'],
        capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
    import csv
    processes = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row)>=5 and row[0].lower() == 'weixin.exe':
            processes.append((int(re.sub(r'\D','',row[4]) or '0'),int(row[1])))
    if not processes:
        raise RuntimeError('没有找到运行中的微信，请先登录微信再断网。')
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes = [wt.DWORD,wt.BOOL,wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.ReadProcessMemory.argtypes = [wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    kernel.VirtualQueryEx.argtypes = [wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
    kernel.VirtualQueryEx.restype = ctypes.c_size_t
    pattern = re.compile(rb'(?<![A-Za-z0-9])([A-Za-z0-9]{32}|[A-Za-z0-9]{16})(?![A-Za-z0-9])')
    wide = re.compile(rb'(?:[A-Za-z0-9]\x00){16,32}')
    seen = set()
    deadline = time.monotonic()+180
    last_check = 0
    for _,pid in sorted(processes,reverse=True):
        require_offline()
        handle = kernel.OpenProcess(0x0400|0x0010,False,pid)
        if not handle:
            continue
        try:
            address = 0
            while address < 0x0000800000000000 and time.monotonic()<deadline:
                if time.monotonic()-last_check>5:
                    require_offline()
                    last_check = time.monotonic()
                    progress('正在断网读取并验证图片密钥候选…')
                info = MBI()
                if not kernel.VirtualQueryEx(handle,ctypes.c_void_p(address),ctypes.byref(info),ctypes.sizeof(info)):
                    break
                next_address = info.BaseAddress+info.RegionSize
                if next_address <= address:
                    break
                if info.State == 0x1000 and info.Protect & 0xff in (0x02,0x04,0x08,0x20,0x40,0x80) and not info.Protect & 0x100:
                    for offset in range(0,info.RegionSize,4*1024*1024):
                        if time.monotonic()>=deadline:
                            break
                        if time.monotonic()-last_check>5:
                            require_offline()
                            last_check = time.monotonic()
                        size = min(4*1024*1024+64,info.RegionSize-offset)
                        buf,read = ctypes.create_string_buffer(size),ctypes.c_size_t()
                        if not kernel.ReadProcessMemory(handle,ctypes.c_void_p(info.BaseAddress+offset),buf,size,ctypes.byref(read)):
                            continue
                        data = buf.raw[:read.value]
                        candidates = (m[1][:16] for m in pattern.finditer(data))
                        import itertools
                        for key in itertools.chain(candidates,(m[0][::2][:16] for m in wide.finditer(data))):
                            if time.monotonic() >= deadline:
                                break
                            if key in seen:
                                continue
                            seen.add(key)
                            if validate(key,probes):
                                require_offline()
                                xor,count = find_xor(key,probes)
                                return key.hex(),xor,count
                address = next_address
        finally:
            kernel.CloseHandle(handle)
    raise RuntimeError('未找到通过校验的图片密钥。请联网打开两张近期聊天图片并保留大图窗口，再断网重试。')
