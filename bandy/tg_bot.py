"""Telegram Bot 轮询: 接收消息、语音转文字、转发给 Agent"""
import os
import asyncio
import tempfile

from .config import cfg
from .telegram import send_tg_message


async def _download_file(session, file_id):
    """通过 Telegram API 下载文件, 返回本地临时路径."""
    base = f"https://api.telegram.org/bot{cfg.TG_BOT_TOKEN}"
    async with session.get(f"{base}/getFile", params={"file_id": file_id}) as r:
        data = await r.json()
        if not data.get("ok"):
            return None
        file_path = data["result"]["file_path"]

    url = f"https://api.telegram.org/file/bot{cfg.TG_BOT_TOKEN}/{file_path}"
    ext = os.path.splitext(file_path)[1] or ".ogg"
    fd, local_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    async with session.get(url) as r:
        with open(local_path, "wb") as f:
            f.write(await r.read())
    return local_path


async def run_tg_bot(assistant):
    """长轮询接收 TG 消息, 语音自动转文字."""
    import aiohttp
    from . import stt as stt_mod
    from .agent import needs_agent, run_agent_bg

    base = f"https://api.telegram.org/bot{cfg.TG_BOT_TOKEN}"
    offset = 0
    print("🤖 TG Bot 轮询已启动", flush=True)

    async with aiohttp.ClientSession() as session:
        while assistant.running:
            try:
                params = {"offset": offset, "timeout": 30,
                          "allowed_updates": '["message"]'}
                async with session.get(
                    f"{base}/getUpdates", params=params,
                    timeout=aiohttp.ClientTimeout(total=40)
                ) as r:
                    data = await r.json()

                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg:
                        continue
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id != cfg.TG_CHAT_ID:
                        continue

                    text = None

                    if msg.get("voice") or msg.get("audio"):
                        voice = msg.get("voice") or msg.get("audio")
                        file_id = voice["file_id"]
                        duration = voice.get("duration", 0)
                        print(f"🎤 TG 收到语音 ({duration}s)", flush=True)

                        local_path = await _download_file(session, file_id)
                        if not local_path:
                            await send_tg_message("语音下载失败")
                            continue

                        try:
                            text = await asyncio.to_thread(
                                stt_mod.transcribe_file,
                                assistant.whisper_model, local_path)
                        finally:
                            try:
                                os.remove(local_path)
                            except OSError:
                                pass

                        if not text:
                            await send_tg_message("未能识别语音内容")
                            continue

                        await send_tg_message(f"🗣️ 识别: {text}")
                        print(f"🗣️ TG 语音识别: {text}", flush=True)

                    elif msg.get("text"):
                        text = msg["text"]
                        if text.startswith("/"):
                            if text == "/start":
                                await send_tg_message(
                                    "Bandy 语音助手已连接\n"
                                    "发送语音消息自动转文字\n"
                                    "发送文字直接对话")
                            elif text == "/status":
                                import time
                                uptime = int(time.time() - assistant._history[0]["ts"]) if assistant._history else 0
                                mode = "对话中" if assistant.conversation_mode else "待机"
                                await send_tg_message(
                                    f"状态: {mode}\n"
                                    f"历史消息: {len(assistant._history)} 条\n"
                                    f"Dashboard: http://localhost:{cfg.DASHBOARD_PORT}")
                            continue

                    if not text:
                        continue

                    assistant._record("user", f"[TG] {text}")
                    print(f"💬 TG 消息: {text}", flush=True)

                    reply = await _process_tg_text(assistant, text)
                    if reply:
                        assistant._record("assistant", reply)
                        await send_tg_message(reply)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ TG Bot 错误: {e}", flush=True)
                await asyncio.sleep(5)

    print("🤖 TG Bot 轮询已停止", flush=True)


async def _process_tg_text(assistant, text):
    """TG 消息的命令路由: 天气 → Agent → LLM."""
    from .weather import parse_weather_query, get_weather
    from .agent import needs_agent
    from .utils import strip_markdown

    low = text.lower()

    _weather_kw = ("天气", "气温", "温度", "预报", "几度", "多少度", "冷不冷", "热不热")
    if any(w in text for w in _weather_kw) or any(w in low for w in ["weather", "forecast", "temperature"]):
        city, off, disp, dz = parse_weather_query(text)
        return await asyncio.to_thread(get_weather, city, off, disp, dz)

    if needs_agent(text):
        from .agent import estimate_seconds, format_eta
        est_s = estimate_seconds(text, assistant._task_history)
        await send_tg_message(f"⏳ Bandy 正在处理，预计{format_eta(est_s)}完成")
        asyncio.create_task(_run_agent_and_reply(assistant, text))
        return None

    from .llm import call_api
    reply = await call_api(assistant, text)
    return strip_markdown(reply) if reply else None


async def _run_agent_and_reply(assistant, task):
    """后台运行 agent, 完成后回复到 TG."""
    try:
        from .agent import call_openclaw
        result = await call_openclaw(assistant, task)
        if result:
            assistant._record("assistant", result)
            await send_tg_message(result)
    except Exception as e:
        await send_tg_message(f"任务出错: {e}")
