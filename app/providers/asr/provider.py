"""SpeechToTextProvider protocol + Mock and FunASR(OpenAI-compatible server) implementations.

The FunASR provider talks to a self-hosted FunASR runtime exposing
/v1/audio/transcriptions (deployed via backend/infra/asr). Business code never
imports funasr directly.
"""
from typing import BinaryIO, Protocol

import httpx

from app.core.config import settings


class SpeechToTextProvider(Protocol):
    name: str

    def transcribe(self, audio: BinaryIO, language: str = "zh") -> dict:
        """Blocking full-audio transcription -> {segments: [{start_ms,end_ms,text,confidence}]}."""
        ...

    def transcribe_stream_chunk(self, session_id: str, chunk: bytes, seq: int) -> dict:
        """Streaming partial/final for one chunk -> {text, is_final, confidence}."""
        ...

    def health(self) -> bool: ...


class MockASRProvider:
    """Deterministic mock: emits a fixed classroom transcript per session.

    Used in CI, tests and offline development. Chunk sequence N returns a
    partial on N%2==0 and a final on N%2==1, mimicking real ASR behavior.
    """

    name = "mock"

    _LINES = [
        "同学们，今天我们来复习椭圆的标准方程。",
        "首先看焦点在 x 轴上的情形，a 平方等于 b 平方加 c 平方。",
        "注意这里有一个常见错误，把 a 和 c 的位置弄反了。",
        "接下来我们看一道例题，已知离心率求标准方程。",
        "好，这道题的关键是联立方程，然后使用韦达定理。",
        "最后布置作业，课本 62 页第 3 题和第 7 题。",
    ]

    def transcribe(self, audio: BinaryIO, language: str = "zh") -> dict:
        start = 0
        segments = []
        for _i, line in enumerate(self._LINES):
            dur = 8000
            segments.append({"start_ms": start, "end_ms": start + dur, "text": line, "confidence": 0.93})
            start += dur
        return {"segments": segments, "model": "mock-asr"}

    def transcribe_stream_chunk(self, session_id: str, chunk: bytes, seq: int) -> dict:
        line = self._LINES[seq % len(self._LINES)]
        if seq % 2 == 0:
            return {"text": line[: max(6, int(len(line) * 0.5))], "is_final": False, "confidence": 0.6}
        return {"text": line, "is_final": True, "confidence": 0.94}

    def health(self) -> bool:
        return True


class FunASRProvider:
    """Client for the self-hosted FunASR OpenAI-compatible runtime.

    Streaming is approximated with chunked full-audio calls until the runtime's
    websocket streaming endpoint is wired (see docs/adr/ADR-005-ASR.md).
    """

    name = "funasr"

    def __init__(self) -> None:
        self.base_url = settings.ASR_BASE_URL.rstrip("/")
        self.model = settings.ASR_MODEL

    def _headers(self) -> dict:
        if settings.ASR_API_KEY:
            return {"Authorization": f"Bearer {settings.ASR_API_KEY}"}
        return {}

    def transcribe(self, audio: BinaryIO, language: str = "zh") -> dict:
        files = {"file": ("audio.webm", audio.read())}
        resp = httpx.post(
            f"{self.base_url}/v1/audio/transcriptions",
            headers=self._headers(),
            files=files,
            data={"model": self.model, "language": language},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"segments": data.get("segments", []), "model": self.model}

    def transcribe_stream_chunk(self, session_id: str, chunk: bytes, seq: int) -> dict:
        if not chunk:
            return {"text": "", "is_final": False, "confidence": None}  # 空分片不消耗识别额度
        resp = httpx.post(
            f"{self.base_url}/v1/audio/transcriptions",
            headers=self._headers(),
            files={"file": (f"chunk_{seq}.webm", chunk)},
            data={"model": self.model},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"text": data.get("text", ""), "is_final": True, "confidence": data.get("confidence", 0.9)}

    def health(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False


class OpenAICompatibleASRProvider:
    """任意 OpenAI 兼容云识别（硅基流动 SenseVoice / Groq Whisper / vLLM 网关等）。

    云 API 按(请求|时长)计费/限额，因此：
      - 实时区不做逐秒请求（transcribe_stream_chunk 返回 no-op），
      - 真实转写走 finalize 的完整音频单次调用（前端在结束后上传完整录音）。
    配置：ASR_BASE_URL（如 https://api.siliconflow.cn/v1）、ASR_API_KEY、ASR_MODEL
    （如 FunAudioLLM/SenseVoiceSmall）。
    """

    name = "openai_compatible"

    def __init__(self) -> None:
        self.base_url = settings.ASR_BASE_URL.rstrip("/")
        self.model = settings.ASR_MODEL
        self.api_key = settings.ASR_API_KEY

    def transcribe(self, audio: BinaryIO, language: str = "zh") -> dict:
        resp = httpx.post(
            f"{self.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": ("audio.webm", audio.read())},
            data={"model": self.model},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("text", "")
        return {
            "segments": [{"start_ms": 0, "end_ms": None, "text": text, "confidence": None}],
            "model": self.model,
        }

    def transcribe_stream_chunk(self, session_id: str, chunk: bytes, seq: int) -> dict:
        # 云识别不做逐秒请求（额度/限流原因）；实时区留空，转写在 finalize 完成
        return {"text": "", "is_final": False, "confidence": None}

    def health(self) -> bool:
        return True  # 云端可用性不作为本地 readiness 依据


_asr: SpeechToTextProvider | None = None


def get_asr_provider() -> SpeechToTextProvider:
    global _asr
    if _asr is None:
        if settings.ASR_PROVIDER == "funasr":
            _asr = FunASRProvider()
        elif settings.ASR_PROVIDER == "openai_compatible":
            _asr = OpenAICompatibleASRProvider()
        else:
            _asr = MockASRProvider()
    return _asr
