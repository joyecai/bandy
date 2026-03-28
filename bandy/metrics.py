"""指标采集: 记录对话会话、各模型吞吐速度"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SttMetric:
    audio_duration: float = 0.0
    process_time: float = 0.0
    text: str = ""
    timestamp: float = 0.0

    @property
    def speed_ratio(self):
        if self.process_time > 0:
            return self.audio_duration / self.process_time
        return 0.0


@dataclass
class LlmMetric:
    prompt: str = ""
    reply: str = ""
    tokens: int = 0
    time_to_first_token: float = 0.0
    total_time: float = 0.0
    timestamp: float = 0.0

    @property
    def tokens_per_sec(self):
        if self.total_time > 0:
            return self.tokens / self.total_time
        return 0.0


@dataclass
class TtsMetric:
    text: str = ""
    char_count: int = 0
    synth_time: float = 0.0
    timestamp: float = 0.0

    @property
    def chars_per_sec(self):
        if self.synth_time > 0:
            return self.char_count / self.synth_time
        return 0.0


@dataclass
class VisionMetric:
    prompt: str = ""
    result: str = ""
    process_time: float = 0.0
    timestamp: float = 0.0


@dataclass
class Turn:
    """对话中的一次交互轮次"""
    role: str = ""
    text: str = ""
    timestamp: float = 0.0
    stt: Optional[SttMetric] = None
    llm: Optional[LlmMetric] = None
    tts: Optional[TtsMetric] = None
    vision: Optional[VisionMetric] = None


@dataclass
class Session:
    """一次唤醒后的对话会话"""
    session_id: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    turns: list = field(default_factory=list)
    active: bool = True


class MetricsStore:
    """全局指标存储 (线程安全)"""

    def __init__(self):
        self._lock = threading.Lock()
        self.sessions: list[Session] = []
        self._next_id = 1
        self._current_session: Optional[Session] = None
        self.start_time = time.time()

        self.stt_history: list[SttMetric] = []
        self.llm_history: list[LlmMetric] = []
        self.tts_history: list[TtsMetric] = []
        self.vision_history: list[VisionMetric] = []

        self.models = {
            "stt": {"name": "", "version": ""},
            "llm": {"name": "", "version": ""},
            "tts": {"name": "Edge TTS", "version": "XiaoxiaoNeural / AriaNeural"},
            "vision": {"name": "", "version": ""},
        }

    def set_model_info(self, category, name, version=""):
        with self._lock:
            self.models[category] = {"name": name, "version": version}

    def new_session(self) -> Session:
        with self._lock:
            if self._current_session and self._current_session.active:
                self._current_session.active = False
                self._current_session.end_time = time.time()
            s = Session(session_id=self._next_id, start_time=time.time())
            self._next_id += 1
            self._current_session = s
            self.sessions.append(s)
            if len(self.sessions) > 200:
                self.sessions = self.sessions[-200:]
            return s

    def end_session(self):
        with self._lock:
            if self._current_session and self._current_session.active:
                self._current_session.active = False
                self._current_session.end_time = time.time()
            self._current_session = None

    def add_turn(self, role, text, **kwargs):
        with self._lock:
            t = Turn(role=role, text=text, timestamp=time.time(), **kwargs)
            if self._current_session and self._current_session.active:
                self._current_session.turns.append(t)
            return t

    @property
    def current_session(self):
        return self._current_session

    def record_stt(self, m: SttMetric):
        with self._lock:
            m.timestamp = time.time()
            self.stt_history.append(m)
            if len(self.stt_history) > 500:
                self.stt_history = self.stt_history[-500:]

    def record_llm(self, m: LlmMetric):
        with self._lock:
            m.timestamp = time.time()
            self.llm_history.append(m)
            if len(self.llm_history) > 500:
                self.llm_history = self.llm_history[-500:]

    def record_tts(self, m: TtsMetric):
        with self._lock:
            m.timestamp = time.time()
            self.tts_history.append(m)
            if len(self.tts_history) > 500:
                self.tts_history = self.tts_history[-500:]

    def record_vision(self, m: VisionMetric):
        with self._lock:
            m.timestamp = time.time()
            self.vision_history.append(m)
            if len(self.vision_history) > 500:
                self.vision_history = self.vision_history[-500:]

    def snapshot(self):
        """返回当前指标快照 (用于 API)"""
        with self._lock:
            def _avg(lst, attr):
                vals = [getattr(m, attr) for m in lst[-20:] if getattr(m, attr, 0) > 0]
                return round(sum(vals) / len(vals), 2) if vals else 0

            return {
                "uptime": round(time.time() - self.start_time),
                "models": dict(self.models),
                "stats": {
                    "stt": {
                        "total_calls": len(self.stt_history),
                        "avg_speed_ratio": _avg(self.stt_history, "speed_ratio"),
                        "avg_process_time": _avg(self.stt_history, "process_time"),
                    },
                    "llm": {
                        "total_calls": len(self.llm_history),
                        "avg_tokens_per_sec": _avg(self.llm_history, "tokens_per_sec"),
                        "avg_ttft": _avg(self.llm_history, "time_to_first_token"),
                        "avg_total_time": _avg(self.llm_history, "total_time"),
                    },
                    "tts": {
                        "total_calls": len(self.tts_history),
                        "avg_chars_per_sec": _avg(self.tts_history, "chars_per_sec"),
                        "avg_synth_time": _avg(self.tts_history, "synth_time"),
                    },
                    "vision": {
                        "total_calls": len(self.vision_history),
                        "avg_process_time": _avg(self.vision_history, "process_time"),
                    },
                },
                "sessions": [self._session_dict(s) for s in self.sessions[-50:]],
                "recent_stt": [self._stt_dict(m) for m in self.stt_history[-10:]],
                "recent_llm": [self._llm_dict(m) for m in self.llm_history[-10:]],
                "recent_tts": [self._tts_dict(m) for m in self.tts_history[-10:]],
                "recent_vision": [self._vision_dict(m) for m in self.vision_history[-10:]],
            }

    @staticmethod
    def _session_dict(s: Session):
        return {
            "id": s.session_id,
            "start": s.start_time,
            "end": s.end_time,
            "active": s.active,
            "turns": [
                {
                    "role": t.role,
                    "text": t.text,
                    "ts": t.timestamp,
                    "stt_time": t.stt.process_time if t.stt else None,
                    "llm_tps": t.llm.tokens_per_sec if t.llm else None,
                    "llm_ttft": t.llm.time_to_first_token if t.llm else None,
                    "tts_time": t.tts.synth_time if t.tts else None,
                    "vision_time": t.vision.process_time if t.vision else None,
                }
                for t in s.turns
            ],
        }

    @staticmethod
    def _stt_dict(m: SttMetric):
        return {
            "text": m.text, "audio_dur": round(m.audio_duration, 2),
            "proc_time": round(m.process_time, 3),
            "speed_ratio": round(m.speed_ratio, 1), "ts": m.timestamp,
        }

    @staticmethod
    def _llm_dict(m: LlmMetric):
        return {
            "prompt": m.prompt[:80], "tokens": m.tokens,
            "tps": round(m.tokens_per_sec, 1),
            "ttft": round(m.time_to_first_token, 3),
            "total": round(m.total_time, 2), "ts": m.timestamp,
        }

    @staticmethod
    def _tts_dict(m: TtsMetric):
        return {
            "text": m.text[:40], "chars": m.char_count,
            "synth_time": round(m.synth_time, 3),
            "cps": round(m.chars_per_sec, 1), "ts": m.timestamp,
        }

    @staticmethod
    def _vision_dict(m: VisionMetric):
        return {
            "prompt": m.prompt[:40], "result": m.result[:60],
            "proc_time": round(m.process_time, 2), "ts": m.timestamp,
        }


store = MetricsStore()
