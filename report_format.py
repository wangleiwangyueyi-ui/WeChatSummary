"""Local, dependency-free reading layout. No API requests or semantic rewriting."""
from html import escape
from pathlib import Path
import re
from urllib.parse import urlsplit

# Used within the existing generation request; never adds a formatting request.
SUMMARY_LAYOUT = '''
使用以下手机阅读结构，最多三级标题，不使用代码块或表格：
## 要点速览：3至5条短句，每条只说一件事。
## 话题详情：每个话题用 ### 01 话题名；将不同人的观点分开写。
每条约40至100字，较长内容拆成多条；先写发生了什么，再单列“来源：日期 时间 · 原发言人”。
发言人姓名用普通文本，不使用反引号；原文中的表情不必重复堆砌。保留影响理解的日期和时间，不在每个从句重复完整时间戳。
## 明确事项：仅列记录明确的决定和已完成事项；群友自述仍须标注“自述”，不等于外部核实。
## 待办与待确认：每项分开写“事项、负责人、期限、状态”。没有负责人或期限写“未明确”，没有事项写“本次记录未明确”。
概览可简述详情，其他章节不得重复铺陈同一事实；区分观点、建议、计划和已完成。不要为了模板编造内容。
'''

SAMPLE_REPORT = '''# 项目协作群 · 日报示例
2026-11-17 09:00 至 18:00 · 以下内容仅用于展示模板

## 要点速览
- 本周培训改为线上举行，开始时间保持不变。
- 新版资料已整理完成，等待负责人复核。
- 报名截止时间尚未明确，需要补充确认。

## 话题详情
### 01 培训安排
- **进展**：原定线下培训改为线上举行。
- **来源**：11-17 10:20 · 小林（组织者）
- **待确认**：会议链接尚未发布。

### 02 资料整理
- **进展**：小周自述已整理新版资料，正在等待复核。
- **来源**：11-17 15:40 · 小周

## 明确事项
- **决定**：培训形式改为线上；日期和开始时间沿用原通知。

## 待办与待确认
### 01 发布会议链接
- **负责人**：小林
- **期限**：未明确
- **状态**：待完成
### 02 确认报名截止时间
- **负责人**：未明确
- **期限**：未明确
- **状态**：待确认

## 本地资料覆盖说明（程序统计）
- 本页为虚构示例，不读取聊天记录，不调用 Gemini，不发送 PushPlus。
'''


def inline(text):
    """Escape HTML first, then allow a small, safe Markdown inline subset."""
    token = re.compile(r'\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`')
    result, end = [], 0
    for match in token.finditer(text):
        result.append(escape(text[end:match.start()]))
        if match[1] is not None:
            url = match[2]
            if urlsplit(url).scheme.lower() in ('http', 'https'):
                result.append(f'<a href="{escape(url,quote=True)}" style="color:#007aff;word-break:break-all">{escape(match[1])}</a>')
            else:
                result.append(escape(match[0]))
        elif match[3] is not None:
            result.append('<strong>'+escape(match[3])+'</strong>')
        else:
            # Names and identifiers used to appear as distracting pink code.
            result.append('<span>'+escape(match[4])+'</span>')
        end = match.end()
    result.append(escape(text[end:]))
    return ''.join(result)


def blocks(markdown):
    """Parse readable Markdown without executing raw HTML or loading remote images."""
    lines = markdown.replace('\r\n','\n').splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or re.fullmatch(r'[-*_]{3,}',line):
            i += 1
            continue
        if line.startswith('```'):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i]); i += 1
            out.append(('paragraph','\n'.join(code))); i += 1
            continue
        if i+1 < len(lines) and '|' in line and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*',lines[i+1]):
            headers=[v.strip() for v in line.strip('|').split('|')]
            i += 2
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                cells=[v.strip() for v in lines[i].strip().strip('|').split('|')]
                # A vertical definition card is legible on narrow phone screens.
                out.append(('paragraph','\n'.join(f'{headers[n] if n<len(headers) else "补充"}：{v}' for n,v in enumerate(cells))))
                i += 1
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)',line)
        if heading:
            out.append(('h'+str(min(len(heading[1]),3)),heading[2]))
        elif re.match(r'^[-*+]\s+',line):
            out.append(('item',re.sub(r'^[-*+]\s+','',line)))
        elif re.match(r'^\d+[.)、]\s*',line):
            out.append(('item',line))
        else:
            # Keep each source line; do not invent summaries or move attributions.
            out.append(('paragraph',line.lstrip('> ').strip() if line.startswith('>') else line))
        i += 1
    return out


