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

_env_context = ""
_env_context_en = ""

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


_REGION_ZH = {
    "Jiangsu": "江苏", "Zhejiang": "浙江", "Shanghai": "上海",
    "Beijing": "北京", "Guangdong": "广东", "Sichuan": "四川",
    "Hubei": "湖北", "Hunan": "湖南", "Fujian": "福建",
    "Shandong": "山东", "Henan": "河南", "Hebei": "河北",
    "Anhui": "安徽", "Jiangxi": "江西", "Liaoning": "辽宁",
    "Chongqing": "重庆", "Tianjin": "天津", "Shaanxi": "陕西",
    "Shanxi": "山西", "Yunnan": "云南", "Guizhou": "贵州",
    "Guangxi": "广西", "Hainan": "海南", "Gansu": "甘肃",
    "Inner Mongolia": "内蒙古", "Tibet": "西藏", "Xinjiang": "新疆",
    "Ningxia": "宁夏", "Qinghai": "青海", "Heilongjiang": "黑龙江",
    "Jilin": "吉林", "Taiwan": "台湾", "Hong Kong": "香港", "Macau": "澳门",
}
_WEEKDAY_ZH = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
_WEEKDAY_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _gather_env_context():
    """收集系统环境信息，返回 (中文, 英文) 双版本"""
    zh, en = [], []

    now = _dt.datetime.now()
    zh.append(f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M')} {_WEEKDAY_ZH[now.weekday()]}")
    en.append(f"Current time: {now.strftime('%Y-%m-%d %H:%M')} {_WEEKDAY_EN[now.weekday()]}")

    try:
        from .weather import _get_system_location, get_weather
        import requests as _req
        loc = _get_system_location()
        if loc:
            try:
                proxy = {"http": cfg.PROXY_HTTP, "https": cfg.PROXY_HTTPS} if cfg.PROXY_HTTP else None
                wr = _req.get(f"https://wttr.in/{loc}?format=j1&lang=zh", timeout=10, proxies=proxy)
                wd = wr.json()
                area = wd.get("nearest_area", [{}])[0]
                region = area.get("region", [{}])[0].get("value", "")
                area_name = area.get("areaName", [{}])[0].get("value", "")
                region_zh = _REGION_ZH.get(region, region)
                lat = float(area.get("latitude", 0))
                lon = float(area.get("longitude", 0))
                city_zh = _reverse_city_zh(lat, lon, area_name)
                city_label_zh = f"{region_zh}{city_zh}".strip() if region_zh else city_zh
                city_label_en = f"{area_name}, {region}".strip(", ") if region else area_name
                if city_label_zh:
                    zh.append(f"用户所在城市: {city_label_zh}")
                    en.append(f"User location: {city_label_en}")
                cc = wd.get("current_condition", [{}])[0]
                if cc:
                    desc_zh, desc_en = "", ""
                    try:
                        desc_zh = cc["lang_zh"][0]["value"]
                    except Exception:
                        pass
                    desc_en = cc.get("weatherDesc", [{}])[0].get("value", "")
                    if not desc_zh:
                        desc_zh = desc_en
                    temp = cc.get("temp_C", "")
                    humidity = cc.get("humidity", "")
                    zh.append(f"天气: {desc_zh}，{temp}度，湿度{humidity}%")
                    en.append(f"Weather: {desc_en}, {temp}°C, humidity {humidity}%")
            except Exception:
                weather = get_weather()
                if weather and "失败" not in weather:
                    zh.append(f"天气: {weather}")
                    en.append(f"Weather: {weather}")
        else:
            weather = get_weather()
            if weather and "失败" not in weather:
                zh.append(f"天气: {weather}")
                en.append(f"Weather: {weather}")
    except Exception:
        pass

    try:
        sp = subprocess.check_output(
            ["system_profiler", "SPHardwareDataType"], text=True, timeout=5)
        model_name, chip_name = "", ""
        for line in sp.splitlines():
            line = line.strip()
            if line.startswith("Model Name:"):
                model_name = line.split(":", 1)[1].strip()
            elif line.startswith("Chip:"):
                chip_name = line.split(":", 1)[1].strip()
        mem_bytes = int(subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True, timeout=3).strip())
        mem_gb = mem_bytes // (1024 ** 3)
        mac_ver = platform.mac_ver()[0]
        hw_zh = f"硬件: {model_name or 'Mac'}, {chip_name or 'Apple Silicon'}, {mem_gb}GB内存, macOS {mac_ver}"
        hw_en = f"Hardware: {model_name or 'Mac'}, {chip_name or 'Apple Silicon'}, {mem_gb}GB RAM, macOS {mac_ver}"
        zh.append(hw_zh)
        en.append(hw_en)
    except Exception:
        mac_ver = platform.mac_ver()[0]
        zh.append(f"系统: macOS {mac_ver}")
        en.append(f"System: macOS {mac_ver}")

    m_zh, m_en = [], []
    m_zh.append(f"STT: Whisper ({cfg.WHISPER_MODEL})")
    m_en.append(f"STT: Whisper ({cfg.WHISPER_MODEL})")
    local_llm_repo = cfg._raw.get("local_llm", {}).get("repo", "")
    if local_llm_repo:
        short = local_llm_repo.split('/')[-1]
        m_zh.append(f"本地LLM: {short}")
        m_en.append(f"Local LLM: {short}")
    m_zh.append(f"云端Agent: {cfg.API_MODEL}")
    m_en.append(f"Cloud Agent: {cfg.API_MODEL}")
    vision_model = cfg.VISION_MODEL
    if vision_model:
        short = vision_model.split('/')[-1]
        m_zh.append(f"视觉: {short}")
        m_en.append(f"Vision: {short}")
    tts_cfg = cfg._raw.get("tts", {})
    tts_engine = tts_cfg.get("engine", "edge")
    if tts_engine == "edge":
        m_zh.append("TTS: Edge TTS (云端)")
        m_en.append("TTS: Edge TTS (cloud)")
    else:
        tts_repo = tts_cfg.get("repo", "")
        tts_short = tts_repo.split('/')[-1] if tts_repo else 'local'
        m_zh.append(f"TTS: {tts_short}")
        m_en.append(f"TTS: {tts_short}")
    zh.append("搭载模型: " + ", ".join(m_zh))
    en.append("Models: " + ", ".join(m_en))

    return "\n".join(zh), "\n".join(en)


