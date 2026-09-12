"""Nạp và điền prompt từ file, không hard-code prompt trong code."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import ContextWindow

CONTEXT_TOKEN = "{{CONTEXT_JSON}}"
SCHEMA_TOKEN = "{{SCHEMA_JSON}}"


def load_prompt(path: Path) -> str:
    try:
        template = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Không thấy prompt: {path}") from None
    if CONTEXT_TOKEN not in template or SCHEMA_TOKEN not in template:
        raise ValueError(
            f"Prompt {path} phải có hai chỗ giữ chỗ {CONTEXT_TOKEN} và {SCHEMA_TOKEN}."
        )
    return template


def render_prompt(template: str, context: ContextWindow, schema: dict[str, Any]) -> str:
    """Điền JSON giữ nguyên tiếng Việt; replace tránh xung đột dấu ngoặc của JSON Schema."""
    context_json = json.dumps(context.as_dict(), ensure_ascii=False, indent=2)
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    return template.replace(CONTEXT_TOKEN, context_json).replace(SCHEMA_TOKEN, schema_json)
