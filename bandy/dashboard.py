"""Dashboard Web 服务: 独立常驻面板，管理 Bandy 生命周期"""
import os
import signal
import asyncio
import subprocess
import threading
import logging

from aiohttp import web

from .config import cfg
from .metrics import store
from .models import save_selection, refresh_state, get_prompts, save_prompt

logger = logging.getLogger(__name__)

_HTML_PATH = os.path.join(os.path.dirname(__file__), "dashboard.html")

_assistant = None
_assistant_thread = None
_lock = threading.Lock()


def _run_assistant():
    global _assistant
    local_va = None
    try:
        from .output import cleanup_old_output
        from .assistant import VoiceAssistant
        cleanup_old_output()
        cfg.DASHBOARD_ENABLED = False
        local_va = VoiceAssistant()
        local_va.running = True
        _assistant = local_va
        asyncio.run(local_va.run())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        logger.exception("Bandy 线程异常退出")
    finally:
        store.end_session()
        if local_va:
            local_va.running = False
        with _lock:
            if _assistant is local_va:
                _assistant = None


def _do_stop():
    """停止语音助手并等待线程真正退出"""
    global _assistant, _assistant_thread
    with _lock:
        va = _assistant
        th = _assistant_thread
    if not va or not va.running:
        return False
    if va.conversation_mode:
        va._end_conversation()
        va._dismiss_bg()
    store.end_session()
    va._shutdown()
    if th:
        for _ in range(30):
            th.join(timeout=1)
            if not th.is_alive():
                break
        if th.is_alive():
            logger.warning("助手线程未在 30s 内退出")
    with _lock:
        if _assistant is va:
            _assistant = None
        _assistant_thread = None
    logger.info("Bandy 已完全停止")
    return True


def _do_start():
    """启动语音助手线程（先重新加载配置）"""
    global _assistant_thread
    from .config import reload as _reload_cfg
    _reload_cfg()
    with _lock:
        _assistant_thread = threading.Thread(target=_run_assistant, daemon=True)
        _assistant_thread.start()


async def _handle_start(request):
    if _assistant and _assistant.running:
        return web.json_response({"ok": False, "error": "already running"})
    await asyncio.to_thread(_do_start)
    return web.json_response({"ok": True})


async def _handle_stop(request):
    ok = await asyncio.to_thread(_do_stop)
    if ok:
        return web.json_response({"ok": True})
    return web.json_response({"ok": False, "error": "not running"})


async def _handle_restart(request):
    await asyncio.to_thread(_do_stop)
    await asyncio.to_thread(_do_start)
    return web.json_response({"ok": True})


async def _handle_status(request):
    running = bool(_assistant and _assistant.running)
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


async def _handle_index(request):
    with open(_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')


async def _handle_metrics(request):
    return web.json_response(store.snapshot())


async def _handle_clear_sessions(request):
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


async def _handle_dashboard_reload(request):
    """重启整个面板进程（launchd KeepAlive 会自动拉起）"""
    logger.info("收到面板重启请求，即将退出进程...")
    asyncio.get_event_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
    return web.json_response({"ok": True})


def _kill_port(port: int):
    """启动前释放被占用的端口"""
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True).strip()
        for pid in out.split():
            pid = pid.strip()
            if pid and pid != str(os.getpid()):
                os.kill(int(pid), 9)
                logger.info("已终止占用端口 %s 的进程 (PID %s)", port, pid)
    except (subprocess.CalledProcessError, OSError):
        pass


async def start_dashboard(port=None):
    if port is None:
        port = cfg.DASHBOARD_PORT
    _kill_port(port)
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
    app.router.add_get('/api/prompts', _handle_get_prompts)
    app.router.add_post('/api/prompts/save', _handle_save_prompt)
    app.router.add_post('/api/dashboard/reload', _handle_dashboard_reload)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"📊 Dashboard: http://localhost:{port}", flush=True)
    return runner
