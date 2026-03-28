"""Insta360 Link 摄像头控制 (via link-ctl WebSocket API)"""
import subprocess
import time

from .config import cfg


def _link(cmd, *args, silent=True):
    """调用 link-ctl CLI, 返回 (returncode, stdout)."""
    argv = [cfg.LINK_CTL] + (["-s"] if silent else []) + [cmd] + list(args)
    r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout.strip()


def _ensure_app():
    """确保 Insta360 Link Controller 主进程正在运行且 WebSocket 就绪, 自动开启 AI 追踪."""
    r = subprocess.run(["pgrep", "-f", "Webcam-desktop"], capture_output=True)
    if r.returncode != 0:
        subprocess.run(["open", "-a", cfg.APP_NAME], capture_output=True)
        for wait in [3, 2, 2, 2, 3]:
            time.sleep(wait)
            rc, _ = _link("status")
            if rc == 0:
                _link("track", "on")
                return
        print("⚠️ Insta360 Link Controller 启动超时", flush=True)


def enable_ai_tracking():
    _ensure_app()
    _link("track", "on")


def disable_ai_tracking():
    _link("track", "off")


def camera_nod(amplitude=None):
    """点头: 关闭追踪 -> 向下 -> 向上(减量补偿惯性) -> 恢复追踪."""
    if amplitude is None:
        amplitude = cfg.NOD_AMPLITUDE
    _link("track", "off")
    step = 30
    pulses_down = []
    remaining = amplitude
    while remaining > 0:
        s = min(step, remaining)
        pulses_down.append(s)
        remaining -= s
    for s in pulses_down:
        _link("tilt-rel", str(-s))
        time.sleep(0.05)
    time.sleep(0.1)
    up_amp = int(amplitude * 0.7)
    pulses_up = []
    remaining = up_amp
    while remaining > 0:
        s = min(step, remaining)
        pulses_up.append(s)
        remaining -= s
    for s in pulses_up:
        _link("tilt-rel", str(s))
        time.sleep(0.05)
    _link("track", "on")


def camera_pan(direction, steps=10):
    val = str(-steps if direction == "left" else steps)
    _link("pan-rel", val)


def camera_tilt(direction, steps=10):
    val = str(-steps if direction == "up" else steps)
    _link("tilt-rel", val)


def camera_center():
    _link("center")


def camera_zoom(value):
    _link("zoom", str(max(100, min(400, value))))


def camera_zoom_rel(delta):
    _link("zoom-rel", str(delta))


def camera_privacy(on=True):
    _link("privacy", "on" if on else "off")


def camera_mode(mode):
    """切换 AI 模式: normal / track / deskview / whiteboard / overhead."""
    _link(mode)


def camera_quit():
    """关闭 Insta360 Link Controller: 直接终止进程."""
    subprocess.run(["pkill", "-9", "-f", "Webcam-desktop"], capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "crashpad_handler.*Insta360"], capture_output=True)
