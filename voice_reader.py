"""Local SILK decoding and CPU SenseVoice recognition; no network calls."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from db_reader import snapshot, storage
from secure_store import BASE, atomic_bytes, protect, safe_error
from app_paths import MODEL_DIR

class VoiceReader:
    def __init__(self, cfg, secrets, cancel, progress):
        self.cfg, self.secrets, self.cancel, self.progress = cfg, secrets, cancel, progress
        self.stack = ExitStack()
        self.connections = {}
        self.recognizer = None
        self.cache_path = BASE/'voice_cache.dpapi'
        self.cache = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(protect(self.cache_path.read_bytes(), True))
            except (OSError, ValueError):
                pass

    def close(self):
        self.stack.close()

    def audio(self, row):
        sid = row.get('server_id')
        if not sid:
            return None
        for path in sorted(storage(self.cfg).rglob('media_*.db')):
            if path not in self.connections:
                self.progress('读取本地语音库：'+path.name)
                self.connections[path] = self.stack.enter_context(snapshot(path, self.secrets.get('db_keys',{})))
            conn = self.connections[path]
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'VoiceInfo','Name2Id'} <= tables:
                continue
            found = conn.execute('SELECT rowid FROM Name2Id WHERE user_name=?', (row['room'],)).fetchone()
            if found:
                record = conn.execute('SELECT voice_data FROM VoiceInfo WHERE chat_name_id=? AND svr_id=? ORDER BY create_time DESC LIMIT 1',
                                      (found[0],sid)).fetchone()
                if record and record[0]:
                    return bytes(record[0])
        return None

    def recognize(self, data):
        digest = hashlib.sha256(b'sensevoice-20250909-v1'+data).hexdigest()
        if digest in self.cache:
            return self.cache[digest]
        model_dir = Path(self.cfg.get('voice_model_dir') or MODEL_DIR)
        if not (model_dir/'model.int8.onnx').is_file() or not (model_dir/'tokens.txt').is_file():
            raise ValueError('离线语音模型尚未安装')
        import numpy as np
        import pilk_nogil as pilk
        import sherpa_onnx
        if self.recognizer is None:
            self.progress('加载本机离线语音模型（首次加载稍慢）')
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_dir/'model.int8.onnx'), tokens=str(model_dir/'tokens.txt'),
                num_threads=2, use_itn=True, language='auto', debug=False)
        with tempfile.TemporaryDirectory(prefix='wechat_voice_') as tmp:
            silk, pcm = Path(tmp)/'audio.silk', Path(tmp)/'audio.pcm'
            silk.write_bytes(data)
            pilk.decode(str(silk), str(pcm), pcm_rate=16000)
            samples = np.frombuffer(pcm.read_bytes(), dtype='<i2').astype(np.float32)/32768.0
        if not 1600 <= len(samples) <= 16000*300:
            raise ValueError('语音长度异常或超出 5 分钟限制')
        if np.sqrt(np.mean(samples*samples)) < 0.0001:
            raise ValueError('音频静音，未识别到语音')
        if self.cancel.is_set():
            from jobs import Cancelled
            raise Cancelled('任务已取消')
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, samples)
        self.recognizer.decode_stream(stream)
        value = stream.result.text.strip()
        if not value:
            raise ValueError('未识别到可读文字')
        self.cache[digest] = value
        self.cache = dict(list(self.cache.items())[-5000:])
        atomic_bytes(self.cache_path, protect(json.dumps(self.cache,ensure_ascii=False).encode('utf-8')))
        return value

    def read(self, row):
        if not self.cfg.get('enable_voice_asr', True):
            return '[语音消息：本地转写已关闭]'
        try:
            data = self.audio(row)
            if data is None:
                return '[语音消息：本机未下载语音音频，需在微信中同步后重试]'
            self.progress('正在本机转写语音…')
            return '[语音转文字·本机识别，可能有误] '+self.recognize(data)
        except Exception as exc:
            from jobs import Cancelled
            if isinstance(exc, Cancelled):
                raise
            return '[语音消息：'+safe_error(exc,self.secrets)+']'
