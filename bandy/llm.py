"""LLM API 调用: 流式与非流式"""
import re
import os
import json
import asyncio
import tempfile
import time as _time

import edge_tts

from .config import cfg
from .utils import detect_lang, strip_markdown, to_simplified
from .metrics import store, LlmMetric, TtsMetric

SYS_ZH = (
    "你是一个语音助手，用户通过语音和你交流，你的回答会被TTS朗读出来。"
    "要求：1.用纯文本回复，禁止Markdown。2.简洁口语化。3.不加括号说明。4.用中文回复。"
    "5.禁止使用任何emoji、图标、特殊符号字符。"
)
SYS_EN = (
    "You are a voice assistant. Your reply is read aloud by TTS. "
    "Rules: plain text only, no Markdown, no emoji or icon characters, "
    "concise conversational style, reply in English."
)

_SENT_BREAK = re.compile(r'[。！？!?\n]|\.(?!\d)')


async def call_streaming(assistant, prompt):
    """流式调用 LLM, 流水线 TTS (合成与播放并行, 消除句间停顿)."""
    import aiohttp

    sys_p = SYS_EN if detect_lang(prompt) == 'en' else SYS_ZH
    messages = [{"role": "system", "content": sys_p}]
    for h in assistant._recent_history():
        messages.append({"role": h["role"], "content": h["text"]})
    messages.append({"role": "user", "content": prompt})

    try:
        session = await assistant._get_session()
        _t_start = _time.time()
        _t_first_token = 0.0
        _token_count = 0
        resp = await session.post(
            cfg.API_URL, headers={"Authorization": f"Bearer {cfg.API_KEY}"},
            json={"model": cfg.API_MODEL, "messages": messages, "stream": True},
            timeout=aiohttp.ClientTimeout(total=60))

        voice = "en-US-AriaNeural" if detect_lang(prompt) == 'en' else "zh-CN-XiaoxiaoNeural"
        pipe = asyncio.Queue()
        synth_tasks = []
        aborted = False

        async def _synth(text):
            _ts = _time.time()
            fd, p = tempfile.mkstemp(suffix='.mp3')
            os.close(fd)
            await edge_tts.Communicate(text, voice).save(p)
            store.record_tts(TtsMetric(
                text=text, char_count=len(text), synth_time=_time.time() - _ts))
            return p

        async def _player():
            nonlocal aborted
            while True:
                item = await pipe.get()
                if item is None:
                    break
                try:
                    path = await item
                except (Exception, asyncio.CancelledError):
                    continue
                import subprocess
                async with assistant._speak_lock:
                    assistant._barge_in = False
                    assistant._is_speaking = True
                    proc = subprocess.Popen(
                        ["afplay", "-r", cfg.PLAYBACK_SPEED, path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    assistant._playback_proc = proc
                    await asyncio.to_thread(proc.wait)
                    assistant._playback_proc = None
                    assistant._is_speaking = False
                    import time
                    import time
                    bargein = assistant._barge_in
                    if bargein:
                        assistant._speak_end_time = time.time() - cfg.SPEAK_COOLDOWN + 0.2
                    else:
                        assistant._speak_end_time = time.time()
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    # flush echo from mic
                    import queue as _q
                    while not assistant._speech_queue.empty():
                        try:
                            assistant._speech_queue.get_nowait()
                        except _q.Empty:
                            break
                    if bargein:
                        assistant._barge_in = False
                        aborted = True
                        break

        player_task = asyncio.create_task(_player())

        buf = ""
        full = ""
        sse_buf = ""
        while not aborted:
            raw = await resp.content.readline()
            if not raw:
                break
            sse_buf += raw.decode()
            while '\n' in sse_buf:
                line, sse_buf = sse_buf.split('\n', 1)
                line = line.strip()
                if line == "data: [DONE]":
                    break
                if not line.startswith("data: "):
                    continue
                try:
                    chunk = json.loads(line[6:])
                    token = chunk["choices"][0]["delta"].get("content", "")
                except Exception:
                    continue
                if not token:
                    continue
                _token_count += 1
                if _token_count == 1:
                    _t_first_token = _time.time() - _t_start
                buf += token
                full += token
                if _SENT_BREAK.search(buf) and len(buf) >= 4:
                    sentence = strip_markdown(buf.strip())
                    if detect_lang(sentence) == 'zh':
                        sentence = to_simplified(sentence)
                    buf = ""
                    if sentence and not aborted:
                        t = asyncio.create_task(_synth(sentence))
                        synth_tasks.append(t)
                        await pipe.put(t)
            else:
                continue
            break

        if buf.strip() and not aborted:
            sentence = strip_markdown(buf.strip())
            if detect_lang(sentence) == 'zh':
                sentence = to_simplified(sentence)
            if sentence:
                t = asyncio.create_task(_synth(sentence))
                synth_tasks.append(t)
                await pipe.put(t)

        await pipe.put(None)
        await player_task
        resp.close()
        _total_time = _time.time() - _t_start
        if full:
            print(f"🤖 回复: {strip_markdown(full)}", flush=True)

        store.record_llm(LlmMetric(
            prompt=prompt, reply=strip_markdown(full) if full else "",
            tokens=_token_count, time_to_first_token=_t_first_token,
            total_time=_total_time))

        for t in synth_tasks:
            if not t.done():
                t.cancel()
            try:
                p = await t
                os.remove(p)
            except (Exception, asyncio.CancelledError):
                pass

        return strip_markdown(full) if full else "抱歉，没有收到回复"
    except (Exception, asyncio.CancelledError) as e:
        print(f"⚠️ API 错误: {e}", flush=True)
        return "抱歉，网络出了点问题，请再说一次"


async def call_api(assistant, prompt):
    """非流式调用 (备用)"""
    try:
        import aiohttp
        sys_p = SYS_EN if detect_lang(prompt) == 'en' else SYS_ZH
        messages = [{"role": "system", "content": sys_p}]
        for h in assistant._recent_history():
            messages.append({"role": h["role"], "content": h["text"]})
        messages.append({"role": "user", "content": prompt})
        session = await assistant._get_session()
        async with session.post(
            cfg.API_URL, headers={"Authorization": f"Bearer {cfg.API_KEY}"},
            json={"model": cfg.API_MODEL, "messages": messages},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
            text = strip_markdown(data['choices'][0]['message']['content'])
            if detect_lang(text) == 'zh':
                text = to_simplified(text)
            return text
    except Exception as e:
        print(f"⚠️ API 错误: {e}", flush=True)
        return "抱歉，网络出了点问题，请再说一次"
