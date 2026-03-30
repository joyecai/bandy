# Bandy v0.8.0 — 全双工语音助手

基于 macOS + Apple Silicon 的本地语音助手，具备全双工语音交互、本地 LLM 推理、视觉识别、摄像头控制、天气查询、Telegram 集成和 OpenClaw Agent 复杂任务编排能力。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│  serve.py — 独立常驻面板入口                                  │
│  ┌──────────────────────────────────┐                       │
│  │  Dashboard (aiohttp)             │   ← 浏览器 UI         │
│  │  · 模型选择 / 切换               │                       │
│  │  · 系统提示词编辑 (中/英)         │                       │
│  │  · 会话记录 / STT·LLM 性能面板    │                       │
│  │  · Start / Stop Bandy            │                       │
│  └──────────┬───────────────────────┘                       │
│             │ threading.Thread                               │
│  ┌──────────▼───────────────────────────────────────────┐   │
│  │  VoiceAssistant (assistant.py)                        │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │  │ Recorder │→│   VAD    │→│  STT     │            │   │
│  │  │ PyAudio  │  │ 高通滤波  │  │ Whisper  │            │   │
│  │  └──────────┘  │ 噪声校准  │  └────┬─────┘            │   │
│  │                └──────────┘       │                   │   │
│  │                              ┌────▼─────┐             │   │
│  │                              │ Commands │             │   │
│  │                              │ 唤醒/退出  │             │   │
│  │                              │ 指令路由   │             │   │
│  │                              └──┬──┬──┬─┘             │   │
│  │              ┌─────────────┐    │  │  │               │   │
│  │              │ Weather     │◄───┘  │  │               │   │
│  │              │ Camera Ctrl │◄──────┘  │               │   │
│  │              └─────────────┘          │               │   │
│  │                    ┌─────────────────▼──────┐        │   │
│  │                    │     LLM Router         │        │   │
│  │                    │  本地 LLM (MLX)         │        │   │
│  │                    │  云端 Agent (OpenClaw)   │        │   │
│  │                    └──────────┬─────────────┘        │   │
│  │                          ┌────▼─────┐                │   │
│  │                          │   TTS    │                │   │
│  │                          │ Edge TTS │                │   │
│  │                          │ → afplay │                │   │
│  │                          └──────────┘                │   │
│  │                    ┌──────────────┐                   │   │
│  │                    │ Vision (MLX) │ ← 按需加载        │   │
│  │                    │ mlx-vlm      │                   │   │
│  │                    └──────────────┘                   │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 核心特性

### 语音交互
- **全双工录音** — PyAudio 实时采集，高通滤波降噪，自动环境噪声校准
- **VAD** — 基于 RMS 的语音活动检测，预缓冲 + 静音截断
- **唤醒词** — 说 "Bandy" / "班迪" 唤醒，支持模糊拼音匹配
- **会话管理** — 唤醒 → 对话 → "退下"关闭，超时自动退出，每次为独立会话记录
- **Barge-in** — 播放时可通过大声说话打断 TTS 播放

### 模型体系
| 类型 | 引擎 | 说明 |
|------|------|------|
| **STT** | Faster Whisper | 本地语音识别，多语种 |
| **本地 LLM** | MLX (mlx_lm) | Apple Silicon 加速，推荐 Qwen3-1.7B-4bit (≈120 tok/s) |
| **云端 Agent** | OpenClaw API | MiniMax / GPT-4o / Claude / DeepSeek 等 |
| **TTS** | Edge TTS (云端) | 微软 TTS，零本地资源 |
| **Vision** | mlx-vlm | 本地视觉理解，默认 Qwen2.5-VL-3B-Instruct-4bit |

### Dashboard 面板
- **独立常驻服务** — `serve.py` 单独启动，通过面板按钮控制 Bandy 生命周期
- **模型管理** — 扫描 HuggingFace 缓存自动发现已下载模型，一键切换
- **中/英双语** — 界面语言切换，中文界面自动过滤仅支持英文的模型
- **系统提示词编辑** — LLM 和 Agent 的系统提示词可在面板上直接编辑（中/英独立）
- **运行时环境注入** — 自动收集时间、城市、天气、硬件、模型配置注入 LLM 系统提示词
- **会话记录** — 实时显示对话历史，含 STT/LLM/TTS 性能指标
- **状态持久化** — 模型选择、提示词通过 `config.yaml` + `dashboard_state.json` 持久化

