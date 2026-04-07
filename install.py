#!/usr/bin/env python3
"""Bandy 安装引导 — 新用户 clone 后运行此脚本完成初始化"""
import os
import sys
import shutil
import subprocess
import platform
import textwrap

# ── 常量 ──
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(WORKSPACE, "bandy_config.yaml")
CFG_EXAMPLE = os.path.join(WORKSPACE, "bandy_config.yaml.example")
LOGS_DIR = os.path.expanduser("~/.openclaw/logs")
LA_DIR = os.path.expanduser("~/Library/LaunchAgents")
DESKTOP = os.path.expanduser("~/Desktop")

DEFAULT_MODELS = {
    "stt": "mlx-community/whisper-small-mlx",
    "llm": "mlx-community/Qwen3-1.7B-4bit",
}

BOLD = "\033[1m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
DIM = "\033[0;90m"
NC = "\033[0m"


def _print_banner():
    print(f"""
{CYAN}╔══════════════════════════════════════════╗
║          Bandy 语音助手 · 安装引导        ║
║      Voice Assistant Setup Wizard         ║
╚══════════════════════════════════════════╝{NC}
""")


def _ask(prompt, default="", secret=False):
    suffix = f" [{DIM}{default}{NC}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return val or default


def _ask_yn(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"  {prompt} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    if not val:
        return default
    return val in ("y", "yes")


def _step(num, total, title):
    print(f"\n{BOLD}[{num}/{total}] {title}{NC}")
    print(f"  {'─' * 40}")


# ═══════════════════════════════════════════
# Step 1: System Check
# ═══════════════════════════════════════════
def step_system_check():
    _step(1, 7, "系统检查 System Check")
    ok = True

    if platform.system() != "Darwin":
        print(f"  {RED}✗ 仅支持 macOS{NC}")
        sys.exit(1)
    print(f"  {GREEN}✓{NC} macOS {platform.mac_ver()[0]}")

    chip = subprocess.check_output(
        ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], text=True
    ).strip()
    if "Apple" not in chip:
        print(f"  {RED}✗ 需要 Apple Silicon (M1/M2/M3/M4){NC}")
        sys.exit(1)
    print(f"  {GREEN}✓{NC} {chip}")

    v = sys.version_info
    if v < (3, 10):
        print(f"  {RED}✗ Python >= 3.10 required (current: {v.major}.{v.minor}){NC}")
        sys.exit(1)
    print(f"  {GREEN}✓{NC} Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")

    mem = int(subprocess.check_output(
        ["/usr/sbin/sysctl", "-n", "hw.memsize"], text=True
    ).strip()) // (1024 ** 3)
    print(f"  {GREEN}✓{NC} 统一内存 {mem} GB")
    if mem < 8:
        print(f"  {YELLOW}⚠ 建议 16GB 以上以运行本地 LLM + TTS + Vision{NC}")

    brew = shutil.which("brew")
    if not brew:
        print(f"  {YELLOW}⚠ 未检测到 Homebrew (部分功能需要){NC}")
    else:
        print(f"  {GREEN}✓{NC} Homebrew 已安装")

    return ok


# ═══════════════════════════════════════════
# Step 2: Install Dependencies
# ═══════════════════════════════════════════
def step_install_deps():
    _step(2, 7, "安装依赖 Install Dependencies")
    req = os.path.join(WORKSPACE, "requirements.txt")
    print(f"  正在安装 pip 依赖...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req, "--quiet"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  {RED}✗ pip install 失败:{NC}")
        print(r.stderr[:500])
        if not _ask_yn("继续安装?", default=False):
            sys.exit(1)
    else:
        print(f"  {GREEN}✓{NC} 依赖安装完成")

    for tool in ["ffmpeg", "imagesnap"]:
        if not shutil.which(tool):
            print(f"  {YELLOW}⚠ {tool} 未安装, 正在通过 brew 安装...{NC}")
            subprocess.run(["brew", "install", tool], capture_output=True)
            if shutil.which(tool):
                print(f"  {GREEN}✓{NC} {tool} 安装成功")
            else:
                print(f"  {YELLOW}⚠ {tool} 安装失败, 部分功能受限{NC}")
        else:
            print(f"  {GREEN}✓{NC} {tool} 已就绪")


