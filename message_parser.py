"""Bounded XML/compression parsing, sender matching and local image OCR."""
import hashlib
import html
import io
import re
import shutil
import struct
import tempfile
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from Crypto.Cipher import AES
import lz4.block
import zstandard

LIMIT = 16 * 1024 * 1024
NOISE = {'收到', '+1', '1', '好的', '谢谢', '好', 'ok', '[动画表情]'}

def text_value(value):
    if not value:
        return ''
    if isinstance(value, str):
        return value
    data = bytes(value)
    if data.startswith(b'\x28\xb5\x2f\xfd'):
        data = zstandard.ZstdDecompressor().decompress(data, max_output_size=LIMIT)
    if len(data) > LIMIT:
        raise ValueError('单条消息解压后过大')
    return data.decode('utf-8', 'replace').rstrip('\0')

def content_of(row):
    compressed = row.get('compress_content')
    normal = row.get('message_content')
    for value in (normal, compressed):
        if isinstance(value, bytes) and value.startswith(b'\x28\xb5\x2f\xfd'):
            return text_value(value)
    if isinstance(compressed, bytes) and compressed:
        for size in (None, 1024*1024, LIMIT):
            try:
                if size is None:
                    # Stored-size LZ4 blocks must not be allowed to allocate arbitrary memory.
                    if len(compressed)<4 or int.from_bytes(compressed[:4], 'little') > LIMIT:
                        continue
                    result = lz4.block.decompress(compressed)
                else:
                    result = lz4.block.decompress(compressed, uncompressed_size=size)
                return text_value(result)
            except (ValueError, lz4.block.LZ4BlockError):
                pass
    return text_value(normal) or text_value(compressed)

def xml(value):
    if len(value) > LIMIT or re.search(r'<!DOCTYPE|<!ENTITY', value, re.I):
        raise ValueError('XML 内容超限或包含外部实体声明')
    value = value.strip().rstrip('\0')
    for _ in range(3):
        if re.search(r'<!DOCTYPE|<!ENTITY', value, re.I):
            raise ValueError('XML 包含实体声明')
        start = value.find('<')
        if start >= 0:
            try:
                return ET.fromstring(value[start:])
            except ET.ParseError:
                pass
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    return None

def node_text(node, *paths):
    for path in paths:
        child = node.find(path)
        if child is not None and child.text:
            return child.text.strip()
    return ''

def match_name(keyword, sender, names=()):
    if keyword.startswith('id='):
        return bool(names) and keyword[3:] == names[0]
    return not keyword or any(keyword.casefold() in str(v).casefold() for v in (sender,*names) if v)

def forwarded(root, keyword='', depth=0, budget=None):
    if depth > 12:
        return ['[嵌套转发超过 12 层，未继续展开]']
    budget = budget if budget is not None else [10000]
    # Select only direct dataitems of this record, not their nested descendants.
    container = root if root.tag == 'datalist' else root.find('datalist')
    if container is None:
        record = root.find('.//recorditem')
        if record is not None:
            inner = xml(record.text or '') if record.text and record.text.strip() else next(iter(record), None)
            return forwarded(inner, keyword, depth+1, budget) if inner is not None else []
        container = root.find('.//datalist')
    if container is None:
        return []
    output = []
    for item in container.findall('dataitem'):
        budget[0] -= 1
        if budget[0] < 0:
            output.append('[转发内消息超过 10000 条，未继续展开]')
            break
        sender = node_text(item, 'sourcename', 'dataitemsource/realchatname') or '未知原发送人'
        uid = node_text(item, 'dataitemsource/fromusr', 'fromusr')
        moment = node_text(item, 'sourcetime', 'dataitemsource/createtime')
        desc = node_text(item, 'datadesc')
        title = node_text(item, 'datatitle')
        nested_lines = []
        for tag in ('recordxml', 'recorditem'):
            child = item.find(tag)
            if child is not None:
                nested = xml(child.text or '') if child.text and child.text.strip() else next(iter(child), None)
                if nested is not None:
                    nested_lines.extend(forwarded(nested, keyword, depth+1, budget))
        if desc and ('<record' in desc or '&lt;record' in desc or '<datalist' in desc):
            nested = xml(desc)
            if nested is not None:
                nested_lines.extend(forwarded(nested, keyword, depth+1, budget))
                desc = ''
        if nested_lines:
            output.extend(nested_lines)
        elif match_name(keyword, sender, (uid,)):
            body = desc or title or '[图片/文件/其他附件，卡片内未包含可读文字]'
            output.append(f'[原消息 {moment or "时间未提供"}] {sender}: {body}')
    return output

