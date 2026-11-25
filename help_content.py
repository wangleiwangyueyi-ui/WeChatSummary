"""Shared help content for the desktop guide and its offline HTML edition."""
from html import escape
import re
from app_info import HELP_TEXT,APP_NAME,AUTHOR_EMAIL


def section(number):
    match=re.search(r'^'+number+r'、(.+?)\n(.*?)(?=^[一二三四五六七]、|^官方参考|\Z)',HELP_TEXT,re.M|re.S)
    return {'kind':'text','title':match[1],'body':match[2].strip()}


CONFIG_ROWS=[
    ('微信账号目录','本机微信 4.x 账号文件夹','读取本机已经同步的消息'),
    ('Gemini API Key','Google AI Studio → API keys','云端总结；只导出时不需要'),
    ('PushPlus 用户 Token','PushPlus → 我的 → 开发设置','把总结发送到对应微信账号'),
    ('PushPlus secretKey','同一账号的开发设置','只用于官网额度同步，不是发送 Token'),
    ('V2 图片密钥','本机“数据库 / 图片密钥”向导','解码 V2 图片必需，可单独提取或与数据库依次提取'),
    ('代理地址 / 模型','本地可用代理 / 账号可用模型','代理配置只供 Gemini 使用'),
    ('导出文件保存目录','输入完整路径或点击“选择目录”','保存后仅影响新任务'),
]
TASK_ROWS=[
    ('仅导出记录','Markdown 原始记录','Gemini 0 次；PushPlus 0 次'),
    ('总结并推送','摘要 + 复盘 + HTML 阅读版','Gemini 分段/合并；PushPlus 按条数'),
    ('已有摘要本地重排','另存 HTML 阅读副本','Gemini 0 次；PushPlus 0 次'),
    ('同步官网额度','更新官网用量及来源','最多 3 次 PushPlus 查询；不发送消息'),
]
FLOW=[('01','准备与初始化','同步微信记录 → 首次初始化；已完成的电脑跳过初始化'),
      ('02','选择范围','日常页勾选群聊，或历史页选择群、时间和发言人'),
      ('03','本机读取与预检','解析文字 / 图片 / 语音，查看预计 API 次数'),
      ('04','选择结果','仅导出：本机保存；总结推送：确认后分析并发送')]
PAGES=[
    ('快速上手',[
        {'kind':'flow','title':'四步完成一次任务','steps':FLOW},
        {'kind':'table','title':'先选择你要的结果','headers':('操作','得到什么','调用次数'),'rows':TASK_ROWS},
        {'kind':'note','title':'界面怎么找','body':'顶部切换日常、历史和基础配置。右上“额度管理”添加 Key、建立独立额度组和校准用量，“任务管理”查看和取消当前任务。\n搜索输入后自动筛选，也可点击放大镜或按 Enter。历史页的匹配提示显示在搜索框下面，请在右侧选择目标群聊。\n底部细进度条的红色表示正在执行，绿色表示完成，灰色表示等待或已取消。文字会显示当前阶段。\n任务管理里可暂停或撤销定时计划。暂停可恢复，撤销则移除已保存的计划群聊。“取消当前任务”只结束这一轮。已经提交的远端请求不能撤回。'},
    ]),
    ('配置与额度',[
        {'kind':'table','title':'配置对照表','headers':('配置项','从哪里获取 / 设置','用途'),'rows':CONFIG_ROWS},
        {'kind':'note','title':'同组与独立组','body':'同一项目的多个 Key 共享一份额度。另一个独立项目在下拉框选择“＋ 新建独立额度组”。例如两组各 500 次，合计 1000 次；是否免费以该项目的模型和计费状态为准。'},
        {'kind':'note','title':'403：已开启白名单，为什么仍失败？','body':'“已启用”只代表检查已打开。PushPlus 还会核对每次请求的出口 IP。浏览器、直连、代理分流或 TUN 可能使用不同出口。软件的 PushPlus 不使用 Gemini 代理；应核对该用户 Token 对应账号中已保存的白名单。不要关闭白名单来回避排查。'},
        section('三'),section('六'),
        {'kind':'note','title':'模型选择与自动回退','body':'默认模型为 gemini-3.5-flash-lite。下拉框提供 gemini-4-hydrogen、gemini-3.8-flash、gemini-3.5-flash-lite、gemini-3.6-flash（2026-11-18 核对官方定价页）。免费层是否可用及额度以你的项目、地区、模型和计费状态为准。\n优先使用所选模型；遇到 429 / RESOURCE_EXHAUSTED，依次尝试 gemini-3.8-flash 和 gemini-3.5-flash-lite，跳过重复项。所有尝试仍计入单次任务上限，并按模型和独立项目分别记录；服务不可用时无法保证发送成功。\n顶部显示本次实际响应模型；日报末尾列出参与分段和合并的实际模型。额度胶囊仍统计配置中所选模型，更换模型并保存后可查看对应额度。\n官方模型：https://ai.google.dev/gemini-api/docs/models\n免费层与价格：https://ai.google.dev/gemini-api/docs/pricing'},
    ]),
    ('日常与导出',[section('四'),section('五'),section('七'),
        {'kind':'table','title':'这三种“次数”不要混淆','headers':('名称','代表什么','如何查看'),'rows':[
            ('本次预估','这一次任务预计需要的请求','开始总结前的预检提示'),
            ('今日已用','统计日内累计消耗','额度面板 / 官网校准'),
            ('Token 数量','模型处理的文字计量','额度详情；不是 API Key 个数'),
        ]},
    ]),
    ('环境与说明',[section('一'),section('二'),
        {'kind':'note','title':'工具特点','body':'日常不注入、不操控微信；本机 OCR 与语音转写；支持本机已保存的近十年记录批量导出，支持定时汇总。十年按钮不能恢复未同步或已删除的内容。'},
        {'kind':'text','title':'作者与官方入口','body':'作者：Boyce\n联系邮箱：'+AUTHOR_EMAIL+'\nGoogle AI Studio：https://aistudio.google.com/api-keys\nGemini 额度：https://ai.google.dev/gemini-api/docs/rate-limits\nPushPlus：https://www.pushplus.plus/\n开放接口文档：https://www.pushplus.plus/doc/guide/openApi.html'},
    ]),
]

