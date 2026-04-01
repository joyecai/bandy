"""文本转语音: 模块化引擎 (Edge TTS 云端 / 本地 MLX) + afplay 播放"""
import os
import asyncio
import subprocess
import tempfile
import time as _time
import logging

import threading

import edge_tts

from .config import cfg
from .metrics import store, TtsMetric

log = logging.getLogger(__name__)

_mlx_model = None
_mlx_repo_loaded = None
_mlx_gpu_lock = threading.Lock()


def _engine() -> str:
    return getattr(cfg, "TTS_ENGINE", "edge")


def _load_mlx():
    """懒加载本地 MLX TTS 模型 (Qwen3-TTS / Kokoro 等均兼容)."""
    global _mlx_model, _mlx_repo_loaded
    repo = getattr(cfg, "TTS_MLX_REPO", "")
    if _mlx_model is not None and _mlx_repo_loaded == repo:
        return _mlx_model
    if _mlx_model is not None:
        del _mlx_model
        _mlx_model = None
    from mlx_audio.tts.utils import load_model
    log.info("加载本地 TTS: %s", repo)
    _mlx_model = load_model(repo)
    _mlx_repo_loaded = repo
    log.info("本地 TTS 就绪 (sample_rate=%d)", _mlx_model.sample_rate)
    return _mlx_model


def _mlx_synth(text: str) -> str:
    """本地 MLX TTS 同步合成, 返回 wav 路径. 使用 GPU 锁防止 Metal 并发崩溃."""
    import numpy as np
    import soundfile as sf
    with _mlx_gpu_lock:
        model = _load_mlx()
        voice = getattr(cfg, "TTS_MLX_VOICE", "") or None
        results = list(model.generate(text=text, voice=voice, verbose=False))
        if not results:
            raise RuntimeError("本地 TTS 未生成音频")
        audio_np = np.array(results[0].audio)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio_np, model.sample_rate)
    return path


async def warm_tts(cache: dict):
    """预热 TTS 引擎."""
    engine = _engine()
    if engine == "mlx":
        repo = getattr(cfg, "TTS_MLX_REPO", "")
        voice = getattr(cfg, "TTS_MLX_VOICE", "")
        print(f"🔊 TTS 引擎: mlx ({repo}, voice={voice or 'default'})", flush=True)
        try:
            await asyncio.to_thread(_load_mlx)
            print("🔥 预热本地 TTS...", flush=True)
            await asyncio.to_thread(_mlx_synth, "在")
            print("   本地 TTS 预热完成", flush=True)
        except Exception as e:
            print(f"⚠️ 本地 TTS 预热失败 ({e}), 回退到 Edge TTS", flush=True)
            log.exception("本地 TTS 预热失败, 回退到 Edge TTS")
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


def _model_supports_zh() -> bool:
    """当前 MLX TTS 模型是否支持中文."""
    repo = (getattr(cfg, "TTS_MLX_REPO", "") or "").lower()
    return "qwen" in repo


async def synthesize(text, voice=None):
    """合成 TTS 音频文件, 返回路径."""
    engine = _engine()
    t0 = _time.time()

    if engine == "mlx":
        from .utils import detect_lang
        if not _model_supports_zh() and detect_lang(text) == "zh":
            engine = "edge"
        else:
            try:
                path = await asyncio.to_thread(_mlx_synth, text)
            except Exception as e:
                print(f"⚠️ 本地 TTS 合成失败 ({e}), 回退 Edge TTS", flush=True)
                log.exception("本地 TTS 合成失败, 回退 Edge TTS")
                engine = "edge"

    if engine != "mlx":
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
