"""Telegram Bot: 发送消息和文件"""
import os

from .config import cfg


async def send_tg_message(text):
    import aiohttp
    url = f"https://api.telegram.org/bot{cfg.TG_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"chat_id": cfg.TG_CHAT_ID, "text": text},
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                return (await r.json()).get("ok", False)
    except Exception as e:
        print(f"⚠️ TG 发送失败: {e}", flush=True)
        return False


async def send_tg_file(file_path, caption=""):
    import aiohttp
    url = f"https://api.telegram.org/bot{cfg.TG_BOT_TOKEN}/sendDocument"
    if not os.path.isfile(file_path):
        print(f"⚠️ 文件不存在: {file_path}", flush=True)
        return False
    try:
        data = aiohttp.FormData()
        data.add_field("chat_id", cfg.TG_CHAT_ID)
        data.add_field("document", open(file_path, "rb"),
                       filename=os.path.basename(file_path))
        if caption:
            data.add_field("caption", caption)
        async with aiohttp.ClientSession() as s:
            async with s.post(url, data=data,
                              timeout=aiohttp.ClientTimeout(total=60)) as r:
                return (await r.json()).get("ok", False)
    except Exception as e:
        print(f"⚠️ TG 文件发送失败: {e}", flush=True)
        return False