def app_message(content, keyword=''):
    root = xml(content)
    if root is None:
        return '[应用消息 XML 无法解析]' if not keyword else ''
    lines = forwarded(root, keyword)
    if lines:
        return '【合并转发】\n' + '\n'.join('  '+v for v in lines)
    if keyword:
        return ''
    title = node_text(root, './/appmsg/title', 'title')
    url = node_text(root, './/appmsg/url', 'url')
    kind = node_text(root, './/appmsg/type', 'type')
    if kind == '57':
        result = '[引用回复] '+(title or '[回复正文缺失]')
        reference = root.find('.//refermsg')
        if reference is not None:
            author = node_text(reference, 'displayname', 'fromusr') or '原发送人未提供'
            reference_kind = node_text(reference, 'type')
            quoted = node_text(reference, 'content')
            if reference_kind in ('3','34','43','47','62'):
                quoted = {'3':'[图片]','34':'[语音]','43':'[视频]','47':'[表情]','62':'[视频]'}[reference_kind]
            elif reference_kind == '49':
                nested = xml(quoted)
                quoted = (node_text(nested,'.//appmsg/title','title') if nested is not None else '') or '[应用消息，原内容不可解析]'
            result += f'\n  ↳ 被引用内容（非本次发送者原话） {author}: {quoted or "[原内容未提供]"}'
        return result
    if kind == '19':
        return f'[合并转发 {title}：卡片未包含可解析的原消息]'
    if kind == '6':
        name = node_text(root, './/appattach/filename') or title
        return '[文件] '+(name or '[文件名未提供]')
    if kind == '5':
        return f'[分享链接] {title}\n{url}'.strip()
    labels = {'33':'小程序','36':'小程序','51':'视频号','87':'群公告','2000':'转账','2001':'转账','2003':'红包'}
    return f'[{labels.get(kind, "应用消息")}] {title}\n{url}'.strip()

def voice(content):
    root = xml(content)
    if root is not None:
        for node in root.iter():
            if node.tag in ('voicetrans', 'trans'):
                value = node.attrib.get('text') or node.text
                if value:
                    return '[语音转文字] '+value
    return '[语音消息：本地记录未提供转文字]'

def useful(text):
    return text.strip().casefold() not in NOISE and bool(re.search(r'[\w\u3400-\u9fff]', re.sub(r'\[[^\]]{1,8}\]', '', text)))

MAGICS = (b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'GIF8', b'BM', b'RIFF')