def warmup_context():
    """启动时调用，预收集环境信息注入系统提示词"""
    global _env_context, _env_context_en, SYS_ZH, SYS_EN
    logger.info("收集系统环境信息...")
    _env_context, _env_context_en = _gather_env_context()
    logger.info("环境上下文:\n%s", _env_context)
    SYS_ZH, SYS_EN = _build_prompt()


def get_env_context() -> dict:
    """返回中英双语运行时环境上下文（供 dashboard 展示）"""
    return {"zh": _env_context, "en": _env_context_en}


def _build_prompt():
    ctx_zh = f"\n\n[系统环境]\n{_env_context}" if _env_context else ""
    ctx_en = f"\n\n[System Environment]\n{_env_context_en}" if _env_context_en else ""
    zh = (
        "你是Bandy，运行在用户Mac上的语音助手，用户通过语音和你交流，你的回答会被TTS朗读出来。"
        f"你的云端大模型是{cfg.API_MODEL}。"
        "要求：1.用纯文本回复，禁止Markdown。2.简洁口语化，1到3句话。3.不加括号说明。4.用中文回复。"
        "5.禁止使用任何emoji、图标、特殊符号字符。6.数字中的小数点读作'点'，例如2.5读作2点5。"
        + ctx_zh
    )
    en = (
        "You are Bandy, a voice assistant on the user's Mac. Your reply is read aloud by TTS. "
        f"Your cloud LLM is {cfg.API_MODEL}. "
        "Rules: plain text only, no Markdown, no emoji or icon characters, "
        "concise conversational style, 1-3 sentences, reply in English."
        + ctx_en
    )
    return zh, en


SYS_ZH, SYS_EN = _build_prompt()

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
