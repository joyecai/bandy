"""模型发现与管理: 扫描 HuggingFace 缓存, 分类, 读写 config.yaml + dashboard_state.json"""
import json
import os
import re
import yaml

_HF_CACHE = os.path.expanduser("~/.cache/huggingface/hub")
_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
_STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard_state.json")

_CATEGORY_RULES = [
    ("stt", re.compile(r"(whisper|asr|sensevoice)", re.I)),
    ("tts", re.compile(r"(tts|kokoro)", re.I)),
    ("vision", re.compile(r"(vl|vision|minicpm|smolvlm)", re.I)),
]

_RE_PARAMS = re.compile(r"(\d+(?:\.\d+)?)\s*[Bb](?!it)", re.I)
_RE_PARAMS_M = re.compile(r"(\d+)\s*[Mm](?!ini|ax|od|LP|CP)", re.I)
_RE_QUANT = re.compile(r"(qat[- ]?4bit|4bit|8bit|bf16|fp16|fp32|int8|int4)", re.I)

_MODEL_META = {
    # ── STT ──
    "Systran/faster-whisper-base": {
        "params": "74M", "quant": "FP16", "desc_zh": "Whisper base, 轻量快速", "desc_en": "Whisper base, lightweight & fast",
        "speed_zh": "1s音频≈0.05s", "speed_en": "1s audio≈0.05s",
    },
    "Systran/faster-whisper-small": {
        "params": "244M", "quant": "FP16", "desc_zh": "Whisper small, 均衡之选", "desc_en": "Whisper small, balanced",
        "speed_zh": "1s音频≈0.1s", "speed_en": "1s audio≈0.1s",
    },
    "Systran/faster-whisper-large-v3": {
        "params": "1.5B", "quant": "FP16", "desc_zh": "Whisper large-v3, 高精度", "desc_en": "Whisper large-v3, high accuracy",
        "speed_zh": "1s音频≈0.6s", "speed_en": "1s audio≈0.6s",
    },
    "mobiuslabsgmbh/faster-whisper-large-v3-turbo": {
        "params": "809M", "quant": "FP16", "desc_zh": "large-v3-turbo, 速度精度兼顾", "desc_en": "large-v3-turbo, speed+accuracy",
        "speed_zh": "1s音频≈0.3s", "speed_en": "1s audio≈0.3s",
    },
    "mlx-community/whisper-large-v3-turbo": {
        "params": "809M", "quant": "FP16", "desc_zh": "MLX whisper turbo, Apple Silicon 优化", "desc_en": "MLX whisper turbo, Apple Silicon",
        "speed_zh": "1s音频≈0.2s", "speed_en": "1s audio≈0.2s",
    },
    "mlx-community/Qwen3-ASR-0.6B-8bit": {
        "params": "0.6B", "quant": "8bit", "desc_zh": "Qwen3 ASR, 中英双语, MLX原生", "desc_en": "Qwen3 ASR, zh/en bilingual, MLX native",
        "speed_zh": "1s音频≈0.09s", "speed_en": "1s audio≈0.09s",
    },
    "FunAudioLLM/SenseVoiceSmall": {
        "params": "234M", "quant": "FP32", "desc_zh": "SenseVoice, 多语种+情感识别", "desc_en": "SenseVoice, multilingual+emotion",
        "speed_zh": "1s音频≈0.15s", "speed_en": "1s audio≈0.15s",
    },
    # ── LLM (本地) ── 2B 以下推荐标 ★
    "mlx-community/Qwen3-0.6B-4bit": {
        "params": "0.6B", "quant": "4bit", "desc_zh": "★ 极速, 335MB, 适合简短对话", "desc_en": "★ Ultra-fast, 335MB, short chat",
        "speed_zh": "≈220 tok/s", "speed_en": "≈220 tok/s",
    },
    "mlx-community/Qwen3-1.7B-4bit": {
        "params": "1.7B", "quant": "4bit", "desc_zh": "★ 推荐! 速度与质量最佳平衡", "desc_en": "★ Best balance of speed & quality",
        "speed_zh": "≈120 tok/s", "speed_en": "≈120 tok/s",
    },
    "mlx-community/Qwen3-1.7B-8bit": {
        "params": "1.7B", "quant": "8bit", "desc_zh": "★ 更高精度, 中文质量更好", "desc_en": "★ Higher precision, better Chinese",
        "speed_zh": "≈80 tok/s", "speed_en": "≈80 tok/s",
    },
    "mlx-community/Youtu-LLM-2B": {
        "params": "1.96B", "quant": "BF16", "desc_zh": "★ 128K上下文, 推理能力强", "desc_en": "★ 128K ctx, strong reasoning",
        "speed_zh": "≈200 tok/s (4bit)", "speed_en": "≈200 tok/s (4bit)",
    },
    "mlx-community/SmolLM2-1.7B-Instruct-4bit": {
        "params": "1.7B", "quant": "4bit", "desc_zh": "★ 轻量指令模型, 中文较弱", "desc_en": "★ Multilingual light instruct",
        "speed_zh": "≈110 tok/s", "speed_en": "≈110 tok/s", "en_only": True,
    },
    # ── LLM (本地) ── 2B+
    "mlx-community/gemma-3-4b-it-qat-4bit": {
        "params": "4B", "quant": "QAT-4bit", "desc_zh": "Gemma 3 4B, 轻量对话", "desc_en": "Gemma 3 4B, lightweight chat",
        "speed_zh": "≈25 tok/s", "speed_en": "≈25 tok/s",
    },
    "mlx-community/gemma-3-12b-it-4bit": {
        "params": "12B", "quant": "4bit", "desc_zh": "Gemma 3 12B, 强推理能力", "desc_en": "Gemma 3 12B, strong reasoning",
        "speed_zh": "≈12 tok/s", "speed_en": "≈12 tok/s",
    },
    "mlx-community/gemma-3n-E4B-it-lm-4bit": {
        "params": "4B(E)", "quant": "4bit", "desc_zh": "Gemma 3n E4B, 高效推理", "desc_en": "Gemma 3n E4B, efficient",
        "speed_zh": "≈22 tok/s", "speed_en": "≈22 tok/s",
    },
    "Qwen/Qwen2.5-3B": {
        "params": "3B", "quant": "FP16", "desc_zh": "Qwen2.5 3B, 全精度基座", "desc_en": "Qwen2.5 3B, full precision base",
        "speed_zh": "≈15 tok/s", "speed_en": "≈15 tok/s",
    },
    "Qwen/Qwen3-8B": {
        "params": "8B", "quant": "FP16", "desc_zh": "Qwen3 8B, 全精度, 高质量", "desc_en": "Qwen3 8B, full precision, high quality",
        "speed_zh": "≈6 tok/s", "speed_en": "≈6 tok/s",
    },
    "mlx-community/Qwen3-14B-4bit": {
        "params": "14B", "quant": "4bit", "desc_zh": "Qwen3 14B, 量化版, 强能力", "desc_en": "Qwen3 14B, quantized, powerful",
        "speed_zh": "≈8 tok/s", "speed_en": "≈8 tok/s",
    },
    "mlx-community/Qwen3.5-4B-4bit": {
        "params": "4B", "quant": "4bit", "desc_zh": "Qwen3.5 4B, 最新小模型", "desc_en": "Qwen3.5 4B, latest small model",
        "speed_zh": "≈28 tok/s", "speed_en": "≈28 tok/s",
    },
    # ── TTS ──
    "hexgrad/Kokoro-82M-v1.1-zh": {
        "params": "82M", "quant": "FP32", "desc_zh": "Kokoro 中文版, 轻量高质", "desc_en": "Kokoro Chinese, light & quality",
        "speed_zh": "10字≈0.3s", "speed_en": "10chars≈0.3s",
    },
    "mlx-community/Kokoro-82M-bf16": {
        "params": "82M", "quant": "BF16", "desc_zh": "Kokoro MLX, 仅英文", "desc_en": "Kokoro MLX, English/multi-lang",
        "speed_zh": "10字≈0.3s", "speed_en": "10chars≈0.3s", "en_only": True,
    },
    "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit": {
        "params": "0.6B", "quant": "8bit", "desc_zh": "Qwen3 TTS Base, MLX原生", "desc_en": "Qwen3 TTS Base, MLX native",
        "speed_zh": "10字≈1.1s", "speed_en": "10chars≈1.1s",
    },
    "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit": {
        "params": "0.6B", "quant": "8bit", "desc_zh": "Qwen3 TTS 自定义音色, MLX原生", "desc_en": "Qwen3 TTS CustomVoice, MLX native",
        "speed_zh": "10字≈1.1s", "speed_en": "10chars≈1.1s",
    },
    "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit": {
        "params": "1.7B", "quant": "8bit", "desc_zh": "Qwen3 TTS 大模型, 更高质量", "desc_en": "Qwen3 TTS large, higher quality",
        "speed_zh": "10字≈2s", "speed_en": "10chars≈2s",
    },
    # ── Vision ──
    "andrevp/MiniCPM-o-4_5-MLX-4bit": {
        "params": "8B", "quant": "4bit", "desc_zh": "MiniCPM-o 4.5 MLX版, 多模态", "desc_en": "MiniCPM-o 4.5 MLX, multimodal",
        "speed_zh": "≈3s/张", "speed_en": "≈3s/image",
    },
    "openbmb/MiniCPM-o-4_5": {
        "params": "8B", "quant": "FP16", "desc_zh": "MiniCPM-o 4.5 全精度", "desc_en": "MiniCPM-o 4.5 full precision",
        "speed_zh": "≈6s/张", "speed_en": "≈6s/image",
    },
    "mlx-community/Qwen2.5-VL-3B-Instruct-4bit": {
        "params": "3B", "quant": "4bit", "desc_zh": "Qwen2.5 VL 3B, 轻量视觉", "desc_en": "Qwen2.5 VL 3B, lightweight vision",
        "speed_zh": "≈2s/张", "speed_en": "≈2s/image",
    },
    "mlx-community/Qwen3-VL-8B-Instruct-4bit": {
        "params": "8B", "quant": "4bit", "desc_zh": "Qwen3 VL 8B, 强视觉理解", "desc_en": "Qwen3 VL 8B, strong vision",
        "speed_zh": "≈4s/张", "speed_en": "≈4s/image",
    },
    "mlx-community/SmolVLM-256M-Instruct-bf16": {
        "params": "256M", "quant": "BF16", "desc_zh": "SmolVLM 256M, 仅英文", "desc_en": "SmolVLM 256M, ultra-light",
        "speed_zh": "≈0.5s/张", "speed_en": "≈0.5s/image", "en_only": True,
    },
    "mlx-community/SmolVLM-500M-Instruct-bf16": {
        "params": "500M", "quant": "BF16", "desc_zh": "SmolVLM 500M, 仅英文", "desc_en": "SmolVLM 500M, light vision",
        "speed_zh": "≈1s/张", "speed_en": "≈1s/image", "en_only": True,
    },
}


