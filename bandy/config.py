"""配置加载: 读取 config.yaml → 全局对象 cfg"""
import os
import yaml

_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def _load():
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class _Cfg:
    def __init__(self, data: dict):
        api = data.get("api", {})
        self.API_URL = api.get("url", "")
        self.API_KEY = api.get("key", "")
        self.API_MODEL = api.get("model", "")

        tg = data.get("telegram", {})
        self.TG_BOT_TOKEN = tg.get("bot_token", "")
        self.TG_CHAT_ID = tg.get("chat_id", "")

        au = data.get("audio", {})
        self.SAMPLE_RATE = au.get("sample_rate", 16000)
        self.CHUNK = au.get("chunk", 480)
        self.CHANNELS = au.get("channels", 1)
        self.INPUT_DEVICE_IDX = au.get("input_device_idx", 1)
        self.SILENCE_AFTER = au.get("silence_after", 0.8)
        self.PRE_SPEECH_BUF = au.get("pre_speech_buf", 0.3)
        self.MIN_SPEECH_DUR = au.get("min_speech_dur", 0.3)
        self.MAX_RECORD_SEC = au.get("max_record_sec", 10)
        self.NOISE_CAL_SEC = au.get("noise_cal_sec", 1.0)
        self.SPEAK_COOLDOWN = au.get("speak_cooldown", 0.5)
        self.PLAYBACK_SPEED = str(au.get("playback_speed", 1.1))

        wh = data.get("whisper", {})
        self.WHISPER_MODEL = wh.get("model", "small")
        self.WHISPER_DEVICE = wh.get("device", "auto")
        self.WHISPER_COMPUTE = wh.get("compute_type", "int8")

        vi = data.get("vision", {})
        self.VISION_MODEL = vi.get("model", "minicpm-v")
        self.OLLAMA_URL = vi.get("ollama_url", "http://localhost:11434")
        self.IMAGESNAP = vi.get("imagesnap", "/opt/homebrew/bin/imagesnap")
        self.VISION_CONTEXT_TTL = vi.get("context_ttl", 60)

        cam = data.get("camera", {})
        self.LINK_CTL = cam.get("link_ctl", "/opt/homebrew/bin/link-ctl")
        self.APP_NAME = cam.get("app_name", "Insta360 Link Controller")
        self.NOD_AMPLITUDE = cam.get("nod_amplitude", 50)

        conv = data.get("conversation", {})
        self.CONVERSATION_TTL = conv.get("ttl", 120)
        self.HISTORY_TTL = conv.get("history_ttl", 10800)
        self.HISTORY_MAX = conv.get("history_max", 50)

        px = data.get("proxy", {})
        self.PROXY_HTTP = px.get("http", "")
        self.PROXY_HTTPS = px.get("https", "")

        self.EXTRA_PATHS = data.get("paths", {}).get("extra", [])

        out = data.get("output", {})
        self.OUTPUT_DIR = out.get("dir", "output")
        self.RETENTION_DAYS = out.get("retention_days", 90)

        dash = data.get("dashboard", {})
        self.DASHBOARD_PORT = dash.get("port", 8765)
        self.DASHBOARD_ENABLED = dash.get("enabled", True)

        self.WAKE_WORD_AGENT = data.get("wake_word", {}).get("agent", "龙虾")
        self.LOCATION_OVERRIDE = data.get("location_override", "")

        self.PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

    @property
    def output_path(self):
        return os.path.join(self.PROJECT_ROOT, self.OUTPUT_DIR)


def _init_env(c: _Cfg):
    path = os.environ.get("PATH", "")
    for p in c.EXTRA_PATHS:
        if p not in path:
            path = p + ":" + path
    os.environ["PATH"] = path
    if c.PROXY_HTTP:
        os.environ["HTTP_PROXY"] = c.PROXY_HTTP
    if c.PROXY_HTTPS:
        os.environ["HTTPS_PROXY"] = c.PROXY_HTTPS


cfg = _Cfg(_load())
_init_env(cfg)
