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
    # ── STT (MLX Whisper) ──
    "mlx-community/whisper-small-mlx": {
        "params": "244M", "quant": "FP16", "desc_zh": "Whisper small MLX (默认)", "desc_en": "Whisper small MLX (default)",
        "speed_zh": "实测: 5s音频≈0.17s (速比30x)", "speed_en": "bench: 5s audio≈0.17s (30x)",
    },
    # ── LLM (本地 MLX) ──
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
    "mlx-community/Qwen3.5-4B-4bit": {
        "params": "4B", "quant": "4bit", "desc_zh": "Qwen3.5 4B, 最新小模型", "desc_en": "Qwen3.5 4B, latest small model",
        "speed_zh": "实测: ≈24-34 tok/s", "speed_en": "bench: ≈24-34 tok/s",
    },
    "mlx-community/gemma-3-4b-it-qat-4bit": {
        "params": "4B", "quant": "QAT-4bit", "desc_zh": "Gemma 3 4B, 轻量对话", "desc_en": "Gemma 3 4B, lightweight chat",
        "speed_zh": "≈25 tok/s", "speed_en": "≈25 tok/s",
    },
    "mlx-community/Qwen3-14B-4bit": {
        "params": "14B", "quant": "4bit", "desc_zh": "Qwen3 14B, 量化版, 强能力", "desc_en": "Qwen3 14B, quantized, powerful",
        "speed_zh": "≈8 tok/s", "speed_en": "≈8 tok/s",
    },
    # ── TTS ──
    "edge-tts": {
        "params": "云端", "quant": "", "desc_zh": "Edge TTS 微软云端, 中文自然流畅", "desc_en": "Edge TTS Microsoft cloud",
        "speed_zh": "实测: ≈13字/s (含网络)", "speed_en": "bench: ≈13 chars/s (incl. network)",
    },
    "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit": {
        "params": "0.6B", "quant": "8bit", "desc_zh": "Qwen3-TTS 多语音, 语音克隆", "desc_en": "Qwen3-TTS multi-voice, voice clone",
        "speed_zh": "实测: ≈13字/s (RTF 2.3x)", "speed_en": "bench: ≈29 ch/s (RTF 2.3x)",
        "default_voice": "serena",
        "voices": [
            {"id": "serena",   "label": "Serena",   "gender": "F", "lang": "zh", "desc_zh": "温柔知性女声", "desc_en": "Warm gentle female"},
            {"id": "vivian",   "label": "Vivian",   "gender": "F", "lang": "zh", "desc_zh": "明亮利落女声", "desc_en": "Bright edgy female"},
            {"id": "uncle_fu", "label": "Uncle Fu", "gender": "M", "lang": "zh", "desc_zh": "沉稳浑厚男声", "desc_en": "Mellow mature male"},
            {"id": "dylan",    "label": "Dylan",    "gender": "M", "lang": "zh", "desc_zh": "清朗北京男声", "desc_en": "Clear Beijing male"},
            {"id": "eric",     "label": "Eric",     "gender": "M", "lang": "zh", "desc_zh": "活泼成都男声", "desc_en": "Lively Chengdu male"},
            {"id": "ryan",     "label": "Ryan",     "gender": "M", "lang": "en", "desc_zh": "动感英文男声", "desc_en": "Dynamic English male"},
            {"id": "aiden",    "label": "Aiden",    "gender": "M", "lang": "en", "desc_zh": "阳光美式男声", "desc_en": "Sunny American male"},
            {"id": "ono_anna", "label": "Ono Anna", "gender": "F", "lang": "ja", "desc_zh": "灵动日语女声", "desc_en": "Playful Japanese female"},
            {"id": "sohee",    "label": "Sohee",    "gender": "F", "lang": "ko", "desc_zh": "温暖韩语女声", "desc_en": "Warm Korean female"},
        ],
    },
    "mlx-community/Kokoro-82M-bf16": {
        "params": "82M", "quant": "BF16", "desc_zh": "★ Kokoro 极速本地, 仅英文", "desc_en": "★ Kokoro ultra-fast local, English only",
        "speed_zh": "实测: ≈141 ch/s (RTF 10x)", "speed_en": "bench: ≈141 ch/s (RTF 10x)",
        "en_only": True,
    },
    # ── Vision ──
    "/Users/joye/.cache/mlx-models/MiniCPM-o-4_5-mlx-4bit": {
        "params": "8B", "quant": "4bit", "desc_zh": "MiniCPM-o 4.5 MLX 4bit (默认)", "desc_en": "MiniCPM-o 4.5 MLX 4bit (default)",
        "speed_zh": "≈3s/张", "speed_en": "≈3s/image",
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


def _dir_size(path):
    """遍历目录返回 (人类可读字符串, MB 浮点数)."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    mb = total / (1024 ** 2)
    if total < 1024 ** 2:
        human = f"{total / 1024:.0f}K"
    elif total < 1024 ** 3:
        human = f"{mb:.0f}M"
    else:
        human = f"{total / 1024 ** 3:.1f}G"
    return human, mb


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
    voices = meta.get("voices", [])
    return {
        "params": params, "quant": quant,
        "desc_zh": meta.get("desc_zh", ""), "desc_en": meta.get("desc_en", ""),
        "speed_zh": meta.get("speed_zh", ""), "speed_en": meta.get("speed_en", ""),
        "en_only": meta.get("en_only", False),
        "voices": voices,
    }


def scan_models() -> dict:
    """扫描 HF 缓存 + _MODEL_META 中的本地路径, 返回 {stt, llm, tts, vision} 各含模型列表"""
    result = {"stt": [], "llm": [], "tts": [], "vision": []}
    seen_repos = set()

    if os.path.isdir(_HF_CACHE):
        skip = {"pvad", "spkrec", "gguf", "s3tokenizer", "prince-canuma"}
        for entry in sorted(os.listdir(_HF_CACHE)):
            if not entry.startswith("models--"):
                continue
            repo = entry[len("models--"):].replace("--", "/")
            low = repo.lower()
            if any(s in low for s in skip):
                continue

            full_path = os.path.join(_HF_CACHE, entry)
            cat = _classify(repo)
            size, mb = _dir_size(full_path)
            mb = round(mb, 1)
            short = repo.split("/")[-1]
            meta = _extract_meta(repo, short)
            result[cat].append({
                "repo": repo, "size": size, "size_mb": mb, "short": short,
                **meta,
            })
            seen_repos.add(repo)

    for key, meta in _MODEL_META.items():
        if key in seen_repos:
            continue
        if key.startswith("/") and os.path.isdir(key):
            short = os.path.basename(key)
            cat = _classify(short)
            size, mb = _dir_size(key)
            mb = round(mb, 1)
        elif not key.startswith("/") and "/" not in key:
            cat = _classify(key)
            short = key
            size = "-"
            mb = 0
        else:
            continue
        result[cat].append({
            "repo": key, "size": size, "size_mb": mb, "short": short,
            "params": meta.get("params", ""),
            "quant": meta.get("quant", ""),
            "desc_zh": meta.get("desc_zh", ""),
            "desc_en": meta.get("desc_en", ""),
            "speed_zh": meta.get("speed_zh", ""),
            "speed_en": meta.get("speed_en", ""),
            "en_only": meta.get("en_only", False),
            "voices": meta.get("voices", []),
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

    stt_sel = wh.get("model", "mlx-community/whisper-small-mlx")

    tts_engine = tts_cfg.get("engine", "edge")
    if tts_engine == "mlx":
        tts_sel = tts_cfg.get("mlx_repo", "")
    else:
        tts_sel = "edge-tts"

    return {
        "stt": stt_sel,
        "llm": local.get("repo", ""),
        "agent_model": agent.get("model", api.get("model", "")),
        "agent_provider": agent.get("provider", ""),
        "tts": tts_sel,
        "tts_voice": tts_cfg.get("mlx_voice", ""),
        "vision": vi.get("model", ""),
    }


def save_selection(category: str, repo: str) -> bool:
    """保存模型选择到 config.yaml + dashboard_state.json"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if category == "stt":
        data.setdefault("whisper", {})["model"] = repo
        if "asr" in data:
            data["asr"].pop("model_dir", None)
    elif category == "llm":
        data.setdefault("local_llm", {})["repo"] = repo
    elif category == "agent":
        data.setdefault("agent", {})["model"] = repo
        data.setdefault("api", {})["model"] = repo
    elif category == "tts":
        if repo == "edge-tts":
            data.setdefault("tts", {})["engine"] = "edge"
        else:
            data.setdefault("tts", {})["engine"] = "mlx"
            data["tts"]["mlx_repo"] = repo
            default_voice = _MODEL_META.get(repo, {}).get("default_voice", "")
            data["tts"]["mlx_voice"] = default_voice
    elif category == "vision":
        data.setdefault("vision", {})["model"] = repo
    else:
        return False

    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _refresh_state()
    return True


def save_voice(voice_id: str) -> bool:
    """保存 TTS 音色选择到 config.yaml"""
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("tts", {})["mlx_voice"] = voice_id
    with open(_CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _refresh_state()
    return True


def get_voices(repo: str) -> list:
    """获取指定 TTS 模型的可选音色列表"""
    meta = _MODEL_META.get(repo, {})
    return meta.get("voices", [])


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