def decode_image(data, key_hex='', xor_key=None):
    if data.startswith(MAGICS):
        return data
    if data[:6] in (bytes.fromhex('070856310807'), bytes.fromhex('070856320807')):
        if data[3] == ord('2') and not key_hex:
            raise ValueError('V2 图片缺少独立图片密钥')
        key = bytes.fromhex(key_hex) if data[3] == ord('2') else hashlib.md5(b'0').hexdigest()[:16].encode()
        if len(data) < 15:
            raise ValueError('图片头不完整')
        count, tail = struct.unpack_from('<II', data, 6)
        end = 15 + (count//16+1)*16
        if not count or end > len(data)-tail:
            raise ValueError('图片长度校验失败')
        head = AES.new(key, AES.MODE_ECB).decrypt(data[15:end])
        pad = head[-1]
        if not 1 <= pad <= 16 or head[-pad:] != bytes([pad])*pad:
            raise ValueError('图片密钥不匹配')
        plain = head[:-pad] + data[end:len(data)-tail if tail else len(data)]
        if tail:
            if xor_key is None and data[3] == ord('1'):
                xor_key = 0x88
            if xor_key is None:
                raise ValueError('图片 XOR 密钥尚未初始化')
            plain += bytes(v ^ xor_key for v in data[-tail:])
        if plain.startswith(b'\xff\xd8\xff'):
            marker = plain.rfind(b'\xff\xd9')
            if marker >= 0 and len(plain)-marker-2 in (0,24):
                plain = plain[:marker+2]
        if not plain.startswith((*MAGICS,b'wxgf')):
            raise ValueError('解密后的图片格式无法识别')
        return plain
    for magic in MAGICS:
        if len(data) >= len(magic):
            key = data[0] ^ magic[0]
            if bytes(v ^ key for v in data[:len(magic)]) == magic:
                return bytes(v ^ key for v in data)
    raise ValueError('无法识别图片格式')

def ocr_image(data):
    if not data.startswith(b'wxgf'):
        return data
    import av
    start = data.find(b'\0\0\0\1')
    if start < 0:
        raise ValueError('WXGF 图片缺少 HEVC 图像流')
    with av.open(io.BytesIO(data[start:]),format='hevc') as media:
        for frame in media.decode(video=0):
            if frame.width*frame.height > 50_000_000:
                raise ValueError('图片分辨率超过本地识别限制')
            output = io.BytesIO()
            frame.to_image().save(output,format='PNG')
            return output.getvalue()
    raise ValueError('WXGF 图片中没有可解码画面')

class ImageReader:
    def __init__(self, account, secrets):
        self.root = Path(account)
        if self.root.name == 'db_storage':
            self.root = self.root.parent
        self.secrets = secrets
        self.index = {}
        self.cache = {}
        self.engine = None

    def read(self, room, content, packed_info=None):
        # WeChat 4.x uses a separate local attachment ID in packed_info_data.
        # XML md5 values often describe CDN content and do not name the local file.
        packed = packed_info.encode('utf-8') if isinstance(packed_info,str) else bytes(packed_info or b'')
        local_ids = [m.decode().lower() for m in re.findall(
            rb'(?<![a-fA-F0-9])([a-fA-F0-9]{32})(?![a-fA-F0-9])',packed)]
        remote_ids = re.findall(r'(?:md5|cdnthumbmd5)=["\x27]([a-fA-F0-9]{32})', content)
        hashes = list(dict.fromkeys(local_ids+[v.lower() for v in remote_ids]))
        if not hashes:
            return '[图片：消息未提供可定位的附件标识]'
        if room not in self.index:
            base = self.root/'msg'/'attach'/hashlib.md5(room.encode()).hexdigest()
            found = {}
            if base.is_dir():
                for p in base.rglob('*.dat'):
                    found.setdefault(p.stem.split('_')[0].lower(), []).append(p)
            self.index[room] = found
        candidates = [p for md5 in hashes for p in self.index[room].get(md5.lower(), [])]
        candidates.sort(key=lambda p: ('_t' in p.stem.lower() or 'thumb' in str(p).lower(), '_h' not in p.stem.lower()))
        errors = []
        for path in candidates:
            if path in self.cache:
                return self.cache[path]
            try:
                if path.stat().st_size > 100*1024*1024:
                    raise ValueError('图片超过 100MB')
                with tempfile.TemporaryDirectory(prefix='wechat_image_') as tmp:
                    copied = Path(tmp)/'image.dat'
                    shutil.copy2(path, copied)
                    image = ocr_image(decode_image(copied.read_bytes(), self.secrets.get('image_key_hex', ''),
                                                  self.secrets.get('image_xor_key')))
                if self.engine is None:
                    from rapidocr_onnxruntime import RapidOCR
                    self.engine = RapidOCR()
                result, _ = self.engine(image)
                value = ' | '.join(str(x[1]).strip() for x in result or [])
                output = '[图片文字] '+value if len(re.sub(r'\W', '', value)) > 8 else '[图片：未识别到超过 8 字的文字]'
                self.cache[path] = output
                return output
            except Exception as exc:
                errors.append(str(exc))
        return '[图片：'+(errors[0] if errors else '原图及缩略图未在本地找到')+']'

def render(row, people, image_reader, keyword='', use_ocr=True, voice_reader=None):
    from db_reader import display
    content = content_of(row)
    sender_id = row.get('sender', '')
    if '\n' in content[:128]:
        head, rest = content.split('\n', 1)
        if head.endswith(':') and (head[:-1] == sender_id or head[:-1] in people):
            sender_id = sender_id or head[:-1]
            content = rest
    sender = display(people, sender_id)
    aliases = people.get(sender_id, {})
    matched = match_name(keyword, sender, (sender_id, aliases.get('nick_name'), aliases.get('remark'), aliases.get('alias')))
    kind = int(row.get('local_type', 0)) & 0xffffffff
    if kind == 49:
        body = app_message(content, '' if matched else keyword)
    elif not matched:
        return None
    elif kind == 1:
        if not useful(content):
            return None
        body = content
    elif kind == 3:
        body = image_reader.read(row['room'], content, row.get('packed_info_data')) if use_ocr else '[图片：OCR 已关闭]'
    elif kind == 34:
        body = voice(content)
        if body.startswith('[语音消息：') and voice_reader is not None:
            body = voice_reader.read(row)
    else:
        return None
    if not body:
        return None
    moment = datetime.fromtimestamp(row['create_time']).strftime('%Y-%m-%d %H:%M:%S')
    return f'[{moment}] {sender} ({sender_id or "身份未提供"}): {body}'