def _human_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    if total < 1024 ** 2:
        return f"{total / 1024:.0f}K"
    if total < 1024 ** 3:
        return f"{total / 1024 ** 2:.0f}M"
    return f"{total / 1024 ** 3:.1f}G"


def _size_mb(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total / (1024 ** 2)


def _classify(repo: str) -> str:
    for cat, pat in _CATEGORY_RULES:
        if pat.search(repo):
            return cat
    return "llm"


def _extract_meta(repo: str, name: str) -> dict:
    meta = _MODEL_META.get(repo, {})
    params = meta.get("params", "")
    quant = meta.get("quant", "")
    if not params:
        m = _RE_PARAMS.search(name)
        if m:
            params = m.group(1) + "B"
        else:
            m = _RE_PARAMS_M.search(name)
            if m:
                params = m.group(1) + "M"
    if not quant:
        m = _RE_QUANT.search(name)
        quant = m.group(1).upper() if m else ""
    return {
        "params": params, "quant": quant,
        "desc_zh": meta.get("desc_zh", ""), "desc_en": meta.get("desc_en", ""),
        "speed_zh": meta.get("speed_zh", ""), "speed_en": meta.get("speed_en", ""),
        "en_only": meta.get("en_only", False),
    }


def scan_models() -> dict:
    """扫描 HF 缓存, 返回 {stt, llm, tts, vision} 各含模型列表"""
    result = {"stt": [], "llm": [], "tts": [], "vision": []}
    if not os.path.isdir(_HF_CACHE):
        return result

    skip = {"pvad", "spkrec", "gguf"}
    for entry in sorted(os.listdir(_HF_CACHE)):
        if not entry.startswith("models--"):
            continue
        repo = entry[len("models--"):].replace("--", "/")
        low = repo.lower()
        if any(s in low for s in skip):
            continue

        full_path = os.path.join(_HF_CACHE, entry)
        cat = _classify(repo)
        size = _human_size(full_path)
        mb = round(_size_mb(full_path), 1)
        short = repo.split("/")[-1]
        meta = _extract_meta(repo, short)
        result[cat].append({
            "repo": repo, "size": size, "size_mb": mb, "short": short,
            **meta,
        })

    return result


def current_selection() -> dict:
    """从 config.yaml 读取当前选中: stt, llm(本地), agent(云端), tts, vision"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    wh = data.get("whisper", {})
    local = data.get("local_llm", {})
    agent = data.get("agent", {})
    api = data.get("api", {})
    vi = data.get("vision", {})
    tts_cfg = data.get("tts", {})

    tts_sel = "edge-tts"
    if tts_cfg.get("engine") == "local" or tts_cfg.get("engine") == "qwen3":
        tts_sel = tts_cfg.get("repo", tts_cfg.get("qwen3", {}).get("repo", "edge-tts"))

    return {
        "stt": wh.get("model", "small"),
        "llm": local.get("repo", ""),
        "agent_model": agent.get("model", api.get("model", "")),
        "agent_provider": agent.get("provider", ""),
        "tts": tts_sel,
        "vision": vi.get("model", ""),
    }


def save_selection(category: str, repo: str) -> bool:
    """保存模型选择到 config.yaml + dashboard_state.json"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if category == "stt":
        low = repo.lower()
        if "faster-whisper" in low:
            short = repo.split("/")[-1].replace("faster-whisper-", "")
            data.setdefault("whisper", {})["model"] = short
        elif "asr" in low or "sensevoice" in low:
            data.setdefault("asr", {})["model_dir"] = repo
        else:
            data.setdefault("whisper", {})["model"] = repo
    elif category == "llm":
        data.setdefault("local_llm", {})["repo"] = repo
    elif category == "agent":
        data.setdefault("agent", {})["model"] = repo
        data.setdefault("api", {})["model"] = repo
    elif category == "tts":
        if repo == "edge-tts":
            data.setdefault("tts", {})["engine"] = "edge"
        else:
            data.setdefault("tts", {})["engine"] = "local"
            data["tts"]["repo"] = repo
    elif category == "vision":
        data.setdefault("vision", {})["model"] = repo
    else:
        return False

    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _refresh_state()
    return True


# ── dashboard_state.json 持久化 ──

def _refresh_state():
    """重新扫描并写入 dashboard_state.json"""
    state = {
        "available": scan_models(),
        "selected": current_selection(),
        "prompts": get_prompts(),
    }
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state


def load_state() -> dict:
    """面板启动时加载: 优先读 JSON 缓存，不存在则重新扫描"""
    if os.path.isfile(_STATE_PATH):
        try:
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return _refresh_state()


def refresh_state() -> dict:
    """强制重新扫描并更新 JSON"""
    return _refresh_state()


def get_prompts() -> dict:
    """读取中英双语系统提示词"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    agent = data.get("agent", {})
    return {
        "llm_zh": data.get("system_prompt", ""),
        "llm_en": data.get("system_prompt_en", ""),
        "agent_zh": agent.get("system_prompt", ""),
        "agent_en": agent.get("system_prompt_en", ""),
    }


def save_prompt(category: str, lang: str, prompt: str) -> bool:
    """保存系统提示词 (category: llm/agent, lang: zh/en)"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    key = "system_prompt" if lang == "zh" else "system_prompt_en"
    if category == "llm":
        data[key] = prompt
    elif category == "agent":
        data.setdefault("agent", {})[key] = prompt
    else:
        return False

    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _refresh_state()
    return True
