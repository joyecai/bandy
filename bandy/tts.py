"""文本转语音: Edge TTS + afplay 播放"""
import os
import asyncio
import subprocess
import tempfile
import time as _time

import edge_tts

from .config import cfg
from .utils import detect_lang
from .metrics import store, TtsMetric


async def warm_tts(cache: dict):
    """预缓存高频回复的 TTS 音频, 减少首次延迟."""
    for txt, voice in [("在", "zh-CN-XiaoxiaoNeural"),
                       ("好的，对话结束", "zh-CN-XiaoxiaoNeural")]:
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
    if detect_lang(text) == 'en':
        return "en-US-AriaNeural"
    return "zh-CN-XiaoxiaoNeural"


async def synthesize(text, voice=None):
    """合成 TTS 音频文件, 返回路径."""
    if voice is None:
        voice = select_voice(text)
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    t0 = _time.time()
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
        from .config import cfg as _cfg
        state._speak_end_time = time.time() - _cfg.SPEAK_COOLDOWN + 0.2
    else:
        state._speak_end_time = time.time()
