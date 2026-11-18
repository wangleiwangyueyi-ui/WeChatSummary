"""Optional documented PushPlus usage synchronization."""
import requests
from datetime import datetime
from credentials import bucket
from usage_tracker import UsageTracker
from secure_store import safe_error
from task_control import check_cancel,Cancelled


def query_error(payload, secrets):
    """Keep the provider's diagnosis, but never leak its credentials."""
    code = payload.get('code')
    message = safe_error(Exception(str(payload.get('msg','未提供错误说明'))),secrets)[:180]
    if code == 403:
        advice = ('请求出口 IP 未获授权。已开启白名单也可能出现此错误：软件直连与浏览器/代理的出口不同，'
                  '或网络出口已改变。PushPlus 不使用 Gemini 代理；请核对该 Token 账号中已保存的安全 IP。')
    elif code == 401:
        advice = '请核对对应账号是否已启用开放接口。'
    else:
        advice = '请核对用户 Token、secretKey 与官网设置。'
    return RuntimeError(f'PushPlus 额度查询失败（{code}）：{message}。{advice}')


def sync_pushplus(secrets, tracker=None, account=None, cancel=None):
    check_cancel(cancel)
    tracker = tracker or UsageTracker()
    account = account or {'id':'primary','group':'default','key':secrets.get('pushplus_token',''),
                          'secret_key':secrets.get('pushplus_secret_key','')}
    token, secret = account.get('key',''),account.get('secret_key','')
    scope = bucket(account)
    if not token or not secret:
        raise ValueError('同步需要 PushPlus 用户 Token 和开放接口 secretKey；只用发送 Token 时请使用本机估算或手动校准')
    with requests.Session() as session:
        session.trust_env = False

        def call(method, path, **kwargs):
            check_cancel(cancel)
            request_id = tracker.begin('pushplus_query',scope)
            try:
                response = session.request(method,'https://www.pushplus.plus'+path,timeout=(10,20),**kwargs)
                response.raise_for_status()
                payload = response.json()
                if payload.get('code') != 200:
                    raise query_error(payload,{'saved':secrets,'account':account})
                tracker.finish(request_id,True)
                check_cancel(cancel)
                return payload['data']
            except Cancelled:
                raise
            except Exception:
                tracker.finish(request_id,False)
                raise

        auth = call('POST','/api/common/openApi/getAccessKey',json={'token':token,'secretKey':secret})
        headers = {'access-key':auth['accessKey']}
        counts = call('GET','/api/open/user/sendCount',headers=headers)
        info = call('GET','/api/open/user/myInfo',headers=headers)
        used = int(counts['wechatSendCount'])
        verified = info.get('verifyStatus') == 1
        vip = info.get('vipInfo') or {}
        limit = (2000 if vip.get('isVip') == 1 else 200) if verified else 0
        check_cancel(cancel)
        tracker.calibrate('pushplus',used,scope,source=f'官网同步 {datetime.now():%m-%d %H:%M}，后续本机累加')
        return {'used':used,'limit':limit,'vip':vip.get('isVip') == 1,'verified':verified,
                'account_id':account['id'],'group':account.get('group','default')}
