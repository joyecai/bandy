# Bandy — Mac 本地语音助手

Bandy 是一个运行在 Apple Silicon Mac 上的全双工语音助手，所有核心推理（STT / LLM / TTS / Vision）均在本地 MLX 加速完成，无需云端依赖即可使用。

## 特性

- **全双工对话** — 语音随时打断，无需等待回复结束
- **本地 MLX 推理** — Whisper STT、Qwen3 LLM、Qwen3-TTS / Kokoro TTS、MiniCPM-o Vision 全部本地运行
- **Web Dashboard** — 实时监控、模型切换、TTS 音色选择、提示词编辑
- **OpenClaw Agent** — 云端大模型执行复杂任务（可选）
- **Telegram 集成** — 远程语音/文字指令、文件推送（可选）
- **摄像头控制** — Insta360 Link AI 追踪、云台控制（可选）
- **中英双语** — Dashboard 语言切换，助手自动跟随

## 系统要求

| 项目 | 要求 |
|------|------|
| macOS | 13.0+ |
| 芯片 | Apple Silicon (M1/M2/M3/M4) |
| 内存 | 8GB 最低, 16GB+ 推荐 |
| Python | 3.10+ |
| Homebrew | 推荐安装 |

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/joyecai/bandy.git
cd bandy
```

### 2. 运行安装引导

```bash
python3 install.py
```

安装引导会依次完成：

| 步骤 | 说明 | 是否必须 |
|------|------|----------|
| 系统检查 | 验证 macOS / Apple Silicon / Python 版本 | 是 |
| 安装依赖 | pip 安装 + brew 安装 ffmpeg / imagesnap | 是 |
| 配置 | API Key / Telegram / 代理 等 | 可跳过 |
| 下载模型 | Whisper small + Qwen3-1.7B (默认最小集) | 可跳过 |
| 系统服务 | 注册 LaunchAgent (Dashboard 开机自启) | 是 |
| 桌面快捷方式 | 生成 `Bandy.app` 到桌面 | 是 |

### 3. 打开 Dashboard

双击桌面 **Bandy.app**，默认浏览器会打开 Dashboard：

```
http://localhost:8765
```

### 4. 下载模型（如安装时跳过）

在 Dashboard 中点击任意模型卡片，未下载的模型会显示 **下载** 按钮，点击即可在线下载。

### 5. 启动 Bandy

在 Dashboard 左上角点击 **启动** 按钮，等待模型加载完成后：

- 对着麦克风说 **"Bandy"** 唤醒
- 语音对话，随时说话可打断
- 说 **"退下"** 结束对话

## 项目结构

```
bandy/
├── install.py              # 安装引导脚本
├── main.py                 # 语音助手入口
├── serve.py                # Dashboard 独立服务入口
├── config.yaml.example     # 配置模板
├── requirements.txt        # Python 依赖
├── bandy/
│   ├── assistant.py        # 语音助手主循环 (VAD/录音/播放)
│   ├── commands.py         # 指令路由 (摄像头/天气/报时/视觉)
│   ├── llm.py              # LLM 调用 (本地 MLX / 云端 API)
│   ├── tts.py              # TTS 合成 (Edge / Kokoro / Qwen3-TTS)
│   ├── stt.py              # Whisper 语音识别
│   ├── vision.py           # MLX-VLM 视觉识别
│   ├── agent.py            # OpenClaw Agent 复杂任务
│   ├── dashboard.py        # Dashboard Web API
│   ├── dashboard.html      # Dashboard 前端
│   ├── models.py           # 模型发现与管理
│   ├── metrics.py          # 性能指标收集
│   ├── config.py           # 配置加载
│   ├── weather.py          # 天气查询
│   ├── camera.py           # Insta360 摄像头控制
│   ├── tg_bot.py           # Telegram Bot
│   └── wake.py             # 唤醒词检测
└── setup_permissions.sh    # macOS 权限检查脚本
```

## 配置说明

`config.yaml` 在安装引导时自动生成，也可手动编辑：

```yaml
# 云端 API (Agent 使用, 可选)
api:
  url: "http://your-api/v1/chat/completions"
  key: "your-key"
  model: "minimax/minimax-m2.5"

# 本地 LLM
local_llm:
  repo: "mlx-community/Qwen3-1.7B-4bit"

# TTS 引擎: edge (云端) 或 mlx (本地)
tts:
  engine: edge
  mlx_repo: "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
  mlx_voice: serena

# Telegram (可选)
telegram:
  bot_token: "your-token"
  chat_id: "your-id"

# 网络代理 (可选)
proxy:
  http: "http://127.0.0.1:7890"
```

## 可选模型

所有模型可在 Dashboard 中一键切换：

| 类别 | 模型 | 大小 | 说明 |
|------|------|------|------|
| STT | whisper-small-mlx | 290M | 默认，速比 30x |
| LLM | Qwen3-1.7B-4bit | 1.1G | 推荐，速度与质量最佳平衡 |
| LLM | Qwen3-0.6B-4bit | 335M | 极速，适合简短对话 |
| TTS | Edge TTS | 云端 | 默认，中文流畅 |
| TTS | Kokoro-82M | 82M | 极速本地，仅英文 |
| TTS | Qwen3-TTS-CustomVoice | 3.7G | 多音色 (9种)，语音克隆 |
| Vision | MiniCPM-o-4.5 | 4.0G | 默认视觉模型 |

## 常用命令

```bash
# 启动/停止 Dashboard
launchctl start com.openclaw.dashboard
launchctl stop com.openclaw.dashboard

# 启动/停止 Bandy (也可通过 Dashboard 操作)
launchctl start com.openclaw.voiceassistant
launchctl stop com.openclaw.voiceassistant

# 查看日志
tail -f ~/.openclaw/logs/voice-assistant.log
tail -f ~/.openclaw/logs/dashboard.log

# 重新运行安装引导
python3 install.py
```

## 语音指令

| 指令 | 说明 |
|------|------|
| "Bandy" | 唤醒 |
| "退下" | 结束对话 |
| "现在几点" | 报时 |
| "今天天气" | 天气查询 |
| "看看这是什么" | 视觉识别 |
| "龙虾，帮我..." | 调用 Agent |
| "发到 TG" | 发送文件到 Telegram |
| 摄像头指令 | "点头" / "向左" / "放大" / "隐私" 等 |

## License

MIT
