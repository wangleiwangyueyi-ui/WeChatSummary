"""Ordered credentials with quota shared by project/account, never by key count."""
import copy
import hashlib
import json
from usage_tracker import UsageTracker, daily_limit, QuotaExceeded

PRIMARY_FIELD = {'gemini':'gemini_api_key','pushplus':'pushplus_token'}


def accounts(cfg, secrets, service, include_empty=False):
    primary = dict(id='primary',label='主 Key' if service == 'gemini' else '主 Token',group='default',enabled=True)
    primary.update(copy.deepcopy(secrets.get(service+'_primary',{})))
    primary['id'] = 'primary'
    primary['group'] = 'default'
    primary['key'] = secrets.get(PRIMARY_FIELD[service],'')
    if service == 'pushplus':
        primary['secret_key'] = secrets.get('pushplus_secret_key','')
    result = [primary]+copy.deepcopy(secrets.get(service+'_accounts',[]))
    # Duplicate keys must never gain an extra accounting bucket.
    seen, filtered = set(), []
    for item in result:
        key = item.get('key','').strip()
        item['key'] = key
        item.setdefault('enabled',True)
        item.setdefault('group','default')
        item['group'] = item['group'].strip().casefold() or 'default'
        if key and key in seen:
            continue
        if key or include_empty:
            filtered.append(item)
        if key:
            seen.add(key)
    return filtered


def bucket(account, model=''):
    group = account.get('group','default').strip().casefold() or 'default'
    if group == 'default':
        return model
    digest = hashlib.sha256(group.casefold().encode()).hexdigest()[:24]
    return json.dumps([model,digest],separators=(',',':'))


def account_limit(cfg, account, service, model=''):
    if account.get('group','default').strip().casefold() == 'default':
        return daily_limit(cfg,service,model)
    value = account.get('limits',{}).get(model) if service == 'gemini' else account.get('limit')
    return None if value in (None,'') else max(0,int(value))


def store_accounts(cfg, secrets, service, items):
    """Save a complete edited list, keeping legacy fields compatible."""
    seen = set()
    for item in items:
        key = item.get('key','').strip()
        if key and key in seen:
            raise ValueError('同一个 Key/Token 不能重复添加')
        seen.add(key)
        item['key'] = key
        item['group'] = item.get('group','default').strip().casefold() or 'default'
    primary = next(item for item in items if item['id'] == 'primary')
    secrets[PRIMARY_FIELD[service]] = primary.get('key','')
    secrets[service+'_primary'] = {k:v for k,v in primary.items() if k not in ('key','secret_key')}
    if service == 'pushplus':
        secrets['pushplus_secret_key'] = primary.get('secret_key','')
    secrets[service+'_accounts'] = [copy.deepcopy(item) for item in items if item['id'] != 'primary']


class CredentialPool:
    def __init__(self, cfg, secrets, service, tracker=None, progress=lambda _:None):
        self.cfg,self.service = cfg,service
        self.model = cfg.get('model','') if service == 'gemini' else ''
        self.items = [a for a in accounts(cfg,secrets,service) if a.get('enabled',True)]
        self.tracker,self.progress = tracker or UsageTracker(),progress
        self.blocked_groups = set()

    def info(self, item):
        return self.tracker.summary(self.service,bucket(item,self.model),account_limit(self.cfg,item,self.service,self.model))

    def summary(self):
        """Aggregate enabled independent groups; same-project keys count once."""
        values = {}
        for item in self.items:
            key = bucket(item,self.model)
            if key in values:
                continue
            values[key] = self.info(item)
        unknown = sum(info['limit'] is None for info in values.values())
        limit = None if unknown else sum(info['limit'] for info in values.values())
        remaining = None if any(info['remaining'] is None for info in values.values()) else sum(info['remaining'] for info in values.values())
        return dict(groups=len(values),credentials=len(self.items),unknown_groups=unknown,
                    used=sum(info['used'] for info in values.values()),limit=limit,remaining=remaining,
                    percent=None if unknown else (100*remaining/limit if limit else 0))

    def capacity(self):
        return self.summary()['remaining']

    def choose(self):
        for item in self.items:
            info = self.info(item)
            if bucket(item,self.model) not in self.blocked_groups and not info.get('blocked') and info['remaining'] != 0:
                return item
        raise QuotaExceeded(f'{self.service} 没有可用的已启用凭据或独立额度；请在“＋ 管理”中检查，或等待额度恢复')

    def begin(self):
        for _ in range(len(self.items)+1):
            item = self.choose()
            try:
                request = self.tracker.begin(self.service,bucket(item,self.model),account_limit(self.cfg,item,self.service,self.model))
            except QuotaExceeded:
                continue
            changed = self.tracker.active(self.service) != item['id']
            self.tracker.set_active(self.service,item['id'])
            if changed:
                self.progress({'usage_changed':True,'text':f'{self.service} 当前使用：{item["label"]}（按项目/账号额度统计）'})
            return item,request
        raise QuotaExceeded('凭据额度已用完，请检查额度设置')

    def exhaust(self, item):
        self.blocked_groups.add(bucket(item,self.model))
        self.tracker.block_day(self.service,bucket(item,self.model))
        self.progress({'usage_changed':True,'text':f'{self.service} 的 {item["label"]} 今日额度已耗尽，检查下一组独立额度'})


def active_account(cfg, secrets, service, tracker):
    items = accounts(cfg,secrets,service,include_empty=True)
    current = tracker.active(service)
    return next((a for a in items if a['id'] == current),items[0])
