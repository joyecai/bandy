"""VoiceAssistant 主类: 录音线程、VAD、主循环"""
import os
import time
import asyncio
import signal
import threading
import queue

import numpy as np

from .config import cfg
from . import stt as stt_mod
from . import tts as tts_mod
from .camera import disable_ai_tracking, camera_quit
from .commands import process_command
from .metrics import store


class VoiceAssistant:
    def __init__(self):
        self.running = False
        self.whisper_model = None
        self._pa = None
        self._filter_b = self._filter_a = None
        self._noise_rms = 0.0

        self.conversation_mode = False
        self.ai_tracking_active = False
        self.last_command_time = 0
        self._session_start = 0.0

        self._aio_session = None
        self._speech_queue = queue.Queue(maxsize=5)
        self._playback_proc = None
        self._audio_stream = None
        self._is_speaking = False
        self._speak_end_time = 0.0
        self._barge_in = False

        self._history = []
        self._tts_cache = {}
        self._task_history = []
        self._speak_lock = None
        self._announce_queue = None
        self._tg_sent_files = set()
        self._vision_frame = None
        self._vision_time = 0.0
        self._vision_history = []
        self._bg_tasks = set()
        self._child_procs = set()
        self._llm_server_proc = None

    # -- 历史管理 --

    def _record(self, role, text, **metric_kwargs):
        self._history.append({"ts": time.time(), "role": role, "text": text})
        if len(self._history) > cfg.HISTORY_MAX:
            self._history = self._history[-cfg.HISTORY_MAX:]
        store.add_turn(role, text, **metric_kwargs)

    def _recent_history(self, max_age=None, limit=20):
        cutoff = self._session_start if self._session_start > 0 else time.time() - (max_age or cfg.CONVERSATION_TTL)
        return [h for h in self._history if h["ts"] >= cutoff][-limit:]

    # -- 初始化 --

    async def load_all(self):
        import pyaudio
        from scipy.signal import butter

        if cfg.LOCAL_LLM_REPO:
            self._start_local_llm()
        if not self.whisper_model:
            self.whisper_model = stt_mod.load_whisper()
        if not self._pa:
            self._pa = pyaudio.PyAudio()
        self._filter_b, self._filter_a = butter(2, 80 / (cfg.SAMPLE_RATE / 2), 'highpass')
        self._calibrate_noise()
        await tts_mod.warm_tts(self._tts_cache)
        stt_mod.warm_whisper(self.whisper_model)
        if cfg.VISION_ENABLED:
            from . import vision as vision_mod
            vision_mod.preload(blocking=True)
        else:
            print("👁️ 摄像头/视觉已关闭，跳过模型加载", flush=True)
        from .llm import warmup_context
        warmup_context()
        if cfg.LOCAL_LLM_REPO:
            self._warm_local_llm()
        print("✅ 已就绪\n", flush=True)

    def _start_local_llm(self):
        import subprocess
        port = cfg.LOCAL_LLM_PORT
        host = cfg.LOCAL_LLM_HOST
        repo = cfg.LOCAL_LLM_REPO
        short = repo.split('/')[-1]
        print(f"🧠 加载本地 LLM ({short})...", flush=True)
        try:
            out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True).strip()
            for pid in out.split():
                pid = pid.strip()
                if pid and pid != str(os.getpid()):
                    os.kill(int(pid), 9)
        except (subprocess.CalledProcessError, OSError):
            pass
        self._llm_server_proc = subprocess.Popen(
            ["/opt/homebrew/Cellar/python@3.11/3.11.15/bin/python3.11",
             "-m", "mlx_lm.server",
             "--model", repo,
             "--host", host,
             "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import urllib.request
        url = f"http://{host}:{port}/v1/models"
        for i in range(60):
            try:
                urllib.request.urlopen(url, timeout=1)
                print(f"   本地 LLM 服务已就绪 (端口 {port})", flush=True)
                return
            except Exception:
                time.sleep(1)
        print(f"⚠️ 本地 LLM 服务启动超时", flush=True)

    def _warm_local_llm(self):
        import urllib.request, json
        print("🔥 预热本地 LLM...", flush=True)
        url = f"{cfg.LOCAL_LLM_URL}/chat/completions"
        body = json.dumps({
            "model": cfg.LOCAL_LLM_REPO,
            "messages": [
                {"role": "system", "content": "你是语音助手"},
                {"role": "user", "content": "你好"}
            ],
            "max_tokens": 32,
            "chat_template_kwargs": {"enable_thinking": False}
        }).encode()
        req = urllib.request.Request(url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {cfg.LOCAL_LLM_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            print("   本地 LLM 预热完成", flush=True)
        except Exception as e:
            print(f"⚠️ 本地 LLM 预热失败: {e}", flush=True)

    def _calibrate_noise(self):
        import pyaudio
        print("🔇 校准环境噪声...", flush=True)
        stream = self._pa.open(
            format=pyaudio.paInt16, channels=cfg.CHANNELS, rate=cfg.SAMPLE_RATE,
            input=True, frames_per_buffer=cfg.CHUNK, input_device_index=cfg.INPUT_DEVICE_IDX)
        rms_vals = []
        for _ in range(int(cfg.SAMPLE_RATE / cfg.CHUNK * cfg.NOISE_CAL_SEC)):
            data = stream.read(cfg.CHUNK, exception_on_overflow=False)
            rms_vals.append(np.sqrt(np.mean(np.frombuffer(data, np.int16).astype(np.float32) ** 2)))
        stream.stop_stream()
        stream.close()
        avg = np.mean(rms_vals)
        self._noise_rms = avg * 3.0 + 80
        print(f"   噪声 RMS={avg:.0f}, 阈值={self._noise_rms:.0f}", flush=True)

    # -- 录音线程 --

    def _reset_vad(self, state):
        state["frames"].clear()
        state["started"] = False
        state["silence"] = 0
        state["speech_chunks"] = 0
        state["total_chunks"] = 0

    def _capture_loop(self):
        import pyaudio
        from scipy.signal import filtfilt

        stream = self._pa.open(
            format=pyaudio.paInt16, channels=cfg.CHANNELS, rate=cfg.SAMPLE_RATE,
            input=True, frames_per_buffer=cfg.CHUNK, input_device_index=cfg.INPUT_DEVICE_IDX)
        self._audio_stream = stream
        thr = self._noise_rms
        sil_limit = int(cfg.SAMPLE_RATE / cfg.CHUNK * cfg.SILENCE_AFTER)
        pre_n = int(cfg.SAMPLE_RATE / cfg.CHUNK * cfg.PRE_SPEECH_BUF)
        min_sp = int(cfg.SAMPLE_RATE / cfg.CHUNK * cfg.MIN_SPEECH_DUR)
        max_ch = int(cfg.SAMPLE_RATE / cfg.CHUNK * cfg.MAX_RECORD_SEC)
        barge_thr = max(thr * 10.0, 1000)
        barge_need = 9

        ring = []
        s = {"frames": [], "started": False, "silence": 0, "speech_chunks": 0, "total_chunks": 0}
        barge_cnt = 0

        while self.running:
            try:
                data = stream.read(cfg.CHUNK, exception_on_overflow=False)
            except Exception:
                time.sleep(0.01)
                continue

            audio = np.frombuffer(data, np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(audio ** 2))

            if self._is_speaking:
                if rms > barge_thr:
                    barge_cnt += 1
                    if barge_cnt >= barge_need and self._playback_proc:
                        try:
                            self._playback_proc.terminate()
                        except Exception:
                            pass
                        self._barge_in = True
                        self._is_speaking = False
                        self._speak_end_time = time.time() - cfg.SPEAK_COOLDOWN + 0.2
                        barge_cnt = 0
                        print("🔇 用户打断播放", flush=True)
                        # short 200ms cooldown then resume VAD
                    else:
                        continue
                else:
                    barge_cnt = 0
                    continue

            if (time.time() - self._speak_end_time) < cfg.SPEAK_COOLDOWN:
                if s["started"]:
                    self._reset_vad(s)
                ring.clear()
                continue

            if not s["started"]:
                ring.append(data)
                if len(ring) > pre_n:
                    ring.pop(0)
                if rms > thr:
                    s["started"] = True
                    s["frames"] = list(ring)
                    ring.clear()
                    s["silence"] = 0
                    s["speech_chunks"] = 1
                    s["total_chunks"] = len(s["frames"])
            else:
                s["frames"].append(data)
                s["total_chunks"] += 1
                if rms > thr:
                    s["speech_chunks"] += 1
                    s["silence"] = 0
                else:
                    s["silence"] += 1

                if s["silence"] >= sil_limit or s["total_chunks"] >= max_ch:
                    if s["speech_chunks"] >= min_sp:
                        raw = np.frombuffer(b''.join(s["frames"]), np.int16).astype(np.float32)
                        filtered = filtfilt(self._filter_b, self._filter_a, raw)
                        norm = np.clip(filtered / 32768.0, -1.0, 1.0).astype(np.float32)
                        if self._speech_queue.full():
                            try:
                                self._speech_queue.get_nowait()
                            except queue.Empty:
                                pass
                        self._speech_queue.put(norm)
                    self._reset_vad(s)

        try:
            stream.stop_stream()
        except OSError:
            pass
        try:
            stream.close()
        except OSError:
            pass

    # -- TTS --

    def _kill_playback(self):
        """立即终止当前 TTS 播放"""
        proc = self._playback_proc
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        self._playback_proc = None
        self._is_speaking = False
        self._barge_in = False

    async def speak(self, text):
        text = text.strip()
        if not text:
            return
        async with self._speak_lock:
            try:
                cached = text in self._tts_cache
                if cached:
                    path = self._tts_cache[text]
                else:
                    path = await tts_mod.synthesize(text)
                await tts_mod.play(path, self)
                # flush echo: discard mic audio captured during TTS playback
                while not self._speech_queue.empty():
                    try:
                        self._speech_queue.get_nowait()
                    except queue.Empty:
                        break
                if self._barge_in:
                    self._barge_in = False
                if not cached:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            except Exception as e:
                self._is_speaking = False
                print(f"⚠️ TTS 错误: {e}", flush=True)

    # -- aiohttp session --

    async def _get_session(self):
        if self._aio_session is None or self._aio_session.closed:
            import aiohttp
            self._aio_session = aiohttp.ClientSession()
        return self._aio_session

    # -- 播报队列 --

    def _announce(self, text):
        if self._announce_queue and text:
            self._announce_queue.put_nowait(text)

    async def _drain_announces(self):
        while self._announce_queue and not self._announce_queue.empty():
            try:
                text = self._announce_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._record("assistant", text)
            print(f"📢 播报: {text}", flush=True)
            await self.speak(text)

    # -- 对话管理 --

    def _check_timeout(self):
        if self.conversation_mode and (time.time() - self.last_command_time) > cfg.CONVERSATION_TTL:
            print(f"⏰ {cfg.CONVERSATION_TTL}秒无指令，退出对话", flush=True)
            self._end_conversation()

    def _end_conversation(self):
        self.conversation_mode = False
        store.end_session()
        if self.ai_tracking_active:
            self.ai_tracking_active = False
            if cfg.VISION_ENABLED:
                asyncio.create_task(asyncio.to_thread(disable_ai_tracking))
            print("📷 AI追踪已关闭", flush=True)

    def _dismiss_bg(self):
        if cfg.VISION_ENABLED:
            camera_quit()
            print("📷 摄像头和软件已关闭", flush=True)

    async def _start_tracking(self):
        try:
            from .camera import enable_ai_tracking
            await asyncio.to_thread(enable_ai_tracking)
            print("📷 AI追踪已开启", flush=True)
        except Exception:
            self.ai_tracking_active = False

    async def _reply(self, text):
        self._record("assistant", text)
        print(f"🤖 回复: {text}", flush=True)
        await self.speak(text)

    # -- 清理 & 退出 --

    def _shutdown(self):
        self.running = False
        if self._llm_server_proc:
            try:
                self._llm_server_proc.terminate()
                self._llm_server_proc.wait(timeout=5)
            except Exception:
                try:
                    self._llm_server_proc.kill()
                except Exception:
                    pass
            self._llm_server_proc = None
        for proc in list(self._child_procs):
            try:
                proc.kill()
            except Exception:
                pass
        self._child_procs.clear()
        if self._playback_proc:
            try:
                self._playback_proc.kill()
            except Exception:
                pass
            self._playback_proc = None
        for task in list(self._bg_tasks):
            try:
                task.cancel()
            except Exception:
                pass
        self._bg_tasks.clear()
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        for p in self._tts_cache.values():
            try:
                os.remove(p)
            except OSError:
                pass
        self._tts_cache.clear()

    # -- 主循环 --

    async def run(self):
        self._speak_lock = asyncio.Lock()
        self._announce_queue = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._shutdown)
        except (ValueError, RuntimeError):
            pass

        await self.load_all()

        if cfg.LLM_PROVIDER == "local" and cfg.LOCAL_LLM_REPO:
            short = cfg.LOCAL_LLM_REPO.split('/')[-1]
            store.set_model_info("llm", short, f"local:{cfg.LOCAL_LLM_PORT}")
        else:
            store.set_model_info("llm", cfg.API_MODEL, cfg.API_URL.split("//")[-1].split("/")[0])

        self._dashboard_runner = None
        if cfg.DASHBOARD_ENABLED:
            import socket, logging
            _log = logging.getLogger(__name__)
            port = cfg.DASHBOARD_PORT
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
                if _s.connect_ex(("127.0.0.1", port)) == 0:
                    _log.info("Dashboard 已在端口 %d 运行 (独立进程), 跳过内置启动", port)
                else:
                    from .dashboard import start_dashboard
                    self._dashboard_runner = await start_dashboard(port)

        self._tg_bot_task = None
        if cfg.TG_BOT_TOKEN and cfg.TG_BOT_ENABLED:
            from .tg_bot import run_tg_bot
            self._tg_bot_task = asyncio.create_task(run_tg_bot(self))

        print("=" * 50)
        print("🎙️ 语音助手已就绪 (全双工)")
        print("   说 'Bandy' 唤醒 | 说话可打断播放")
        print("=" * 50, flush=True)

        from .llm import get_ui_lang
        _ready_text = "Voice assistant is ready" if get_ui_lang() == "en" else "语音助手已就绪"
        await self.speak(_ready_text)

        threading.Thread(target=self._capture_loop, daemon=True).start()

        _metrics_tick = 0

        try:
            while self.running:
                try:
                    try:
                        audio = await asyncio.to_thread(self._speech_queue.get, True, 1.0)
                    except queue.Empty:
                        await self._drain_announces()
                        self._check_timeout()
                        _metrics_tick += 1
                        if _metrics_tick >= 3:
                            _metrics_tick = 0
                            store.check_clear_flag()
                            store.dump_to_file()
                        continue

                    text = await asyncio.to_thread(stt_mod.recognize, self.whisper_model, audio)
                    if text:
                        await process_command(self, text)
                        store.dump_to_file()

                    await self._drain_announces()
                    self._check_timeout()
                except Exception as e:
                    if not self.running:
                        break
                    print(f"❌ 错误: {e}", flush=True)
                    await asyncio.sleep(0.5)
        finally:
            if self._tg_bot_task and not self._tg_bot_task.done():
                self._tg_bot_task.cancel()
                try:
                    await self._tg_bot_task
                except (asyncio.CancelledError, Exception):
                    pass
            if self._dashboard_runner:
                await self._dashboard_runner.cleanup()
            if self._aio_session and not self._aio_session.closed:
                await self._aio_session.close()
            self._shutdown()
            print("\n🛑 语音助手已退出", flush=True)

    def start(self):
        self.running = True
        try:
            asyncio.run(self.run())
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()
