"""Dashboard Web 服务: 独立常驻面板，通过 launchctl 管理 Bandy 生命周期"""
import os
import sys
import signal
import asyncio
import subprocess
import logging

from aiohttp import web

from .config import cfg
from .metrics import store
from .models import save_selection, save_voice, refresh_state, get_prompts, save_prompt

logger = logging.getLogger(__name__)

_HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")

_VA_LABEL = "com.openclaw.voiceassistant"


def _va_pid() -> int | None:
    """通过 launchctl 获取语音助手 PID, 未运行返回 None."""
    try:
        out = subprocess.check_output(
            ["launchctl", "list", _VA_LABEL], text=True, stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            if '"PID"' in line:
                return int(line.strip().rstrip(";").split("=")[-1].strip())
    except (subprocess.CalledProcessError, ValueError):
        pass
    return None


def _va_running() -> bool:
    pid = _va_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _va_start():
    subprocess.run(["launchctl", "start", _VA_LABEL],
                   capture_output=True, timeout=5)
    logger.info("已发送 launchctl start %s", _VA_LABEL)


def _va_stop():
    pid = _va_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("已发送 SIGTERM -> PID %d", pid)
    except OSError:
        pass
    for _ in range(30):
        import time; time.sleep(1)
        if not _va_running():
            logger.info("Bandy 已停止")
            return True
    logger.warning("Bandy 未在 30s 内退出")
    return True


async def _handle_start(request):
    if _va_running():
        return web.json_response({"ok": False, "error": "already running"})
    await asyncio.to_thread(_va_start)
    return web.json_response({"ok": True})


async def _handle_stop(request):
    if not _va_running():
        return web.json_response({"ok": False, "error": "not running"})
    ok = await asyncio.to_thread(_va_stop)
    return web.json_response({"ok": ok})


async def _handle_restart(request):
    await asyncio.to_thread(_va_stop)
    await asyncio.to_thread(_va_start)
    return web.json_response({"ok": True})


async def _handle_status(request):
    running = _va_running()
    return web.json_response({"running": running})


async def _handle_models(request):
    state = refresh_state()
    try:
        from .llm import get_env_context
        ctx = get_env_context()
        state["env_context_zh"] = ctx.get("zh", "")
        state["env_context_en"] = ctx.get("en", "")
    except Exception:
        state.setdefault("env_context_zh", "")
        state.setdefault("env_context_en", "")
    return web.json_response(state)


async def _handle_switch_model(request):
    body = await request.json()
    cat = body.get("category", "")
    repo = body.get("repo", "")
    if not cat or not repo:
        return web.json_response({"ok": False, "error": "missing category or repo"})
    ok = save_selection(cat, repo)
    state = refresh_state()
    return web.json_response({"ok": ok, "restart_required": True, "state": state})


async def _handle_switch_voice(request):
    body = await request.json()
    voice_id = body.get("voice", "")
    if not voice_id:
        return web.json_response({"ok": False, "error": "missing voice"})
    ok = save_voice(voice_id)
    state = refresh_state()
    return web.json_response({"ok": ok, "restart_required": True, "state": state})


_PREVIEW_DIR = os.path.expanduser("~/.openclaw/tts_preview")
_preview_lock = asyncio.Lock()


def _gen_preview_sync(repo: str, voice: str, name: str, out_path: str):
    """子进程内生成试听音频."""
    text = f"hi，我是{name}"
    if repo == "edge-tts":
        import edge_tts, asyncio as _aio
        mp3 = out_path.replace(".wav", ".mp3")
        _aio.run(edge_tts.Communicate(text, "zh-CN-XiaoyiNeural").save(mp3))
        import subprocess as _sp
        _sp.run(["ffmpeg", "-y", "-i", mp3, "-ar", "24000", out_path],
                capture_output=True, timeout=10)
        try:
            os.remove(mp3)
        except OSError:
            pass
    else:
        from mlx_audio.tts.utils import load_model
        import numpy as np, soundfile as sf
        model = load_model(repo)
        kw = {"text": text, "verbose": False}
        if voice:
            kw["voice"] = voice
        results = list(model.generate(**kw))
        audio = np.array(results[0].audio)
        sf.write(out_path, audio, model.sample_rate)


_download_status = {}


async def _handle_model_download(request):
    """下载 HuggingFace 模型 (后台执行)."""
    body = await request.json()
    repo = body.get("repo", "")
    if not repo or repo.startswith("/"):
        return web.json_response({"ok": False, "error": "invalid repo"})

    if repo in _download_status and _download_status[repo].get("running"):
        return web.json_response({"ok": False, "error": "already downloading"})

    _download_status[repo] = {"running": True, "done": False, "error": ""}

    async def _do_download():
        import subprocess as sp
        env = os.environ.copy()
        env.pop("HF_HUB_OFFLINE", None)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c",
                f"from huggingface_hub import snapshot_download; snapshot_download('{repo}')",
                env=env, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                _download_status[repo] = {"running": False, "done": True, "error": ""}
            else:
                err = stderr.decode().strip().split("\n")[-1] if stderr else "unknown"
                _download_status[repo] = {"running": False, "done": False, "error": err}
        except Exception as e:
            _download_status[repo] = {"running": False, "done": False, "error": str(e)}

    asyncio.create_task(_do_download())
    return web.json_response({"ok": True, "status": "downloading"})


async def _handle_model_download_status(request):
    repo = request.query.get("repo", "")
    if repo in _download_status:
        return web.json_response(_download_status[repo])
    return web.json_response({"running": False, "done": False, "error": ""})


async def _handle_tts_preview(request):
    body = await request.json()
    repo = body.get("repo", "")
    voice = body.get("voice", "")
    name = body.get("name", "")
    if not repo or not name:
        return web.json_response({"ok": False, "error": "missing params"})

    os.makedirs(_PREVIEW_DIR, exist_ok=True)
    safe_key = f"{repo.replace('/', '_')}_{voice or 'default'}"
    out_path = os.path.join(_PREVIEW_DIR, f"{safe_key}.wav")

    if not os.path.exists(out_path):
        async with _preview_lock:
            if not os.path.exists(out_path):
                try:
                    await asyncio.to_thread(
                        _gen_preview_sync, repo, voice, name, out_path)
                except Exception as e:
                    logger.exception("试听生成失败")
                    return web.json_response({"ok": False, "error": str(e)})

    return web.FileResponse(out_path, headers={
        "Content-Type": "audio/wav",
        "Cache-Control": "public, max-age=86400",
    })


async def _handle_index(request):
    with open(_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')


async def _handle_metrics(request):
    from .metrics import MetricsStore
    data = MetricsStore.read_from_file()
    if data is not None:
        return web.json_response(data)
    return web.json_response(store.snapshot())


async def _handle_clear_sessions(request):
    from .metrics import CLEAR_FLAG
    try:
        with open(CLEAR_FLAG, "w") as f:
            f.write("1")
    except OSError:
        pass
    store.clear_sessions()
    return web.json_response({"ok": True})


async def _handle_get_prompts(request):
    data = get_prompts()
    try:
        from .llm import get_env_context
        ctx = get_env_context()
        data["env_context_zh"] = ctx.get("zh", "")
        data["env_context_en"] = ctx.get("en", "")
    except Exception:
        data["env_context_zh"] = ""
        data["env_context_en"] = ""
    return web.json_response(data)


async def _handle_save_prompt(request):
    body = await request.json()
    cat = body.get("category", "")
    lang = body.get("lang", "zh")
    prompt = body.get("prompt", "")
    if cat not in ("llm", "agent") or lang not in ("zh", "en"):
        return web.json_response({"ok": False, "error": "invalid params"})
    ok = save_prompt(cat, lang, prompt)
    return web.json_response({"ok": ok, "restart_required": True})


async def _handle_set_lang(request):
    body = await request.json()
    lang = body.get("lang", "zh")
    from .llm import set_ui_lang
    set_ui_lang(lang)
    return web.json_response({"ok": True, "lang": lang})


async def _handle_get_vision_enabled(request):
    import yaml
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        enabled = data.get("vision", {}).get("enabled", True)
    except Exception:
        enabled = True
    return web.json_response({"enabled": enabled})


async def _handle_set_vision_enabled(request):
    import yaml
    body = await request.json()
    enabled = bool(body.get("enabled", True))
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("vision", {})["enabled"] = enabled
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return web.json_response({"ok": True, "enabled": enabled, "restart_required": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})


async def _handle_dashboard_reload(request):
    """重启整个面板进程（launchd KeepAlive 会自动拉起）"""
    logger.info("收到面板重启请求，即将退出进程...")
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return web.json_response({"ok": True})


async def start_dashboard(port=None):
    if port is None:
        port = cfg.DASHBOARD_PORT
    app = web.Application()
    app.router.add_get('/', _handle_index)
    app.router.add_get('/api/metrics', _handle_metrics)
    app.router.add_post('/api/sessions/clear', _handle_clear_sessions)
    app.router.add_get('/api/status', _handle_status)
    app.router.add_post('/api/start', _handle_start)
    app.router.add_post('/api/stop', _handle_stop)
    app.router.add_post('/api/restart', _handle_restart)
    app.router.add_post('/api/lang', _handle_set_lang)
    app.router.add_get('/api/models', _handle_models)
    app.router.add_post('/api/models/switch', _handle_switch_model)
    app.router.add_post('/api/models/voice', _handle_switch_voice)
    app.router.add_post('/api/tts/preview', _handle_tts_preview)
    app.router.add_post('/api/models/download', _handle_model_download)
    app.router.add_get('/api/models/download/status', _handle_model_download_status)
    app.router.add_get('/api/prompts', _handle_get_prompts)
    app.router.add_post('/api/prompts/save', _handle_save_prompt)
    app.router.add_get('/api/vision/enabled', _handle_get_vision_enabled)
    app.router.add_post('/api/vision/enabled', _handle_set_vision_enabled)
    app.router.add_post('/api/dashboard/reload', _handle_dashboard_reload)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"📊 Dashboard: http://localhost:{port}", flush=True)
    return runner
