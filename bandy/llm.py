"""LLM API 调用: 流式与非流式"""
import re
import os
import json
import asyncio
import logging
import platform
import subprocess
import tempfile
import time as _time
import datetime as _dt

import edge_tts

from .config import cfg
from .utils import detect_lang, strip_markdown, to_simplified
from .metrics import store, LlmMetric, TtsMetric

logger = logging.getLogger(__name__)

_hw_context_zh = ""
_hw_context_en = ""
_ui_lang = "zh"


def set_ui_lang(lang: str):
    """由 Dashboard 调用，设置全局 UI 语言 (zh/en)"""
    global _ui_lang
    _ui_lang = lang if lang in ("zh", "en") else "zh"


def get_ui_lang() -> str:
    return _ui_lang

_CITY_COORDS = [
    (31.57, 120.30, "无锡"), (31.30, 121.47, "上海"), (32.06, 118.80, "南京"),
    (30.27, 120.15, "杭州"), (31.23, 121.47, "上海"), (30.58, 114.30, "武汉"),
    (23.13, 113.26, "广州"), (22.54, 114.06, "深圳"), (39.90, 116.40, "北京"),
    (29.56, 106.55, "重庆"), (30.57, 104.07, "成都"), (34.26, 108.94, "西安"),
    (36.67, 116.99, "济南"), (34.75, 113.65, "郑州"), (28.23, 112.94, "长沙"),
    (25.04, 102.71, "昆明"), (26.65, 106.63, "贵阳"), (31.86, 117.28, "合肥"),
    (28.68, 115.86, "南昌"), (26.08, 119.30, "福州"), (41.80, 123.43, "沈阳"),
    (43.88, 125.32, "长春"), (45.75, 126.65, "哈尔滨"), (38.04, 114.50, "石家庄"),
    (37.87, 112.55, "太原"), (36.07, 120.38, "青岛"), (31.95, 120.87, "苏州"),
    (32.39, 119.42, "镇江"), (31.81, 119.97, "常州"), (32.01, 120.86, "南通"),
    (33.96, 118.28, "淮安"), (34.28, 117.19, "徐州"), (33.37, 120.16, "盐城"),
]


def _reverse_city_zh(lat: float, lon: float, fallback: str) -> str:
    best, best_d = fallback, 999
    for clat, clon, name in _CITY_COORDS:
        d = ((lat - clat) ** 2 + (lon - clon) ** 2) ** 0.5
        if d < best_d:
            best_d = d
            best = name
    return best if best_d < 0.5 else fallback


_WEEKDAY_ZH = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
_WEEKDAY_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _gather_hw_context():
    """收集硬件/系统信息（启动时调用一次），返回 (中文, 英文)"""
    zh, en = [], []

    try:
        from .weather import _get_system_location
        loc = _get_system_location()
        if loc:
            lat, lon = (float(x) for x in loc.split(","))
            city_zh = _reverse_city_zh(lat, lon, "")
            if city_zh:
                zh.append(f"用户所在城市: {city_zh}")
                en.append(f"User location: {city_zh}")
    except Exception:
        pass

    try:
        def _sysctl(key):
            return subprocess.check_output(
                ["/usr/sbin/sysctl", "-n", key], text=True, timeout=3).strip()

        chip = _sysctl("machdep.cpu.brand_string")
        mem_gb = int(_sysctl("hw.memsize")) // (1024 ** 3)
        ncpu = _sysctl("hw.ncpu")

        model_name = ""
        try:
            sp = subprocess.check_output(
                ["/usr/sbin/system_profiler", "SPHardwareDataType"],
                text=True, timeout=8)
            for line in sp.splitlines():
                if "Model Name:" in line:
                    model_name = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass

        stat = os.statvfs("/")
        disk_total = f"{(stat.f_frsize * stat.f_blocks) / (1024 ** 3):.0f}GB"
        disk_free = f"{(stat.f_frsize * stat.f_bavail) / (1024 ** 3):.0f}GB"

        mac_ver = platform.mac_ver()[0]
        parts_zh = [model_name or "Mac", chip or "Apple Silicon"]
        parts_en = list(parts_zh)
        parts_zh.append(f"{ncpu}核")
        parts_en.append(f"{ncpu} cores")
        parts_zh.append(f"{mem_gb}GB内存")
        parts_en.append(f"{mem_gb}GB RAM")
        parts_zh.append(f"磁盘{disk_total}(可用{disk_free})")
        parts_en.append(f"Disk {disk_total} ({disk_free} free)")
        parts_zh.append(f"macOS {mac_ver}")
        parts_en.append(f"macOS {mac_ver}")
        zh.append("硬件: " + ", ".join(parts_zh))
        en.append("Hardware: " + ", ".join(parts_en))
    except Exception:
        mac_ver = platform.mac_ver()[0]
        zh.append(f"系统: macOS {mac_ver}")
        en.append(f"System: macOS {mac_ver}")

    return "\n".join(zh), "\n".join(en)


