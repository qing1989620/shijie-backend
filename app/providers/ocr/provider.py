"""OCRProvider + Mock implementation.

Real deployment: PaddleOCR / Pix2Text runtime served over HTTP (same provider
pattern as ASR). The mock extracts plain text the user typed as the OCR body so
the upload->preview->confirm flow is fully testable without the model runtime.
"""
from typing import BinaryIO, Protocol

from app.core.config import settings


class OCRProvider(Protocol):
    name: str

    def recognize(self, file: BinaryIO, mime: str, display_name: str = "") -> dict:
        """Returns {text, blocks: [{type, content}], needs_review: bool}."""
        ...


class MockOCRProvider:
    name = "mock"

    def recognize(self, file: BinaryIO, mime: str, display_name: str = "") -> dict:
        raw = file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = (
                "（图片/PDF 内容需接入 PaddleOCR 运行时后自动识别。"
                "当前为 Development Mock 模式，请在预览中手动录入题目内容后确认。）"
            )
        blocks = [{"type": "text", "content": p.strip()} for p in text.split("\n\n") if p.strip()]
        return {
            "text": text,
            "blocks": blocks,
            "needs_review": True,
            "notice": "Mock OCR：请人工校对识别结果。复杂数学公式识别不稳定时必须校对。",
        }


class PaddleOCRProvider:
    """HTTP client for a PaddleOCR sidecar (POST /ocr, multipart file)."""

    name = "paddleocr"

    def __init__(self) -> None:
        self.base_url = settings.ASR_BASE_URL  # same sidecar host convention; override via env when deployed

    def recognize(self, file: BinaryIO, mime: str, display_name: str = "") -> dict:
        import httpx

        resp = httpx.post(
            f"{self.base_url.rstrip('/')}/ocr",
            files={"file": (display_name or "upload", file.read())},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


_ocr: OCRProvider | None = None


def get_ocr_provider() -> OCRProvider:
    global _ocr
    if _ocr is None:
        if settings.OCR_PROVIDER == "paddleocr":
            _ocr = PaddleOCRProvider()
        else:
            _ocr = MockOCRProvider()
    return _ocr
