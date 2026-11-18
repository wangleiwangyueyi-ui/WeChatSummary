"""Durable request accounting; no credentials or chat text are stored here."""
from datetime import datetime, timezone
from contextlib import contextmanager
import sqlite3
from zoneinfo import ZoneInfo
from secure_store import BASE


class QuotaExceeded(RuntimeError):
    pass


def quota_day(service, now=None):
    now = now or datetime.now(timezone.utc)
    zone = 'America/Los_Angeles' if service == 'gemini' else 'Asia/Shanghai'
    return now.astimezone(ZoneInfo(zone)).date().isoformat()


def daily_limit(cfg, service, model=''):
    value = cfg.get('gemini_daily_limits',{}).get(model) if service == 'gemini' else cfg.get('pushplus_daily_limit',200)
    return None if value in (None,'') else max(0,int(value))


class UsageTracker:
    def __init__(self, path=None):
        self.path = path or BASE/'api_usage.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, day TEXT, service TEXT, model TEXT, status TEXT, tokens INTEGER DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS baselines (day TEXT, service TEXT, model TEXT, used INTEGER, local_count INTEGER, source TEXT, PRIMARY KEY(day,service,model))')
            db.execute('CREATE INDEX IF NOT EXISTS requests_day ON requests(day,service,model)')
            db.execute('CREATE TABLE IF NOT EXISTS active_credentials (service TEXT PRIMARY KEY, account_id TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS exhausted (day TEXT, service TEXT, model TEXT, PRIMARY KEY(day,service,model))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path,timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _summary(self, db, service, model, day):
        count,tokens = db.execute('SELECT count(*),coalesce(sum(tokens),0) FROM requests WHERE day=? AND service=? AND model=?',(day,service,model)).fetchone()
        base = db.execute('SELECT used,local_count,source FROM baselines WHERE day=? AND service=? AND model=?',(day,service,model)).fetchone()
        used = base[0]+max(0,count-base[1]) if base else count
        blocked = db.execute('SELECT 1 FROM exhausted WHERE day=? AND service=? AND model=?',(day,service,model)).fetchone() is not None
        return dict(day=day,used=used,local=count,tokens=tokens,source=base[2] if base else '本机估算',blocked=blocked)

    def summary(self, service, model='', limit=None, now=None):
        with self.connect() as db:
            result = self._summary(db,service,model,quota_day(service,now))
        result['limit'] = limit
        result['remaining'] = max(0,limit-result['used']) if limit is not None else None
        if result['blocked']:
            result['remaining'] = 0
        result['percent'] = (100*result['remaining']/limit if limit else 0) if limit is not None else None
        return result

    def begin(self, service, model='', limit=None, now=None):
        day = quota_day(service,now)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._summary(db,service,model,day)
            if current['blocked'] or (limit is not None and current['used'] >= limit):
                raise QuotaExceeded(f'{service} 已达到设置的每日额度 {limit} 次，已停止发送；可在额度设置中校准')
            return db.execute('INSERT INTO requests(day,service,model,status) VALUES (?,?,?,?)',(day,service,model,'attempted')).lastrowid

    def finish(self, request_id, success, tokens=None):
        with self.connect() as db:
            db.execute('UPDATE requests SET status=?,tokens=coalesce(?,tokens) WHERE id=?',
                       ('ok' if success else 'failed',None if tokens is None else int(tokens),request_id))

    def calibrate(self, service, used, model='', source='手动校准估算', now=None):
        if int(used) < 0:
            raise ValueError('已用次数不能为负数')
        day = quota_day(service,now)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._summary(db,service,model,day)
            db.execute('INSERT OR REPLACE INTO baselines VALUES (?,?,?,?,?,?)',(day,service,model,int(used),current['local'],source))
            db.execute('DELETE FROM exhausted WHERE day=? AND service=? AND model=?',(day,service,model))

    def active(self, service):
        with self.connect() as db:
            row = db.execute('SELECT account_id FROM active_credentials WHERE service=?',(service,)).fetchone()
        return row[0] if row else 'primary'

    def set_active(self, service, account_id):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO active_credentials VALUES (?,?)',(service,account_id))

    def block_day(self, service, model='', now=None):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO exhausted VALUES (?,?,?)',(quota_day(service,now),service,model))


def format_usage(name, info):
    if info['limit'] is None:
        return f'{name}：已用 {info["used"]} ｜日额度/剩余：待确认'
    return f'{name}：{info["used"]}/{info["limit"]} 次 ｜估余 {info["remaining"]}（{info["percent"]:.1f}%）'
