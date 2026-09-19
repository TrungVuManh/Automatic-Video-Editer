"""Interface LLM có structured output, không khóa pipeline vào một nhà cung cấp."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMRefusal(RuntimeError):
    """LLM từ chối trả lời một đoạn (ví dụ bộ lọc an toàn) — bỏ riêng đoạn đó, chạy tiếp."""


class StructuredLLM(ABC):
    """Backend nhận prompt + JSON Schema và trả về chuỗi JSON."""

    model: str

    @abstractmethod
    def complete(self, prompt: str, schema: dict[str, Any]) -> str:
        """Sinh một câu trả lời JSON tuân theo `schema`."""
