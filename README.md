# Bandy — macOS 全双工语音助手

基于 Apple Silicon MLX 加速的本地语音助手。支持全双工语音交互、本地 LLM / 视觉 / 语音识别 / 语音合成，可选云端 Agent 执行复杂任务。

## 架构

```
                         ┌──────────────────────┐
                         │   Dashboard (Web UI)  │  ← serve.py 常驻
                         │  模型管理 · 会话记录   │     http://localhost:8765
                         │  提示词编辑 · 启停控制  │
                         └──────────┬───────────┘
                                    │ launchctl
┌───────────────────────────────────▼──────────────────────────────────┐
│                   VoiceAssistant (main.py)                           │
│                                                                      │
│  ┌──────────┐   ┌──────┐   ┌─────────────┐   ┌───────────────────┐  │
│  │ PyAudio  │──▶│ VAD  │──▶│ MLX Whisper │──▶│    Commands 路由   │  │
│  │ 全双工录音 │   │高通滤波│   │    STT      │   │                   │  │
│  └──────────┘   │噪声校准│   └─────────────┘   │ 唤醒 / 退出 / 天气 │  │
│                 └──────┘                      │ 摄像头 / 视觉识别  │  │
│                                               │ TG / Agent / LLM  │  │
│  ┌──────────────┐  ┌───────────┐              └──┬──┬──┬──────────┘  │
│  │ MLX Vision   │  │ WeatherKit│                 │  │  │             │
│  │ MiniCPM-o    │◀─┘ (Swift)  │◀────────────────┘  │  │             │
│  └──────────────┘  └───────────┘                    │  │             │
│                                                     │  │             │
│  ┌──────────────────┐   ┌───────────────────────┐   │  │             │
│  │ 本地 LLM (MLX)   │◀──┤ 云端 Agent (OpenClaw) │◀──┘  │             │
│  │ mlx_lm.server    │   │ 复杂任务异步执行        │      │             │
│  └────────┬─────────┘   └───────────────────────┘      │             │
│           │                                             │             │
│  ┌────────▼──────────────────────────────────────┐      │             │
│  │ TTS: Edge TTS (云端) / Qwen3-TTS (本地 MLX)  │◀─────┘             │
│  │ → afplay 播放 · Barge-in 打断                  │                   │
│  └────────────────────────────────────────────────┘                   │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────┐                              │
│  │ Telegram Bot     │  │ Insta360 Link│                              │
│  │ 语音消息 · 文件推送│  │ 云台 · 追踪   │                              │
│  └──────────────────┘  └──────────────┘                              │
└──────────────────────────────────────────────────────────────────────┘
```

## 模型体系

| 类型 | 引擎 | 默认模型 | 加速 |
|------|------|----------|------|
| **STT** | mlx-whisper | whisper-small-mlx | MLX FP16, ≈30x 实时 |
| **本地 LLM** | mlx_lm.server | Qwen3-1.7B-4bit | MLX 4bit, ≈120 tok/s |
| **云端 Agent** | OpenClaw CLI | MiniMax M2.5 / GPT-4o | 复杂任务编排 |
| **TTS** | Edge TTS / Qwen3-TTS | Edge (云端) 或 Qwen3-TTS-0.6B (本地) | MLX 4bit |
| **Vision** | mlx-vlm | MiniCPM-o 4.5 MLX 4bit | MLX 4bit, ≈3s/张 |

所有本地模型在 Dashboard 面板上一键切换，模型列表自动扫描 HuggingFace 缓存。

## 核心特性

- **全双工语音** — PyAudio 实时采集，高通滤波 + RMS VAD，环境噪声自动校准
- **Barge-in** — 说话打断 TTS 播放，无需等待回复结束
- **唤醒词** — "Bandy" / "班迪" 唤醒，支持模糊拼音匹配；"退下" 结束对话
- **会话管理** — 唤醒→对话→退出为独立会话，超时自动退出，上下文仅限当前会话
- **Dashboard 面板** — 独立常驻 Web UI，模型切换 / 系统提示词编辑 / 会话记录 / 性能指标
- **视觉识别** — "看看这是什么" 触发摄像头拍照 + 本地 VLM 理解
- **天气查询** — macOS WeatherKit + 系统定位，支持城市名和日期偏移
- **摄像头控制** — Insta360 Link 云台、AI 追踪、变焦、隐私模式、桌面/白板模式
- **Agent** — "龙虾" 唤醒词触发 OpenClaw Agent，后台异步执行复杂任务
- **Telegram** — 语音消息转文字、文件自动推送、消息发送

