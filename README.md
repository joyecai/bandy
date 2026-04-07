<p align="center">
  <h1 align="center">Bandy</h1>
  <p align="center">
    <strong>Local Voice Assistant for Apple Silicon Mac</strong><br>
    在 Apple Silicon Mac 上运行的本地语音助手
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> · <a href="#快速开始">快速开始</a> · <a href="https://github.com/joyecai/bandy/releases">Releases</a> · <a href="https://www.youtube.com/watch?v=2VoQTcYthRI">Demo Video</a>
  </p>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=2VoQTcYthRI">
    <img src="https://img.youtube.com/vi/2VoQTcYthRI/maxresdefault.jpg" alt="Bandy Demo Video" width="640">
  </a>
  <br>
  <sub>Click to watch demo / 点击观看演示视频</sub>
</p>

---

Bandy is a **full-duplex voice assistant** that runs entirely on your Apple Silicon Mac. All core inference — STT, LLM, TTS, and Vision — is accelerated locally via [MLX](https://github.com/ml-explore/mlx), with **no cloud dependency required**.

Bandy 是一个运行在 Apple Silicon Mac 上的**全双工语音助手**，所有核心推理（STT / LLM / TTS / Vision）均通过 [MLX](https://github.com/ml-explore/mlx) 在本地加速完成，**无需云端依赖**即可使用。

## Features / 特性

| | English | 中文 |
|--|---------|------|
| Full-Duplex | Interrupt anytime — no waiting for reply to finish | 语音随时打断，无需等待回复结束 |
| Local MLX | Whisper STT, Qwen3 LLM, Qwen3-TTS / Kokoro TTS, MiniCPM-o Vision | Whisper STT、Qwen3 LLM、Qwen3-TTS / Kokoro TTS、MiniCPM-o Vision 全部本地运行 |
| Web Dashboard | Real-time monitoring, model switching, TTS voice selection, prompt editing | 实时监控、模型切换、TTS 音色选择、系统提示词编辑 |
| Cloud Agent | Optional cloud LLM for complex tasks (OpenClaw Agent) | 云端大模型执行复杂任务（可选） |
| Telegram | Remote voice/text commands, file push | 远程语音/文字指令、文件推送（可选） |
| Camera | Insta360 Link AI tracking & gimbal control | Insta360 Link AI 追踪、云台控制（可选） |
| Bilingual | Dashboard & assistant in Chinese or English | Dashboard 语言切换，助手自动跟随 |

## System Requirements / 系统要求

| | Requirement / 要求 |
|--|---------------------|
| macOS | 13.0+ (Ventura or later) |
| Chip / 芯片 | Apple Silicon (M1 / M2 / M3 / M4) |
| RAM / 内存 | 8 GB min, 16 GB+ recommended |
| Python | 3.10+ |
| Homebrew | Recommended / 推荐安装 |

## Quick Start

```bash
git clone https://github.com/joyecai/bandy.git
cd bandy
python3 install.py
```

The guided installer will walk you through:

| Step | Description | Required? |
|------|-------------|-----------|
| System Check | Verify macOS / Apple Silicon / Python | Yes |
| Install Deps | pip install + brew install ffmpeg, imagesnap | Yes |
| Configure | API Key / Telegram / Proxy (all skippable) | Optional |
| Download Models | Whisper small + Qwen3-1.7B (minimal set) | Optional |
| System Service | Register LaunchAgent (Dashboard auto-start) | Yes |
| Desktop Shortcut | Create `Bandy.app` on Desktop | Yes |

Then double-click **Bandy.app** on your desktop to open the Dashboard, click **Start**, and say **"Bandy"** to wake it up.

## 快速开始

```bash
git clone https://github.com/joyecai/bandy.git
cd bandy
python3 install.py
```

安装引导会依次完成：

| 步骤 | 说明 | 是否必须 |
|------|------|----------|
| 系统检查 | 验证 macOS / Apple Silicon / Python 版本 | 是 |
| 安装依赖 | pip 安装 + brew 安装 ffmpeg / imagesnap | 是 |
| 配置 | API Key / Telegram / 代理 等（可跳过） | 可选 |
| 下载模型 | Whisper small + Qwen3-1.7B（默认最小集） | 可选 |
| 系统服务 | 注册 LaunchAgent（Dashboard 开机自启） | 是 |
| 桌面快捷方式 | 生成 `Bandy.app` 到桌面 | 是 |

双击桌面 **Bandy.app** 打开 Dashboard，点击 **启动**，对着麦克风说 **"Bandy"** 唤醒。

## Models / 可选模型

All models can be switched in the Dashboard. 所有模型可在 Dashboard 中一键切换：

| Category | Model | Size | Note |
|----------|-------|------|------|
| STT | whisper-small-mlx | 290 MB | Default, ~30x real-time |
| LLM | Qwen3-1.7B-4bit | 1.1 GB | Recommended — best speed/quality balance |
| LLM | Qwen3-0.6B-4bit | 335 MB | Ultra-fast, short conversations |
| TTS | Edge TTS | Cloud | Default, fluent Chinese |
| TTS | Kokoro-82M | 82 MB | Ultra-fast local, English only |
| TTS | Qwen3-TTS-CustomVoice | 3.7 GB | 9 voices, voice cloning |
| Vision | MiniCPM-o-4.5 | 4.0 GB | Default vision model |

## Configuration / 配置

`bandy_config.yaml` is auto-generated during installation. You can also edit it manually or via the Dashboard prompt editor:

`bandy_config.yaml` 在安装引导时自动生成，也可手动编辑或通过 Dashboard 提示词编辑器修改：

```yaml
api:
  url: "http://your-api/v1/chat/completions"
  key: "your-key"
  model: "minimax/minimax-m2.5"

local_llm:
  repo: "mlx-community/Qwen3-1.7B-4bit"

tts:
  engine: edge              # edge (cloud) or mlx (local)
  mlx_repo: "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
  mlx_voice: serena

# Custom system prompts (editable via Dashboard)
system_prompt: "你是Bandy，运行在用户Mac上的语音助手..."
system_prompt_en: "You are Bandy, a voice assistant on the user's Mac..."

telegram:
  bot_token: "your-token"
  chat_id: "your-id"

proxy:
  http: "http://127.0.0.1:7890"
```

## Project Structure / 项目结构

```
bandy/
├── install.py              # Guided installer / 安装引导脚本
├── main.py                 # Voice assistant entry / 语音助手入口
├── serve.py                # Dashboard server entry / Dashboard 服务入口
├── bandy_config.yaml.example  # Config template / 配置模板
├── requirements.txt        # Python dependencies
├── bandy/
│   ├── assistant.py        # Voice assistant main loop (VAD/recording/playback)
│   ├── commands.py         # Command routing (camera/weather/time/vision)
│   ├── llm.py              # LLM calls (local MLX / cloud API)
│   ├── tts.py              # TTS synthesis (Edge / Kokoro / Qwen3-TTS)
│   ├── stt.py              # Whisper speech recognition
│   ├── vision.py           # MLX-VLM vision recognition
│   ├── agent.py            # OpenClaw Agent for complex tasks
│   ├── dashboard.py        # Dashboard Web API
│   ├── dashboard.html      # Dashboard frontend
│   ├── models.py           # Model discovery & management
│   ├── metrics.py          # Performance metrics
│   ├── config.py           # Config loader
│   ├── weather.py          # Weather query
│   ├── camera.py           # Insta360 camera control
│   ├── tg_bot.py           # Telegram Bot
│   └── wake.py             # Wake word detection
└── setup_permissions.sh    # macOS permission check
```

## Commands / 常用命令

```bash
# Start/Stop Dashboard  启动/停止 Dashboard
launchctl start com.openclaw.dashboard
launchctl stop com.openclaw.dashboard

# Start/Stop Bandy (or use Dashboard)  启动/停止 Bandy
launchctl start com.openclaw.voiceassistant
launchctl stop com.openclaw.voiceassistant

# View logs  查看日志
tail -f ~/.openclaw/logs/voice-assistant.log
tail -f ~/.openclaw/logs/dashboard.log

# Re-run installer  重新运行安装引导
python3 install.py
```

## Voice Commands / 语音指令

| Command / 指令 | Description / 说明 |
|----------------|---------------------|
| "Bandy" | Wake up / 唤醒 |
| "退下" / "dismiss" | End conversation / 结束对话 |
| "现在几点" / "what time" | Tell time / 报时 |
| "今天天气" / "weather" | Weather query / 天气查询 |
| "看看这是什么" / "what is this" | Vision recognition / 视觉识别 |
| "龙虾，帮我..." / "shrimp, help me..." | Invoke Agent / 调用 Agent |
| "发到 TG" / "send to TG" | Send to Telegram |
| Camera commands | "点头/nod", "向左/left", "放大/zoom in", "隐私/privacy" |

## License

MIT
