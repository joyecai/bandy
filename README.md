# Bandy - 全双工语音助手

基于 macOS 的本地语音助手，支持摄像头控制、视觉识别、天气查询、Telegram 集成和 OpenClaw Agent 任务。

## 功能

- **全双工语音交互** - 实时录音、VAD、Whisper 识别、流式 TTS 播放
- **Insta360 Link 摄像头控制** - AI 追踪、点头、云台控制、模式切换
- **本地视觉识别** - Ollama + MiniCPM-V 实时图像理解
- **天气查询** - 基于 wttr.in，自动检测 macOS 系统定位
- **Telegram 集成** - 自动发送文件和消息
- **OpenClaw Agent** - 复杂任务后台异步执行

## 安装

```bash
pip install -r requirements.txt
brew install imagesnap
```

## 配置

复制配置模板并填入你的 API 密钥:

```bash
cp config.yaml.example config.yaml
```

## 运行

```bash
python main.py
```

## 目录结构

```
├── config.yaml          # 配置文件 (不入库)
├── config.yaml.example  # 配置模板
├── main.py              # 入口
├── requirements.txt     # 依赖
├── bandy/               # 核心包
│   ├── assistant.py     # 主类 (录音、VAD、主循环)
│   ├── config.py        # 配置加载
│   ├── stt.py           # Whisper 语音识别
│   ├── tts.py           # Edge TTS 合成与播放
│   ├── llm.py           # LLM API 调用
│   ├── vision.py        # 视觉识别
│   ├── weather.py       # 天气查询
│   ├── camera.py        # 摄像头控制
│   ├── telegram.py      # Telegram Bot
│   ├── agent.py         # OpenClaw Agent
│   ├── commands.py      # 指令路由
│   ├── wake.py          # 唤醒词检测
│   ├── utils.py         # 文本工具
│   └── output.py        # 输出文件管理
└── output/              # 生成文件 (按日期子目录)
```

## 唤醒词

说 **"Bandy"** 唤醒助手进入对话模式，说 **"退下"** 关闭摄像头。
