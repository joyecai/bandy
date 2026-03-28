"""语音识别: faster-whisper STT"""
import os
import time as _time

import numpy as np

import re

from .config import cfg
from .utils import to_simplified, detect_lang
from .metrics import store, SttMetric

_WHISPER_FIX = [
    (re.compile(r'电器'), '天气'),
    (re.compile(r'天汽'), '天气'),
    (re.compile(r'点击'), '天气'),
    (re.compile(r'典起'), '天气'),
    (re.compile(r'[Bb]en\s*[Ll]ee'), 'Bandy'),
    (re.compile(r'[Bb]endy'), 'Bandy'),
    (re.compile(r'[Bb]en\s*[Dd]y'), 'Bandy'),
    (re.compile(r'[Bb]andy'), 'Bandy'),
]


def _post_fix(text):
    """修正 Whisper 常见误识别."""
    for pat, repl in _WHISPER_FIX:
        text = pat.sub(repl, text)
    return text


def load_whisper():
    from faster_whisper import WhisperModel
    print(f"🔊 加载 Whisper ({cfg.WHISPER_MODEL})...", flush=True)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    m = WhisperModel(cfg.WHISPER_MODEL, device=cfg.WHISPER_DEVICE,
                     compute_type=cfg.WHISPER_COMPUTE)
    store.set_model_info("stt", f"Whisper ({cfg.WHISPER_MODEL})",
                         f"{cfg.WHISPER_DEVICE}/{cfg.WHISPER_COMPUTE}")
    return m


def warm_whisper(model):
    """用一段静音做一次推理, 触发 JIT 编译, 消除首次识别延迟."""
    print("🔥 预热 Whisper...", flush=True)
    try:
        silence = np.zeros(cfg.SAMPLE_RATE, dtype=np.float32)
        segs, _ = model.transcribe(silence, language="zh", beam_size=1, vad_filter=False)
        for _ in segs:
            pass
    except Exception:
        pass


def transcribe_file(model, file_path):
    """转写音频文件 (支持 ogg/mp3/wav 等), 返回文本."""
    import subprocess, tempfile
    wav_path = None
    try:
        fd, wav_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-ar", str(cfg.SAMPLE_RATE),
             "-ac", "1", "-f", "wav", wav_path],
            capture_output=True, timeout=30)
        import soundfile as sf
        audio, sr = sf.read(wav_path, dtype='float32')
        if len(audio.shape) > 1:
            audio = audio[:, 0]
    except Exception:
        try:
            raw = np.fromfile(wav_path or file_path, dtype=np.int16, offset=44)
            audio = raw.astype(np.float32) / 32768.0
        except Exception:
            return ""
    finally:
        if wav_path:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    if len(audio) < cfg.SAMPLE_RATE * 0.3:
        return ""
    t0 = _time.time()
    segs, _ = model.transcribe(audio, temperature=0.0, beam_size=3,
                               vad_filter=True, condition_on_previous_text=False)
    text = "".join(s.text for s in segs).strip()
    proc_time = _time.time() - t0
    if detect_lang(text) == 'zh':
        text = to_simplified(text)
    text = _post_fix(text)
    if text:
        store.record_stt(SttMetric(
            audio_duration=len(audio) / cfg.SAMPLE_RATE,
            process_time=proc_time, text=text))
    return text


def recognize(model, audio):
    try:
        if len(audio) < cfg.SAMPLE_RATE * cfg.MIN_SPEECH_DUR:
            return ""
        audio_dur = len(audio) / cfg.SAMPLE_RATE
        t0 = _time.time()
        segs, _ = model.transcribe(audio, temperature=0.0, beam_size=1,
                                   vad_filter=True, condition_on_previous_text=False)
        text = "".join(s.text for s in segs).strip()
        proc_time = _time.time() - t0
        if detect_lang(text) == 'zh':
            text = to_simplified(text)
        text = _post_fix(text)
        if len(text) > 80 or (len(set(text)) < 5 and len(text) > 5):
            return ""
        if text:
            store.record_stt(SttMetric(
                audio_duration=audio_dur, process_time=proc_time, text=text))
        return text
    except Exception:
        return ""
