"""Adapter mỏng cho Ollama và Claude; import SDK bên trong lúc dùng."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import StructuredLLM


class OllamaLLM(StructuredLLM):
    def __init__(self, host: str, model: str, *, client_factory: Callable[..., Any] | None = None):
        self.host = host
        self.model = model
        self._client_factory = client_factory

    def complete(self, prompt: str, schema: dict[str, Any]) -> str:
        try:
            if self._client_factory is None:
                from ollama import Client
                factory = Client
            else:
                factory = self._client_factory
            client = factory(host=self.host)
            response = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format=schema,
                options={"temperature": 0},
                think=False,
            )
            message = response.message if hasattr(response, "message") else response["message"]
            content = message.content if hasattr(message, "content") else message["content"]
            if not content:
                raise RuntimeError("Ollama trả về nội dung rỗng.")
            return str(content)
        except ImportError:
            raise RuntimeError(
                'Chưa cài SDK Ollama. Chạy: python -m pip install -e ".[llm]"'
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Không gọi được Ollama tại {self.host} với model {self.model}. "
                f"Hãy mở ứng dụng Ollama và kiểm tra `ollama list`. Chi tiết: {e}"
            ) from e


class ClaudeLLM(StructuredLLM):
    def __init__(self, model: str, *, client_factory: Callable[..., Any] | None = None,
                 max_tokens: int = 1024):
        self.model = model
        self.max_tokens = max_tokens
        self._client_factory = client_factory

    def complete(self, prompt: str, schema: dict[str, Any]) -> str:
        try:
            if self._client_factory is None:
                from anthropic import Anthropic, transform_schema
                factory = Anthropic
                output_schema = transform_schema(schema)
            else:
                factory = self._client_factory
                output_schema = schema
            client = factory()
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": output_schema}},
            )
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    return str(block.text)
            raise RuntimeError("Claude không trả về nội dung JSON.")
        except ImportError:
            raise RuntimeError(
                'Chưa cài Anthropic SDK. Chạy: python -m pip install -e ".[claude]"'
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Không gọi được Claude model {self.model}: {e}") from e


def create_llm(settings: Any) -> StructuredLLM:
    if settings.llm.backend == "ollama":
        return OllamaLLM(settings.ollama.host, settings.ollama.model)
    if settings.llm.backend == "claude":
        return ClaudeLLM(settings.claude.model, max_tokens=settings.analyzer.max_tokens)
    raise ValueError(f"Backend LLM không hỗ trợ: {settings.llm.backend}")
