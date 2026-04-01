"""视觉识别: MLX-VLM 本地推理 + imagesnap 抓帧"""
import logging
import os
import re as _re
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


def _patch_quantized_vision_dtype():
    """修复 mlx_vlm 0.4.2 bug: 4bit 量化模型 embed_tokens 权重 dtype 为 uint32,
    导致像素值被错误转为 uint32 触发 conv2d 崩溃."""
    import mlx.core as mx
    try:
        import mlx_vlm.models.minicpmo.minicpmo as mod
        original = mod._to_mx_array
        def _fixed_to_mx_array(value, dtype=None):
            if dtype is not None and dtype in (mx.uint32, mx.uint16, mx.uint8):
                dtype = mx.float16
            return original(value, dtype)
        mod._to_mx_array = _fixed_to_mx_array
    except Exception:
        pass


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
        print(f"👁️ 加载视觉模型: {repo} ...", flush=True)
        t0 = _time.time()
        _model, _processor = load(repo)
        _config = _model.config if hasattr(_model, 'config') else None
        _patch_quantized_vision_dtype()
        _loaded = True
        print(f"👁️ 视觉模型就绪 ({_time.time() - t0:.1f}s)", flush=True)


def preload(blocking=False):
    """启动时预热视觉模型。blocking=True 时同步等待加载完成。"""
    if not cfg.VISION_PRELOAD:
        return
    def _warmup():
        try:
            _ensure_loaded()
            print(f"👁️ 视觉模型预热完成: {cfg.VISION_MODEL}", flush=True)
        except Exception as e:
            print(f"⚠️ 视觉模型预热失败: {type(e).__name__}: {e}", flush=True)
    if blocking:
        _warmup()
    else:
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


_CONV_MARKER = _re.compile(
    r'\n\s*(Human|User|Assistant|A:|Q:|H:|请告诉|如果您有|祝您)',
    _re.IGNORECASE)


def _clean_vision_text(text):
    """清洗视觉模型输出: 去掉思维链、对话标记、前缀、重复文本"""
    text = text.strip()
    text = _re.sub(r'<think>.*?</think>\s*', '', text, flags=_re.DOTALL)
    for prefix in ("Assistant:", "assistant:", "A:", "回答:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    m = _CONV_MARKER.search(text)
    if m:
        text = text[:m.start()].strip()
    lines = text.split('\n')
    seen = set()
    deduped = []
    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            deduped.append(line)
    text = '\n'.join(deduped).strip()
    sentences = _re.split(r'(?<=[。！？!?])', text)
    seen_s = set()
    unique = []
    for s in sentences:
        s_clean = s.strip()
        if s_clean and s_clean not in seen_s:
            seen_s.add(s_clean)
            unique.append(s)
    return ''.join(unique).strip()


def vision_query(image_path, prompt="用简洁中文描述你看到了什么", history=None):
    """调用 MLX 视觉模型识别图片内容."""
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    _ensure_loaded()
    store.set_model_info("vision", cfg.VISION_MODEL, "MLX-VLM (local)")

    formatted = apply_chat_template(
        _processor, _config, prompt,
        num_images=1, enable_thinking=False)

    from .tts import _mlx_gpu_lock
    t0 = _time.time()
    try:
        with _mlx_gpu_lock:
            gen = generate(
                _model, _processor,
                image=image_path,
                prompt=formatted,
                max_tokens=150,
                verbose=False,
                repetition_penalty=1.2,
                repetition_context_size=64,
                enable_thinking=False,
            )
        result = gen.text if hasattr(gen, 'text') else str(gen)
        result = _clean_vision_text(result)
        if not result:
            result = "识别失败"
        if detect_lang(result) == 'zh':
            result = to_simplified(result)
        store.record_vision(VisionMetric(
            prompt=prompt, result=result, process_time=_time.time() - t0))
        return result
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        logger.exception("视觉识别出错: %s", err_msg)
        store.record_vision(VisionMetric(
            prompt=prompt, result=err_msg, process_time=_time.time() - t0))
        return f"视觉识别出错，请稍后再试"