def _current_models_context():
    """实时从 config.yaml 读取当前选中的模型，返回 (中文, 英文)"""
    try:
        from .models import current_selection
        sel = current_selection()
    except Exception:
        sel = {}

    m_zh, m_en = [], []

    stt = sel.get("stt", cfg.WHISPER_MODEL)
    stt_short = stt.split("/")[-1] if stt else cfg.WHISPER_MODEL
    m_zh.append(f"STT: {stt_short}")
    m_en.append(f"STT: {stt_short}")

    llm_repo = sel.get("llm", cfg.LOCAL_LLM_REPO)
    if llm_repo:
        m_zh.append(f"本地LLM: {llm_repo.split('/')[-1]}")
        m_en.append(f"Local LLM: {llm_repo.split('/')[-1]}")

    agent = sel.get("agent_model", cfg.API_MODEL)
    if agent:
        m_zh.append(f"云端Agent: {agent}")
        m_en.append(f"Cloud Agent: {agent}")

    vision = sel.get("vision", cfg.VISION_MODEL)
    if vision:
        m_zh.append(f"视觉: {vision.split('/')[-1]}")
        m_en.append(f"Vision: {vision.split('/')[-1]}")

    tts = sel.get("tts", "")
    if tts == "edge-tts":
        m_zh.append("TTS: Edge TTS (云端)")
        m_en.append("TTS: Edge TTS (cloud)")
    elif tts:
        m_zh.append(f"TTS: {tts.split('/')[-1]}")
        m_en.append(f"TTS: {tts.split('/')[-1]}")

    return "搭载模型: " + ", ".join(m_zh), "Models: " + ", ".join(m_en)


def warmup_context():
    """启动时调用，预收集硬件环境信息"""
    global _hw_context_zh, _hw_context_en
    logger.info("收集系统环境信息...")
    _hw_context_zh, _hw_context_en = _gather_hw_context()
    models_zh, _ = _current_models_context()
    full = f"{_hw_context_zh}\n{models_zh}" if _hw_context_zh else models_zh
    logger.info("环境上下文:\n%s", full)


def get_env_context() -> dict:
    """返回中英双语运行时环境上下文（供 dashboard 展示）"""
    models_zh, models_en = _current_models_context()
    zh = f"{_hw_context_zh}\n{models_zh}" if _hw_context_zh else models_zh
    en = f"{_hw_context_en}\n{models_en}" if _hw_context_en else models_en
    return {"zh": zh, "en": en}


def _build_prompt():
    """每次调用动态生成系统提示词（含实时时间 + 实时模型）"""
    now = _dt.datetime.now()
    time_zh = f"当前时间: {now.strftime('%Y年%m月%d日 %H时%M分')} {_WEEKDAY_ZH[now.weekday()]}"
    time_en = f"Current time: {now.strftime('%Y-%m-%d %H:%M')} {_WEEKDAY_EN[now.weekday()]}"
    models_zh, models_en = _current_models_context()
    hw_zh = f"{_hw_context_zh}\n{models_zh}" if _hw_context_zh else models_zh
    hw_en = f"{_hw_context_en}\n{models_en}" if _hw_context_en else models_en
    env_zh = f"\n{time_zh}\n{hw_zh}"
    env_en = f"\n{time_en}\n{hw_en}"
    zh = (
        "你是Bandy，运行在用户Mac上的语音助手，用户通过语音和你交流，你的回答会被TTS朗读出来。"
        f"你的云端大模型是{cfg.API_MODEL}。"
        "要求：1.用纯文本回复，禁止Markdown。2.简洁口语化，1到3句话。3.不加括号说明。4.用中文回复。"
        "5.禁止使用任何emoji、图标、特殊符号字符。6.数字中的小数点读作'点'，例如2.5读作2点5。"
        "7.报时必须精确到分钟，例如'现在是下午4点23分'。"
        f"\n\n[系统环境]{env_zh}"
    )
    en = (
        "You are Bandy, a voice assistant on the user's Mac. Your reply is read aloud by TTS. "
        f"Your cloud LLM is {cfg.API_MODEL}. "
        "Rules: plain text only, no Markdown, no emoji or icon characters, "
        "concise conversational style, 1-3 sentences, reply in English."
        f"\n\n[System Environment]{env_en}"
    )
    return zh, en

