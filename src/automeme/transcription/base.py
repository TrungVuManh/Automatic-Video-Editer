"""Interface cho mọi backend nhận dạng giọng nói (SPEC §13).

Backend chỉ cần trả về dict "thô" theo đúng dạng dưới đây; việc chuẩn hóa do
`normalize.py` làm, nên thay backend không ảnh hưởng các bước sau:

    {
      "language": "vi",
      "duration": 47.83,          # hoặc None nếu backend không biết
      "segments": [
        {"start": 0.42, "end": 3.21, "text": " Hôm nay…",
         "words": [{"w": "Hôm", "start": 0.42, "end": 0.6}, ...]}
      ]
    }
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio: Path) -> dict[str, Any]:
        """Nhận dạng một file audio (WAV mono 16 kHz) → dict thô như mô tả ở đầu module."""

    def unload(self) -> None:
        """Giải phóng model khỏi VRAM. Backend nào không giữ model thì không phải làm gì."""
        return None
