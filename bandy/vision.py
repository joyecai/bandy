"""视觉识别: Ollama MiniCPM-V + imagesnap 抓帧"""
import os
import subprocess
import tempfile
import time as _time

from .config import cfg
from .metrics import store, VisionMetric

_VISION_KW_STRONG = [
    "看看", "看一下", "看下", "拍一下", "拍照", "辨认",
    "look at", "what do you see", "describe", "recognize",
]
_VISION_KW_QUERY = [
    "是什么", "什么东西", "什么品牌", "什么牌子", "什么型号",
    "手里", "手上", "桌上", "面前", "眼前", "前面",
    "what is", "what's this", "what's that",
]


def is_vision_command(text):
    low = text.lower()
    if any(kw in low for kw in _VISION_KW_STRONG):
        return True
    return (sum(1 for kw in _VISION_KW_QUERY if kw in low) >= 1
            and ("什么" in text or "what" in low))


def capture_frame():
    """用 imagesnap 抓取摄像头一帧, 返回临时文件路径."""
    fd, path = tempfile.mkstemp(suffix='.jpg')
    os.close(fd)
    try:
        r = subprocess.run([cfg.IMAGESNAP, "-w", "0.5", path],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and os.path.getsize(path) > 0:
            return path
    except Exception:
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    return None


def vision_query(image_path, prompt="用简洁中文描述你看到了什么", history=None):
    """调用 Ollama 视觉模型识别图片内容, 可带对话历史."""
    import base64
    import requests as req

    store.set_model_info("vision", cfg.VISION_MODEL, f"Ollama @ {cfg.OLLAMA_URL}")

    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()
    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt, "images": [img_b64]})
    t0 = _time.time()
    try:
        resp = req.post(f"{cfg.OLLAMA_URL}/api/chat", json={
            "model": cfg.VISION_MODEL,
            "messages": messages,
            "stream": False,
        }, timeout=60)
        data = resp.json()
        result = data.get("message", {}).get("content", "识别失败")
        store.record_vision(VisionMetric(
            prompt=prompt, result=result, process_time=_time.time() - t0))
        return result
    except Exception as e:
        store.record_vision(VisionMetric(
            prompt=prompt, result=str(e), process_time=_time.time() - t0))
        return f"视觉识别出错: {e}"
