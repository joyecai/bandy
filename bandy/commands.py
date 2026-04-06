"""指令路由: process_command"""
import os
import time
import asyncio

from .config import cfg
from .utils import strip_markdown
from .wake import is_wake_word, strip_wake_word
from .metrics import store
from .weather import parse_weather_query, get_weather
from .vision import is_vision_command, capture_frame, vision_query
from .camera import (camera_nod, camera_center, camera_pan, camera_tilt,
                     camera_zoom_rel, camera_privacy, camera_mode,
                     enable_ai_tracking, disable_ai_tracking)
from .telegram import send_tg_file
from .agent import needs_agent, run_agent_bg, _FILE_RE


def _is_en() -> bool:
    from .llm import get_ui_lang
    return get_ui_lang() == "en"


def _t(zh: str, en: str) -> str:
    return en if _is_en() else zh


async def process_command(assistant, text):
    if not text:
        return

    now = time.time()
    in_conv = assistant.conversation_mode and (now - assistant.last_command_time) < cfg.CONVERSATION_TTL
    print(f"👤 你说: {text}", flush=True)
    assistant._record("user", text)

    has_dismiss = "退下" in text or "dismiss" in text.lower()

    if has_dismiss:
        assistant._kill_playback()
        assistant._end_conversation()
        asyncio.create_task(asyncio.to_thread(assistant._dismiss_bg))
        return await assistant._reply(_t("好的，我先退下了", "OK, I'll step back"))

    if cfg.WAKE_WORD_AGENT in text:
        import re
        _aw = re.escape(cfg.WAKE_WORD_AGENT)
        question = re.sub(
            rf'(?:你)?(?:让|叫|问|跟|告诉|请)?{_aw}\s*', '', text
        ).strip()
        question = re.sub(r'^(?:去|来|帮我|帮忙)\s*', '', question).strip()
        if not question:
            return await assistant._reply(_t("在", "Yes?"))
        t = asyncio.create_task(run_agent_bg(assistant, question))
        assistant._bg_tasks.add(t)
        t.add_done_callback(assistant._bg_tasks.discard)
        return

    if is_wake_word(text):
        if in_conv:
            text = strip_wake_word(text)
            if not text:
                return
        else:
            assistant.conversation_mode = True
            assistant.last_command_time = now
            assistant._session_start = now
            store.new_session()
            remainder = strip_wake_word(text)
            speak_task = asyncio.create_task(assistant._reply(_t("在", "Yes?")))
            if not assistant.ai_tracking_active:
                assistant.ai_tracking_active = True
                asyncio.create_task(assistant._start_tracking())
            await speak_task
            if not remainder:
                return
            text = remainder
            in_conv = True

    if not in_conv:
        return

    assistant.last_command_time = now

    low = text.lower()
    resp = None

    # -- 摄像头指令 (需开启摄像头) --
    cam_action = None
    if not cfg.VISION_ENABLED:
        pass
    elif "点" in text and "头" in text or "nod" in low:
        cam_action = camera_nod
        resp = _t("好的", "OK")
    elif "复位" in text or "居中" in text or "回正" in text or "center" in low:
        cam_action = camera_center
        resp = _t("好的，已复位", "OK, centered")
    elif any(w in text for w in ["向左", "左转", "往左"]) or "turn left" in low:
        cam_action = lambda: camera_pan("left")
        resp = _t("好的，向左转", "Turning left")
    elif any(w in text for w in ["向右", "右转", "往右"]) or "turn right" in low:
        cam_action = lambda: camera_pan("right")
        resp = _t("好的，向右转", "Turning right")
    elif any(w in text for w in ["抬头", "向上", "往上"]) or "look up" in low:
        cam_action = lambda: camera_tilt("up")
        resp = _t("好的，向上", "Looking up")
    elif any(w in text for w in ["低头", "向下", "往下"]) or "look down" in low:
        cam_action = lambda: camera_tilt("down")
        resp = _t("好的，向下", "Looking down")
    elif any(w in text for w in ["放大", "拉近"]) or "zoom in" in low:
        cam_action = lambda: camera_zoom_rel(50)
        resp = _t("好的，已放大", "Zoomed in")
    elif any(w in text for w in ["缩小", "拉远"]) or "zoom out" in low:
        cam_action = lambda: camera_zoom_rel(-50)
        resp = _t("好的，已缩小", "Zoomed out")
    elif "隐私" in text or "privacy" in low:
        on = "关" not in text and "off" not in low
        cam_action = lambda: camera_privacy(on)
        resp = _t("隐私模式已开启", "Privacy mode on") if on else _t("隐私模式已关闭", "Privacy mode off")
    elif "桌面模式" in text or "俯拍" in text or "deskview" in low:
        cam_action = lambda: camera_mode("deskview")
        resp = _t("已切换到桌面模式", "Switched to desk view")
    elif "白板" in text or "whiteboard" in low:
        cam_action = lambda: camera_mode("whiteboard")
        resp = _t("已切换到白板模式", "Switched to whiteboard mode")
    elif "俯视" in text or "顶部" in text or "overhead" in low:
        cam_action = lambda: camera_mode("overhead")
        resp = _t("已切换到俯视模式", "Switched to overhead mode")
    elif "普通模式" in text or "正常模式" in text or "取消模式" in text or "normal" in low:
        cam_action = lambda: camera_mode("normal")
        resp = _t("已切换到普通模式", "Switched to normal mode")
    elif "开启追踪" in text or "开追踪" in text:
        cam_action = enable_ai_tracking
        assistant.ai_tracking_active = True
        resp = _t("AI追踪已开启", "AI tracking on")
    elif "关闭追踪" in text or "关追踪" in text:
        cam_action = disable_ai_tracking
        assistant.ai_tracking_active = False
        resp = _t("AI追踪已关闭", "AI tracking off")

    if cam_action:
        asyncio.create_task(asyncio.to_thread(cam_action))
        return await assistant._reply(resp)

    # -- 视觉识别 (需开启摄像头) --
    in_vision_ctx = (cfg.VISION_ENABLED
                     and time.time() - assistant._vision_time < cfg.VISION_CONTEXT_TTL
                     and assistant._vision_frame and os.path.isfile(assistant._vision_frame))
    trigger_vision = cfg.VISION_ENABLED and is_vision_command(text)

    if trigger_vision or in_vision_ctx:
        if trigger_vision:
            await assistant._reply(_t("我看看", "Let me see"))
            frame_path = await asyncio.to_thread(capture_frame)
            if not frame_path:
                return await assistant._reply(_t("摄像头抓帧失败，请确认摄像头已开启",
                                                 "Camera capture failed, please check the camera"))
            if assistant._vision_frame:
                try:
                    os.remove(assistant._vision_frame)
                except OSError:
                    pass
            assistant._vision_frame = frame_path
            assistant._vision_time = time.time()
            assistant._vision_history = []
        default_prompt = _t(
            "请仔细观察图片中的物体，用简洁中文准确描述你看到了什么，包括物体的类型、颜色和特征",
            "Describe what you see in the image concisely, including object type, color and features")
        prompt = text if len(text) > 5 else default_prompt
        result = await asyncio.to_thread(
            vision_query, assistant._vision_frame, prompt,
            assistant._vision_history or None)
        assistant._vision_history.append({"role": "user", "content": prompt})
        assistant._vision_history.append({"role": "assistant", "content": result})
        if len(assistant._vision_history) > 10:
            assistant._vision_history = assistant._vision_history[-10:]
        print(f"👁️ 视觉识别: {result}", flush=True)
        return await assistant._reply(strip_markdown(result))

    # -- 报时 --
    _time_kw = ("几点", "几時", "时间", "時間", "what time", "what's the time")
    if any(w in low for w in _time_kw):
        import datetime
        _now = datetime.datetime.now()
        _h, _m = _now.hour, _now.minute
        if _is_en():
            _suffix = "AM" if _h < 12 else "PM"
            _h12 = _h if _h <= 12 else _h - 12
            if _h12 == 0:
                _h12 = 12
            resp = f"It's {_h12}:{_m:02d} {_suffix}"
        else:
            _period = "上午" if _h < 12 else "下午"
            _h12 = _h if _h <= 12 else _h - 12
            if _h12 == 0:
                _h12 = 12
            resp = f"现在是{_period}{_h12}点{_m}分"
        return await assistant._reply(resp)

    # -- 其他指令 --
    _weather_kw = ("天气", "气温", "温度", "预报", "几度", "多少度", "冷不冷", "热不热")
    if any(w in text for w in _weather_kw) or any(w in low for w in ["weather", "forecast", "temperature"]):
        city, off, disp, dz = parse_weather_query(text)
        resp = await asyncio.to_thread(get_weather, city, off, disp, dz)
    elif "退出" in text or "结束" in text or "end" in low or "bye" in low:
        assistant._end_conversation()
        resp = _t("好的，对话结束", "OK, conversation ended")
    elif ("发" in text or "send" in low) and ("tg" in low or "telegram" in low):
        resp = await _handle_tg_send(assistant, text)
    elif needs_agent(text):
        t = asyncio.create_task(run_agent_bg(assistant, text))
        assistant._bg_tasks.add(t)
        t.add_done_callback(assistant._bg_tasks.discard)
        return

    if resp:
        return await assistant._reply(resp)

    # LLM 流式
    from .llm import call_streaming, _TOOL_CALL_SENTINEL
    full = await call_streaming(assistant, text)
    if full == _TOOL_CALL_SENTINEL:
        print("🔄 LLM 返回 tool call，转给 agent 执行", flush=True)
        t = asyncio.create_task(run_agent_bg(assistant, text))
        assistant._bg_tasks.add(t)
        t.add_done_callback(assistant._bg_tasks.discard)
        return
    if full:
        assistant._record("assistant", full)


async def _handle_tg_send(assistant, text):
    """处理 '发到TG' 语音指令."""
    output_dir = cfg.output_path
    files = _FILE_RE.findall(text)
    for f in files:
        path = os.path.expanduser(f)
        if os.path.isfile(path):
            ok = await send_tg_file(path, os.path.basename(path))
            return _t("文件已发送到你的Telegram", "File sent to your Telegram") if ok else _t("发送失败，请检查文件或网络", "Send failed")

    all_files = []
    for root, _dirs, fnames in os.walk(output_dir):
        for fn in fnames:
            fp = os.path.join(root, fn)
            all_files.append(fp)
    all_files.sort(key=os.path.getmtime, reverse=True)
    if all_files:
        path = all_files[0]
        name = os.path.basename(path)
        ok = await send_tg_file(path, name)
        return _t(f"已将{name}发送到你的Telegram", f"Sent {name} to your Telegram") if ok else _t("发送失败", "Send failed")
    return _t("没有找到可以发送的文件", "No files found to send")
