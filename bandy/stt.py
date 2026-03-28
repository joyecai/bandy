"""语音识别: faster-whisper STT"""
import os
import time as _time

import numpy as np

from .config import cfg
from .utils import to_simplified, detect_lang
from .metrics import store, SttMetric


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
        if len(text) > 80 or (len(set(text)) < 5 and len(text) > 5):
            return ""
        if text:
            store.record_stt(SttMetric(
                audio_duration=audio_dur, process_time=proc_time, text=text))
        return text
    except Exception:
        return ""