# ═══════════════════════════════════════════
# Step 3: Configure
# ═══════════════════════════════════════════
def step_configure():
    _step(3, 7, "配置 Configuration")
    cfg = {}

    if os.path.exists(CFG_PATH):
        print(f"  {YELLOW}已检测到 bandy_config.yaml, 是否覆盖?{NC}")
        if not _ask_yn("重新配置?", default=False):
            print(f"  {DIM}跳过配置, 使用现有文件{NC}")
            return
        import yaml
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    print(f"\n  {BOLD}云端 API (用于 Agent 云端大模型, 可跳过){NC}")
    print(f"  {DIM}支持 OpenAI 兼容 API (MiniMax/DeepSeek/OpenAI/Anthropic 等){NC}")
    api_url = _ask("API URL", cfg.get("api", {}).get("url", ""))
    api_key = _ask("API Key (留空跳过)", cfg.get("api", {}).get("key", ""))
    api_model = ""
    if api_key:
        api_model = _ask("模型名称", cfg.get("api", {}).get("model", "minimax/minimax-m2.5"))

    print(f"\n  {BOLD}Telegram 通知 (可跳过){NC}")
    tg_token = _ask("Bot Token (留空跳过)", cfg.get("telegram", {}).get("bot_token", ""))
    tg_chat = ""
    if tg_token:
        tg_chat = _ask("Chat ID", cfg.get("telegram", {}).get("chat_id", ""))

    print(f"\n  {BOLD}网络代理 (可跳过){NC}")
    proxy = _ask("HTTP 代理 (如 http://127.0.0.1:7890, 留空跳过)",
                 cfg.get("proxy", {}).get("http", ""))

    print(f"\n  {BOLD}Dashboard 端口{NC}")
    port = _ask("端口", str(cfg.get("dashboard", {}).get("port", 8765)))

    import yaml
    if os.path.exists(CFG_EXAMPLE):
        with open(CFG_EXAMPLE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    data.setdefault("api", {})
    if api_url:
        data["api"]["url"] = api_url
    if api_key:
        data["api"]["key"] = api_key
    if api_model:
        data["api"]["model"] = api_model
    data.setdefault("agent", {})
    if api_model:
        data["agent"]["model"] = api_model

    data.setdefault("telegram", {})
    if tg_token:
        data["telegram"]["bot_token"] = tg_token
    if tg_chat:
        data["telegram"]["chat_id"] = tg_chat
    data["telegram"]["bot_enabled"] = bool(tg_token)

    data.setdefault("proxy", {})
    data["proxy"]["http"] = proxy
    data["proxy"]["https"] = proxy

    data.setdefault("dashboard", {})
    data["dashboard"]["port"] = int(port)
    data["dashboard"]["enabled"] = True

    data.setdefault("local_llm", {})
    data["local_llm"].setdefault("repo", DEFAULT_MODELS["llm"])
    data["local_llm"].setdefault("server_host", "127.0.0.1")
    data["local_llm"].setdefault("server_port", 8766)

    data.setdefault("whisper", {})
    data["whisper"].setdefault("model", DEFAULT_MODELS["stt"])

    data.setdefault("tts", {})
    data["tts"].setdefault("engine", "edge")

    data.setdefault("vision", {})
    data["vision"].setdefault("preload", False)

    home = os.path.expanduser("~")
    data.setdefault("paths", {})
    data["paths"]["extra"] = [
        os.path.join(home, "Library/Python/3.11/bin"),
        "/opt/homebrew/bin",
    ]

    with open(CFG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  {GREEN}✓{NC} bandy_config.yaml 已生成")


# ═══════════════════════════════════════════
# Step 4: Download Models
# ═══════════════════════════════════════════
def step_download_models():
    _step(4, 7, "下载模型 Download Models")
    print(f"  {DIM}默认下载 STT (Whisper) + LLM (Qwen3-1.7B) 最小可运行集{NC}")
    print(f"  {DIM}TTS 默认使用云端 Edge TTS, 无需下载{NC}")
    print(f"  {DIM}其他模型 (Vision/本地TTS) 可后续在 Dashboard 中切换下载{NC}\n")

    if not _ask_yn("开始下载默认模型?"):
        print(f"  {YELLOW}跳过模型下载, 首次启动时 Dashboard 会提示下载{NC}")
        return

    env = os.environ.copy()
    env.pop("HF_HUB_OFFLINE", None)

    for role, repo in DEFAULT_MODELS.items():
        print(f"\n  ⬇ 下载 {role.upper()}: {CYAN}{repo}{NC} ...")
        r = subprocess.run(
            [sys.executable, "-c",
             f"from huggingface_hub import snapshot_download; snapshot_download('{repo}')"],
            env=env, capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(f"  {GREEN}✓{NC} {repo} 下载完成")
        else:
            err = r.stderr.strip().split("\n")[-1] if r.stderr else "unknown error"
            print(f"  {YELLOW}⚠ 下载失败: {err}{NC}")
            print(f"  {DIM}可稍后在 Dashboard 中重试{NC}")


# ═══════════════════════════════════════════
# Step 5: Setup LaunchAgents
# ═══════════════════════════════════════════
def step_launchagents():
    _step(5, 7, "配置系统服务 Setup LaunchAgents")
    os.makedirs(LA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    python_bin = sys.executable
    home = os.path.expanduser("~")

    import yaml
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    proxy_http = data.get("proxy", {}).get("http", "")

    path_dirs = [
        os.path.join(home, "Library/Python/3.11/bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/opt/node/bin",
        "/usr/local/bin", "/usr/bin", "/usr/sbin", "/bin",
    ]
    path_str = ":".join(path_dirs)

    va_plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.voiceassistant</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>sleep 8; cd {WORKSPACE} &amp;&amp; {python_bin} main.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{path_str}</string>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>{f'''
        <key>HTTP_PROXY</key>
        <string>{proxy_http}</string>
        <key>HTTPS_PROXY</key>
        <string>{proxy_http}</string>''' if proxy_http else ''}
    </dict>
    <key>StandardOutPath</key>
    <string>{LOGS_DIR}/voice-assistant.log</string>
    <key>StandardErrorPath</key>
    <string>{LOGS_DIR}/voice-assistant.err.log</string>
</dict>
</plist>
"""

    dash_plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.dashboard</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>serve.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{WORKSPACE}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{path_str}</string>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
    </dict>
    <key>StandardOutPath</key>
    <string>{LOGS_DIR}/dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>{LOGS_DIR}/dashboard.err.log</string>
</dict>
</plist>
"""

    uid = os.getuid()
    for name, content in [
        ("com.openclaw.voiceassistant", va_plist),
        ("com.openclaw.dashboard", dash_plist),
    ]:
        path = os.path.join(LA_DIR, f"{name}.plist")
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", path],
                       capture_output=True)
        with open(path, "w") as f:
            f.write(content)
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", path],
                       capture_output=True)
        print(f"  {GREEN}✓{NC} {name} 已注册")

    print(f"  {GREEN}✓{NC} Dashboard 将开机自启, Bandy 通过 Dashboard 按钮控制")


# ═══════════════════════════════════════════
# Step 6: Create Desktop Shortcut
# ═══════════════════════════════════════════
def step_shortcut():
    _step(6, 7, "创建桌面快捷方式 Create Shortcut")

    import yaml
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    port = data.get("dashboard", {}).get("port", 8765)

    app_dir = os.path.join(DESKTOP, "Bandy.app")
    macos_dir = os.path.join(app_dir, "Contents", "MacOS")
    res_dir = os.path.join(app_dir, "Contents", "Resources")
    os.makedirs(macos_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    script = f"""\
#!/bin/bash
open "http://localhost:{port}"
"""
    script_path = os.path.join(macos_dir, "Bandy")
    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, 0o755)

    plist = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Bandy</string>
    <key>CFBundleName</key>
    <string>Bandy Dashboard</string>
    <key>CFBundleIdentifier</key>
    <string>com.openclaw.bandy</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""
    with open(os.path.join(app_dir, "Contents", "Info.plist"), "w") as f:
        f.write(plist)

    print(f"  {GREEN}✓{NC} 桌面快捷方式已创建: {CYAN}~/Desktop/Bandy.app{NC}")
    print(f"  {DIM}双击打开 Dashboard (http://localhost:{port}){NC}")


# ═══════════════════════════════════════════
# Step 7: Summary
# ═══════════════════════════════════════════
def step_summary():
    _step(7, 7, "安装完成 Setup Complete!")

    import yaml
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    port = data.get("dashboard", {}).get("port", 8765)

    print(f"""
  {GREEN}✓ Bandy 安装完成!{NC}

  {BOLD}快速开始:{NC}
  1. 双击桌面 {CYAN}Bandy.app{NC} 打开 Dashboard
  2. 在 Dashboard 中点击 {CYAN}启动{NC} 按钮运行 Bandy
  3. 对着麦克风说 {CYAN}"Bandy"{NC} 唤醒语音助手

  {BOLD}Dashboard 地址:{NC} {CYAN}http://localhost:{port}{NC}

  {BOLD}管理命令:{NC}
  {DIM}启动 Dashboard:  launchctl start com.openclaw.dashboard{NC}
  {DIM}启动 Bandy:      launchctl start com.openclaw.voiceassistant{NC}
  {DIM}查看日志:        tail -f ~/.openclaw/logs/voice-assistant.log{NC}

  {BOLD}配置文件:{NC} {DIM}{CFG_PATH}{NC}
  {DIM}可直接编辑或在 Dashboard 中调整模型、提示词等设置{NC}
""")

    subprocess.Popen(["launchctl", "start", "com.openclaw.dashboard"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  {CYAN}正在启动 Dashboard...{NC}")
    import time
    time.sleep(3)
    subprocess.Popen(["open", f"http://localhost:{port}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ═══════════════════════════════════════════
def main():
    _print_banner()
    step_system_check()
    step_install_deps()
    step_configure()
    step_download_models()
    step_launchagents()
    step_shortcut()
    step_summary()


if __name__ == "__main__":
    main()