### 摄像头控制 (Insta360 Link)
- AI 追踪开/关、点头、云台（上下左右）、变焦、隐私模式
- 桌面模式 / 白板模式 / 俯视模式切换

### 其他能力
- **天气查询** — 基于 wttr.in + macOS 系统定位，自动识别城市
- **视觉识别** — "看看这是什么" 触发摄像头拍照 + 本地 VLM 理解
- **OpenClaw Agent** — "龙虾" 唤醒词触发复杂任务，后台异步执行
- **Telegram Bot** — 语音消息转文字、文件发送、消息推送

## 安装

```bash
pip install -r requirements.txt
brew install imagesnap  # 摄像头抓帧
```

## 配置

```bash
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入 API 密钥和模型配置
```

关键配置项:
- `api.url` / `api.key` / `api.model` — 云端 LLM API
- `local_llm.repo` — 本地 LLM 模型 (HuggingFace repo)
- `vision.model` — 本地视觉模型
- `dashboard.port` — 面板端口 (默认 8765)
- `whisper.model` — Faster Whisper 模型大小

## 运行

**推荐: 面板模式 (独立常驻)**
```bash
python serve.py
# 浏览器打开 http://localhost:8765
# 点击 "启动 Bandy" 按钮
```

**直连模式**
```bash
python main.py
```

## 目录结构

```
├── serve.py              # 面板入口 (推荐)
├── main.py               # 直连入口
├── config.yaml           # 用户配置 (不入库)
├── config.yaml.example   # 配置模板
├── requirements.txt      # Python 依赖
├── bandy/
│   ├── assistant.py      # VoiceAssistant 主类: 录音、VAD、主循环
│   ├── commands.py       # 指令路由: 唤醒/退出/摄像头/天气/视觉/LLM
│   ├── config.py         # 配置加载 (config.yaml → Python 对象)
│   ├── dashboard.py      # Web 面板: 模型管理、会话记录、系统提示词编辑
│   ├── models.py         # 模型发现: HF 缓存扫描、分类、元数据、持久化
│   ├── llm.py            # LLM 调用: 流式/非流式 + 环境上下文注入
│   ├── stt.py            # 语音识别: Faster Whisper 加载与推理
│   ├── tts.py            # 语音合成: Edge TTS 合成 + afplay 播放
│   ├── vision.py         # 视觉识别: mlx-vlm 本地推理
│   ├── wake.py           # 唤醒词: 精确匹配 + 模糊拼音匹配
│   ├── weather.py        # 天气: wttr.in + macOS 系统定位
│   ├── camera.py         # 摄像头: Insta360 Link HTTP API
│   ├── agent.py          # OpenClaw Agent: 复杂任务异步执行
│   ├── telegram.py       # Telegram: Bot API 文件/消息发送
│   ├── tg_bot.py         # Telegram Bot: 长轮询接收消息
│   ├── metrics.py        # 性能指标: STT/LLM/TTS/Vision 统计
│   ├── utils.py          # 工具: 语言检测、Markdown 清理、繁简转换
│   └── output.py         # 输出管理: 按日期归档、旧文件清理
└── output/               # 生成文件 (按日期子目录)
```

## 唤醒词

| 唤醒词 | 作用 |
|--------|------|
| **Bandy** / **班迪** | 唤醒助手，进入对话模式 |
| **退下** | 结束对话，关闭摄像头 |
| **龙虾** | 触发 OpenClaw Agent 执行复杂任务 |

## 版本历史

### v0.8.0 (2026-03-30)
- 独立常驻 Dashboard 面板，Start/Stop 控制 Bandy 生命周期
- 模型管理系统: HF 缓存自动扫描、一键切换、中英文双语界面
- 中文界面过滤仅支持英文的模型候选
- 系统提示词编辑器 (LLM / Agent，中英独立)
- 运行时环境上下文自动注入 (时间、城市、天气、硬件、模型配置)
- 本地视觉模型 (mlx-vlm) 预加载与按需推理
- 唤醒词模糊匹配优化，防止 "and" 等短词误触发
- 启动语音播报 "语音助手已就绪"
- 会话管理完善: 唤醒→退出为独立会话，对话中不重复触发唤醒
- 端口管理: 重启时强制释放配置端口，避免冲突
- 状态持久化: config.yaml + dashboard_state.json

### v0.7.0
- 全双工语音交互基础架构
- Insta360 Link 摄像头控制
- 天气查询、Telegram 集成、OpenClaw Agent

## License

MIT