def render_block(kind,text):
    content = '<br>'.join(inline(line) for line in text.split('\n'))
    if kind == 'h1':
        return f'<h1 style="font-size:22px;line-height:1.4;margin:4px 0 12px;font-weight:700">{content}</h1>'
    if kind == 'h2':
        return f'<h2 style="font-size:18px;line-height:1.5;margin:22px 0 10px;padding:9px 12px;background:#eef4ff;border-left:3px solid #007aff;border-radius:6px">{content}</h2>'
    if kind == 'h3':
        return f'<h3 style="font-size:16px;line-height:1.5;margin:16px 0 8px;color:#1d1d1f">{content}</h3>'
    if kind == 'item':
        return f'<div style="margin:7px 0;padding:10px 12px;background:#f7f8fa;border-radius:8px;line-height:1.85">{content}</div>'
    return f'<p style="margin:8px 0;line-height:1.85">{content}</p>'


def fragment(values,title='',part=None):
    heading = render_block('h1',title) if title else ''
    marker = f'<p style="color:#6e6e73;font-size:12px">第 {part[0]} / {part[1]} 部分</p>' if part else ''
    return ('<article style="max-width:760px;margin:0 auto;padding:14px 12px;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Microsoft YaHei,sans-serif;'
            'font-size:15px;color:#1d1d1f;background:#fff;word-wrap:break-word;overflow-wrap:anywhere">'
            +heading+marker+''.join(render_block(*item) for item in values)+'</article>')


def push_parts(markdown,title='',limit=18000):
    """Bound the final HTML size (PushPlus ordinary-account limit is 20k chars)."""
    values = blocks(markdown)
    if not values: values=[('paragraph','本次报告没有可显示的内容。')]
    split=[]
    # Bound escaping/markup expansion, including a single very long source line.
    for kind,text in values:
        pending=[text[offset:offset+12000] for offset in range(0,len(text),12000)] or ['']
        while pending:
            value=pending.pop(0)
            if len(fragment([(kind,value)],title,(9999,9999)))>limit:
                if len(value)<=1:raise ValueError('推送模板超过可用大小')
                mid=len(value)//2
                pending[:0]=[value[:mid],value[mid:]]
            else:split.append((kind,value))
    groups,current=[],[]
    for item in split:
        if current and (sum(len(text)+1 for _,text in current)+len(item[1])>12000 or
                        len(fragment(current+[item],title,(9999,9999)))>limit):
            groups.append(current);current=[]
        current.append(item)
    if current:groups.append(current)
    return [fragment(group,title,(i,len(groups)) if len(groups)>1 else None) for i,group in enumerate(groups,1)]


def document(markdown,title='聊天总结 · 阅读版'):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+escape(title)+'</title><style>body{margin:0;background:#f5f5f7}*{box-sizing:border-box}article{min-height:100vh}a{overflow-wrap:anywhere}</style></head><body>'
            +fragment(blocks(markdown))+'</body></html>')


def save_reading_copy(path):
    """Keep the original Markdown and write only a separately named HTML copy."""
    path=Path(path)
    target=path.with_name(path.stem+'_阅读版.html')
    index=2
    while target.exists():
        target=path.with_name(path.stem+f'_阅读版_{index}.html');index+=1
    target.write_text(document(path.read_text(encoding='utf-8-sig'),path.stem),encoding='utf-8')
    return target