## 安装

**系统要求**: macOS + Apple Silicon (M1/M2/M3/M4), Python 3.11+

```bash
git clone https://github.com/joyecai/bandy.git
cd bandy
pip install -r requirements.txt
brew install imagesnap    # 摄像头抓帧
```

## 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 API 密钥和模型路径
```

关键配置项:

| 配置 | 说明 |
|------|------|
| `api.url` / `api.key` / `api.model` | 云端 LLM API |
| `local_llm.repo` | 本地 LLM 模型 (HuggingFace repo ID) |
| `vision.model` | 本地视觉模型路径 |
| `tts.engine` | TTS 引擎: `edge` (云端) 或 `qwen` (本地) |
| `whisper.model` | MLX Whisper 模型 |
| `dashboard.port` | 面板端口 (默认 8765) |
| `telegram.bot_token` | Telegram Bot Token |

## 运行

**推荐: 面板模式**

```bash
python serve.py
# 浏览器打开 http://localhost:8765
# 点击 "启动 Bandy" 按钮
```

**直连模式**

```bash
python main.py
```

**macOS LaunchAgent 自启动**

Dashboard 和 Bandy 均可通过 LaunchAgent plist 配置为开机自启。Dashboard 设为 `KeepAlive: true` 常驻，Bandy 通过面板按钮按需启停。

## 目录结构

```
├── serve.py                     # 面板入口 (推荐)
├── main.py                      # 直连入口
├── config.yaml                  # 用户配置 (不入库)
├── config.yaml.example          # 配置模板
├── requirements.txt             # Python 依赖
├── setup_permissions.sh         # macOS 权限引导脚本
├── bandy/
│   ├── assistant.py             # VoiceAssistant 主类: 录音、VAD、主循环
│   ├── commands.py              # 指令路由: 唤醒/退出/摄像头/天气/视觉/LLM/Agent
│   ├── config.py                # 配置加载 (config.yaml → cfg 对象)
│   ├── dashboard.py             # Dashboard API: launchctl 生命周期管理
│   ├── dashboard.html           # Dashboard 前端 (单文件 HTML/JS/CSS)
│   ├── models.py                # 模型发现: HF 缓存扫描、分类、选择持久化
│   ├── metrics.py               # 性能指标: STT/LLM/TTS/Vision 统计 + 文件 IPC
│   ├── llm.py                   # LLM: 流式对话 + 环境上下文注入
│   ├── stt.py                   # STT: mlx-whisper 加载与推理
│   ├── tts.py                   # TTS: Edge TTS / Qwen3-TTS + afplay 播放
│   ├── vision.py                # Vision: mlx-vlm 本地推理 + imagesnap 抓帧
│   ├── wake.py                  # 唤醒词: 精确 + 模糊拼音匹配
│   ├── weather.py               # 天气: macOS WeatherKit + Swift 桥接
│   ├── weatherkit_query.swift   # WeatherKit Swift 脚本
│   ├── camera.py                # 摄像头: Insta360 Link HTTP 控制
│   ├── agent.py                 # Agent: OpenClaw CLI 调用 + 异步任务
│   ├── telegram.py              # Telegram: 消息/文件发送
│   ├── tg_bot.py                # Telegram Bot: 长轮询接收
│   ├── utils.py                 # 工具: 繁简转换、语言检测、Markdown 清理
│   └── output.py                # 输出管理: 按日期归档、过期清理
└── output/                      # 生成文件 (按日期子目录，不入库)
```

## 唤醒词

| 唤醒词 | 作用 |
|--------|------|
| **Bandy** / **班迪** | 唤醒助手，进入对话模式 |
| **退下** | 结束对话，关闭摄像头 |
| **龙虾** (可配置) | 触发 OpenClaw Agent |

## License

MIT