URL_PATTERN = re.compile(r'https?://[A-Za-z0-9:/?#@!$&*+,.=_%~;()\-]+')


def paragraphs(body):
    return [re.sub(r'^\s*\d+[.、]\s*','',p.strip()) for p in body.splitlines() if p.strip()]


def linked_html(text):
    parts=[]
    offset=0
    for match in URL_PATTERN.finditer(text):
        url=match[0].rstrip('.,;')
        parts.extend([escape(text[offset:match.start()]),'<a href="'+escape(url,quote=True)+'" target="_blank" rel="noopener noreferrer">'+escape(url)+'</a>'])
        offset=match.start()+len(url)
    return ''.join(parts)+escape(text[offset:])


def help_html():
    parts=[]
    for i,(name,items) in enumerate(PAGES):
        parts.append(f'<h2 id="p{i}">{escape(name)}</h2>')
        for item in items:
            parts.append('<section><h3>'+escape(item['title'])+'</h3>')
            if item['kind']=='flow':
                parts.append('<div class="flow">')
                for n,title,body in item['steps']:
                    parts.append(f'<div class="step"><b>{n}</b><h4>{escape(title)}</h4><p>{escape(body)}</p></div>')
                parts.append('</div>')
            elif item['kind']=='table':
                parts.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+escape(t)+'</th>' for t in item['headers'])+'</tr></thead><tbody>')
                for row in item['rows']:parts.append('<tr>'+''.join('<td>'+escape(t)+'</td>' for t in row)+'</tr>')
                parts.append('</tbody></table></div>')
            else:
                parts.append('<ol>')
                for para in paragraphs(item['body']):
                    parts.append('<li>'+linked_html(para)+'</li>')
                parts.append('</ol>')
            parts.append('</section>')
    nav=''.join(f'<a href="#p{i}">{escape(name)}</a>' for i,(name,_) in enumerate(PAGES))
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>软件使用说明</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f5f7;color:#1d1d1f;font:16px/1.8 -apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif}main{max-width:1040px;margin:auto;padding:32px 20px}header{padding:12px 4px 24px}h1{font-size:28px;line-height:1.4;margin:0 0 8px}header p{color:#6e6e73;margin:0}nav{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}nav a{padding:7px 14px;border-radius:20px;background:#eaf2ff;color:#0062cc;text-decoration:none}h2{font-size:23px;margin:32px 4px 12px}section{background:white;border:1px solid #e5e5ea;border-radius:16px;padding:22px;margin:12px 0}h3{font-size:18px;margin:0 0 16px}p{margin:10px 0;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:15px}th,td{text-align:left;border-bottom:1px solid #e5e5ea;padding:12px;vertical-align:top}th{background:#f2f2f7}th:first-child,td:first-child{width:24%;font-weight:600}.table-wrap{overflow:auto}.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:24px}.step{position:relative;background:#f5f8ff;border:1px solid #dce8ff;border-radius:12px;padding:14px}.step:not(:last-child):after{content:'→';position:absolute;right:-22px;top:44%;color:#007aff;font-size:22px}.step b{color:#007aff;font-size:22px}.step h4{margin:6px 0}.step p{font-size:14px;color:#6e6e73}@media(max-width:700px){main{padding:20px 12px}section{padding:16px}.flow{grid-template-columns:1fr;gap:26px}.step:not(:last-child):after{content:'↓';right:50%;top:auto;bottom:-28px}th,td{padding:8px;font-size:13px}}
</style></head><body><main><header><h1>软件使用说明</h1><p>微信聊天总结分析助手 V1.0 · Boyce</p>'''+nav+'</header>'+''.join(parts)+'</main></body></html>'
