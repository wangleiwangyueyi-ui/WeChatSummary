"""Read-only file snapshots and offline SQLCipher 4 decoding. No process access."""
import hashlib
import hmac
import shutil
import sqlite3
import struct
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from Crypto.Cipher import AES
from task_control import check_cancel,Cancelled

PAGE = 4096
HEADER = b'SQLite format 3\0'

def checksum(data, state=(0, 0), endian='<'):
    if len(data) % 8:
        raise ValueError('WAL 校验长度无效')
    a, b = state
    words = struct.unpack(endian + str(len(data)//4) + 'I', data)
    for i in range(0, len(words), 2):
        a = (a + words[i] + b) & 0xffffffff
        b = (b + words[i+1] + a) & 0xffffffff
    return a, b

class Cipher:
    def __init__(self, key, salt):
        self.key = key
        self.mac = hashlib.pbkdf2_hmac('sha512', key, bytes(v ^ 0x3a for v in salt), 2, 32)

    def page(self, raw, number):
        if len(raw) != PAGE or number < 1:
            raise ValueError('数据库页长度或页号无效')
        offset = 16 if number == 1 else 0
        digest = hmac.new(self.mac, raw[offset:4032] + struct.pack('<I', number), 'sha512').digest()
        if not hmac.compare_digest(digest, raw[4032:4096]):
            raise ValueError(f'第 {number} 页完整性验证失败：密钥不匹配或数据库快照发生变化')
        out = AES.new(self.key, AES.MODE_CBC, raw[4016:4032]).decrypt(raw[offset:4016])
        return (HEADER if number == 1 else b'') + out + raw[4016:]

def decrypt_snapshot(raw_path, wal_path, output, key_hex, cancel=None):
    check_cancel(cancel)
    with open(raw_path, 'rb') as src:
        salt = src.read(16)
        src.seek(0)
        cipher = Cipher(bytes.fromhex(key_hex), salt)
        with open(output, 'w+b') as dst:
            number = 1
            while raw := src.read(PAGE):
                check_cancel(cancel)
                dst.write(cipher.page(raw, number))
                number += 1
            if wal_path.exists() and wal_path.stat().st_size:
                with wal_path.open('rb') as wal:
                    header = wal.read(32)
                    if len(header) != 32:
                        raise ValueError('WAL 文件头不完整，请重试')
                    magic, version, page_size = struct.unpack('>III', header[:12])
                    if magic not in (0x377f0682, 0x377f0683) or version != 3007000 or page_size != PAGE:
                        raise ValueError('不支持的 WAL 格式')
                    endian = '<' if magic == 0x377f0682 else '>'
                    state = checksum(header[:24], endian=endian)
                    if state != struct.unpack('>II', header[24:]):
                        raise ValueError('WAL 文件头校验失败')
                    committed = []
                    pending = []
                    final_size = 0
                    while frame := wal.read(24 + PAGE):
                        check_cancel(cancel)
                        if len(frame) != 24 + PAGE or frame[8:16] != header[16:24]:
                            break # uncommitted/tail of previous WAL generation
                        expected = checksum(frame[:8] + frame[24:], state, endian)
                        if expected != struct.unpack('>II', frame[16:24]):
                            break
                        state = expected
                        pg, db_size = struct.unpack('>II', frame[:8])
                        if not pg:
                            raise ValueError('WAL 页号为零')
                        pending.append((pg, wal.tell() - PAGE))
                        if db_size:
                            committed.extend(pending)
                            pending = []
                            final_size = db_size
                    for pg, offset in committed:
                        check_cancel(cancel)
                        wal.seek(offset)
                        decoded = cipher.page(wal.read(PAGE), pg)
                        dst.seek((pg-1)*PAGE)
                        dst.write(decoded)
                    if final_size:
                        dst.truncate(final_size * PAGE)

def stamp(paths):
    return [(p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in paths]

@contextmanager
def snapshot(source, keys, cancel=None):
    check_cancel(cancel)
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f'找不到数据库：{source}')
    last_error = None
    for attempt in range(3):
        with tempfile.TemporaryDirectory(prefix='wechat_summary_') as tmp:
            tmp = Path(tmp)
            paths = [source, Path(str(source) + '-wal')]
            raw, wal, output = tmp/'raw.db', tmp/'raw.db-wal', tmp/'plain.db'
            conn = None
            try:
                check_cancel(cancel)
                before = stamp(paths)
                shutil.copy2(source, raw)
                if paths[1].exists():
                    shutil.copy2(paths[1], wal)
                check_cancel(cancel)
                if stamp(paths) != before:
                    raise ValueError('复制时数据库发生变化')
                with raw.open('rb') as f:
                    salt = f.read(16)
                if salt == HEADER:
                    shutil.copy2(raw, output)
                    if wal.exists():
                        shutil.copy2(wal, str(output)+'-wal')
                else:
                    key = keys.get(salt.hex())
                    if not key:
                        raise KeyError(f'{source.name} 缺少已验证密钥，请完成一次性离线初始化')
                    decrypt_snapshot(raw, wal, output, key, cancel)
                check_cancel(cancel)
                conn = sqlite3.connect(output)
                if cancel is not None:
                    conn.set_progress_handler(lambda:int(cancel.is_set()),1000)
                conn.execute('PRAGMA query_only=ON')
                if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    conn.close()
                    raise ValueError('解密后的数据库完整性检查未通过')
            except Cancelled:
                if conn is not None:
                    conn.close()
                raise
            except (OSError, sqlite3.Error, ValueError) as exc:
                if conn is not None:
                    conn.close()
                check_cancel(cancel)
                last_error = exc
                if attempt < 2:
                    if cancel is None:time.sleep(.2)
                    else:cancel.wait(.2)
                continue
            try:
                conn.row_factory = sqlite3.Row
                yield conn
            except sqlite3.Error:
                check_cancel(cancel)
                raise
            finally:
                conn.close()
            return
    raise RuntimeError(f'{source.name} 无法取得一致快照：{last_error}')

def storage(cfg):
    root = Path(cfg['wechat_dir'])
    if root.name == 'db_storage':
        return root
    result = root/'db_storage'
    if not result.is_dir():
        raise ValueError('请选择微信 4.x 账号目录（其下应有 db_storage）。旧版目录需另行适配。')
    return result

def contacts(cfg, secrets, cancel=None):
    result = {}
    with snapshot(storage(cfg)/'contact'/'contact.db', secrets.get('db_keys', {}), cancel) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('contact', 'stranger', 'chat_room'):
            if table not in tables:
                continue
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            if 'username' not in cols:
                continue
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                check_cancel(cancel)
                d = dict(row)
                uid = d['username']
                if not uid:
                    continue
                old = result.get(uid, {})
                result[uid] = {**d, **old}
    return result

def display(contact, uid):
    row = contact.get(uid, {})
    return row.get('remark') or row.get('nick_name') or row.get('alias') or uid or '未知发送人'

def latest_update(cfg):
    files = list((storage(cfg)/'message').glob('message_[0-9]*.db'))
    files += [Path(str(p)+'-wal') for p in files]
    return max((p.stat().st_mtime for p in files if p.exists()), default=0)

def messages(cfg, secrets, rooms, start, end, progress=lambda _: None, cancel=None):
    check_cancel(cancel)
    if start > end:
        raise ValueError('起始时间不能晚于结束时间')
    files = sorted((storage(cfg)/'message').glob('message_[0-9]*.db'))
    if not files:
        raise FileNotFoundError('没有找到 message_N.db 历史分库')
    for i, source in enumerate(files):
        progress({'percent':3+50*i/len(files),'stage':'本地预检 / 读取数据库',
                  'text':f'读取历史分库 {i+1}/{len(files)}：{source.name}'})
        with snapshot(source, secrets.get('db_keys', {}), cancel) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            names = dict(conn.execute('SELECT rowid,user_name FROM Name2Id')) if 'Name2Id' in tables else {}
            room_tables = [(room,'Msg_' + hashlib.md5(room.encode()).hexdigest()) for room in rooms]
            room_tables = [(room,table) for room,table in room_tables if table in tables]
            total = sum(conn.execute(f'SELECT count(*) FROM "{table}" WHERE create_time>=? AND create_time<=?',(start,end)).fetchone()[0]
                        for _,table in room_tables)
            scanned = 0
            last_progress = 0
            for room, table in room_tables:
                for row in conn.execute(f'SELECT * FROM "{table}" WHERE create_time>=? AND create_time<=? ORDER BY create_time,local_id', (start,end)):
                    check_cancel(cancel)
                    scanned += 1
                    if scanned == 1 or scanned == total or time.monotonic()-last_progress >= .25:
                        progress({'percent':3+50*(i+scanned/max(1,total))/len(files),'stage':'本地预检 / 解析消息',
                                  'text':f'分库 {i+1}/{len(files)} · 消息 {scanned}/{total}（含图片和语音处理）'})
                        last_progress = time.monotonic()
                    item = dict(row)
                    item['room'] = room
                    item['sender'] = names.get(item.get('real_sender_id'), '')
                    item['shard'] = source.name
                    yield item
            progress({'percent':3+50*(i+1)/len(files),'stage':'本地预检',
                      'text':f'历史分库 {i+1}/{len(files)} 解析完毕'})