_SENT_BREAK = re.compile(r'[。！？!?\n]|\.(?!\d)')


async def call_streaming(assistant, prompt):
    """流式调用 LLM, 流水线 TTS (合成与播放并行, 消除句间停顿)."""
    import aiohttp

    use_local = cfg.LLM_PROVIDER == "local" and cfg.LOCAL_LLM_REPO
    if use_local:
        api_url = cfg.LOCAL_LLM_URL + "/chat/completions"
        api_key = cfg.LOCAL_LLM_KEY
        api_model = cfg.LOCAL_LLM_REPO
    else:
        api_url = cfg.API_URL
        api_key = cfg.API_KEY
        api_model = cfg.API_MODEL

    sys_zh, sys_en = _build_prompt()
    sys_p = sys_en if _ui_lang == 'en' else sys_zh
    messages = [{"role": "system", "content": sys_p}]
    for h in assistant._recent_history(limit=50):
        messages.append({"role": h["role"], "content": h["text"]})
    messages.append({"role": "user", "content": prompt})

    req_body = {"model": api_model, "messages": messages, "stream": True}
    if use_local:
        req_body["max_tokens"] = 500
        req_body["chat_template_kwargs"] = {"enable_thinking": False}

    try:
        session = await assistant._get_session()
        _t_start = _time.time()
        _t_first_token = 0.0
        _token_count = 0
        resp = await session.post(
            api_url, headers={"Authorization": f"Bearer {api_key}"},
            json=req_body,
            timeout=aiohttp.ClientTimeout(total=60))

        voice = "en-US-AriaNeural" if _ui_lang == 'en' else "zh-CN-XiaoyiNeural"
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
            import subprocess, time as _t, queue as _q
            async with assistant._speak_lock:
                while True:
                    item = await pipe.get()
                    if item is None:
                        break
                    try:
                        path = await item
                    except (Exception, asyncio.CancelledError):
                        continue
                    assistant._barge_in = False
                    assistant._is_speaking = True
                    proc = subprocess.Popen(
                        ["afplay", "-r", cfg.PLAYBACK_SPEED, path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    assistant._playback_proc = proc
                    await asyncio.to_thread(proc.wait)
                    assistant._playback_proc = None
                    assistant._is_speaking = False
                    bargein = assistant._barge_in
                    if bargein:
                        assistant._speak_end_time = _t.time() - cfg.SPEAK_COOLDOWN + 0.2
                    else:
                        assistant._speak_end_time = _t.time()
                    try:
                        os.remove(path)
                    except OSError:
                        pass
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
        src = "本地" if use_local else "云端"
        if full:
            print(f"🤖 回复({src}): {strip_markdown(full)}", flush=True)

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

        cleaned = strip_markdown(full) if full else ""
        if not cleaned and full:
            return _TOOL_CALL_SENTINEL
        return cleaned or "抱歉，没有收到回复"
    except (Exception, asyncio.CancelledError) as e:
        print(f"⚠️ API 错误: {e}", flush=True)
        return "抱歉，网络出了点问题，请再说一次"


_TOOL_CALL_SENTINEL = "__TOOL_CALL__"


async def call_api(assistant, prompt):
    """非流式调用 (备用)"""
    try:
        import aiohttp
        sys_zh, sys_en = _build_prompt()
        sys_p = sys_en if _ui_lang == 'en' else sys_zh
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
