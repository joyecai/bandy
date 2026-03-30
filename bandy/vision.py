"""视觉识别: MLX-VLM 本地推理 + imagesnap 抓帧"""
import logging
import os
import subprocess
import tempfile
import time as _time
import threading

from .config import cfg
from .metrics import store, VisionMetric
from .utils import to_simplified, detect_lang

logger = logging.getLogger(__name__)

_VISION_KW_STRONG = [
    "看看", "看一下", "看下", "拍一下", "拍照", "辨认",
    "look at", "what do you see", "describe", "recognize",
]
_VISION_KW_CONTEXT = [
    "手里", "手上", "桌上", "面前", "眼前", "前面",
    "这个", "那个", "这是", "那是",
]
_VISION_KW_OBJECT = [
    "什么东西", "什么品牌", "什么牌子", "什么型号",
    "what is this", "what's this", "what's that",
]
_VISION_EXCLUDE = [
    "模型", "版本", "配置", "设置", "功能", "引擎", "搭载",
    "model", "version", "config", "stt", "tts", "llm", "api",
]

_model = None
_processor = None
_config = None
_lock = threading.Lock()
_loaded = False


def is_vision_command(text):
    low = text.lower()
    if any(ex in low for ex in _VISION_EXCLUDE):
        return False
    if any(kw in low for kw in _VISION_KW_STRONG):
        return True
    if any(kw in low for kw in _VISION_KW_OBJECT):
        return True
    has_context = any(kw in low for kw in _VISION_KW_CONTEXT)
    has_what = "什么" in text or "what" in low
    return has_context and has_what


def _ensure_loaded():
    """按需加载 MLX 视觉模型（线程安全）"""
    global _model, _processor, _config, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        from mlx_vlm import load
        repo = cfg.VISION_MODEL
        logger.info("加载视觉模型: %s ...", repo)
        t0 = _time.time()
        _model, _processor = load(repo)
        _config = _model.config if hasattr(_model, 'config') else None
        _loaded = True
        logger.info("视觉模型就绪 (%.1fs)", _time.time() - t0)


def preload():
    """启动时预热: 在后台线程中预加载模型"""
    if not cfg.VISION_PRELOAD:
        return
    def _warmup():
        _ensure_loaded()
        logger.info("视觉模型预热完成: %s", cfg.VISION_MODEL)
    t = threading.Thread(target=_warmup, daemon=True, name="vision-preload")
    t.start()


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
    """调用 MLX 视觉模型识别图片内容."""
    from mlx_vlm import generate

    _ensure_loaded()
    store.set_model_info("vision", cfg.VISION_MODEL, "MLX-VLM (local)")

    t0 = _time.time()
    try:
        gen = generate(
            _model, _processor,
            image=image_path,
            prompt=prompt,
            max_tokens=256,
            verbose=False,
        )
        result = gen.text if hasattr(gen, 'text') else str(gen)
        if not result or not result.strip():
            result = "识别失败"
        if detect_lang(result) == 'zh':
            result = to_simplified(result)
        store.record_vision(VisionMetric(
            prompt=prompt, result=result, process_time=_time.time() - t0))
        return result
    except Exception as e:
        logger.exception("视觉识别出错")
        store.record_vision(VisionMetric(
            prompt=prompt, result=str(e), process_time=_time.time() - t0))
        return f"视觉识别出错: {e}"
