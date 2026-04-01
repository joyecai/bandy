"""文本转语音: 模块化引擎 (Edge TTS 云端 / Qwen3-TTS 本地 MLX) + afplay 播放"""
import os
import asyncio
import subprocess
import tempfile
import time as _time
import logging

import edge_tts

from .config import cfg
from .metrics import store, TtsMetric

log = logging.getLogger(__name__)

# ── Qwen3-TTS 懒加载 ──
_qwen_model = None


def _engine() -> str:
    return getattr(cfg, "TTS_ENGINE", "edge")


def _load_qwen():
    global _qwen_model
    if _qwen_model is not None:
        return _qwen_model
    from mlx_audio.tts.utils import load_model
    repo = getattr(cfg, "TTS_QWEN_REPO", "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit")
    log.info("加载 Qwen3-TTS: %s", repo)
    _qwen_model = load_model(repo)
    log.info("Qwen3-TTS 就绪 (sample_rate=%d)", _qwen_model.sample_rate)
    return _qwen_model


def _qwen_synth(text: str) -> str:
    """Qwen3-TTS 同步合成, 返回 wav 路径."""
    import numpy as np
    import soundfile as sf
    model = _load_qwen()
    results = list(model.generate(text=text, verbose=False))
    if not results:
        raise RuntimeError("Qwen3-TTS 未生成音频")
    audio_np = np.array(results[0].audio)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio_np, model.sample_rate)
    return path


async def warm_tts(cache: dict):
    """预热 TTS 引擎."""
    engine = _engine()
    if engine == "qwen":
        try:
            await asyncio.to_thread(_load_qwen)
            log.info("Qwen3-TTS 预热中...")
            await asyncio.to_thread(_qwen_synth, "在")
            log.info("Qwen3-TTS 预热完成")
        except Exception:
            log.exception("Qwen3-TTS 预热失败, 回退到 Edge TTS")
            cfg.TTS_ENGINE = "edge"
    if _engine() == "edge":
        for txt, voice in [("在", "zh-CN-XiaoyiNeural"),
                           ("好的，对话结束", "zh-CN-XiaoyiNeural")]:
            fd, path = tempfile.mkstemp(suffix='.mp3')
            os.close(fd)
            try:
                await edge_tts.Communicate(txt, voice).save(path)
                cache[txt] = path
            except Exception:
                try:
                    os.remove(path)
                except OSError:
                    pass


def select_voice(text):
    from .llm import get_ui_lang
    if get_ui_lang() == 'en':
        return "en-US-AriaNeural"
    return "zh-CN-XiaoyiNeural"


async def synthesize(text, voice=None):
    """合成 TTS 音频文件, 返回路径."""
    engine = _engine()
    t0 = _time.time()

    if engine == "qwen":
        try:
            path = await asyncio.to_thread(_qwen_synth, text)
        except Exception:
            log.exception("Qwen3-TTS 合成失败, 回退 Edge TTS")
            engine = "edge"

    if engine != "qwen":
        if voice is None:
            voice = select_voice(text)
        fd, path = tempfile.mkstemp(suffix='.mp3')
        os.close(fd)
        await edge_tts.Communicate(text, voice).save(path)

    store.record_tts(TtsMetric(
        text=text, char_count=len(text), synth_time=_time.time() - t0))
    return path


async def play(path, state):
    """播放音频文件, state 需包含 _playback_proc / _is_speaking / _barge_in 等属性."""
    state._barge_in = False
    state._is_speaking = True
    proc = subprocess.Popen(
        ["afplay", "-r", cfg.PLAYBACK_SPEED, path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state._playback_proc = proc
    await asyncio.to_thread(proc.wait)
    state._playback_proc = None
    state._is_speaking = False
    import time
    if state._barge_in:
        state._speak_end_time = time.time() - cfg.SPEAK_COOLDOWN + 0.2
    else:
        state._speak_end_time = time.time()
