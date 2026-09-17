"""Cấu hình, ghép theo thứ tự (sau đè trước):

    configs/default.yaml  →  profile (--profile <tên>)  →  biến môi trường / .env  →  cờ CLI

- Tham số dựng video (cooldown, số meme/phút, ngưỡng…) nằm trong profile YAML.
- Tham số của máy (model, device, địa chỉ Ollama…) thường đặt trong .env.

`.env` dùng đúng tên biến của SPEC §14 (WHISPER_MODEL, MEME_COOLDOWN…). Các tên này không
theo một quy luật lồng nhau nào nên được ánh xạ bằng bảng ENV_MAP.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .utils.files import CONFIGS_DIR, ENV_FILE, PROJECT_ROOT, resolve_path


class ConfigError(ValueError):
    """Cấu hình sai: thiếu file, thiếu profile, sai kiểu, sai tên khóa."""


# ------------------------------------------------------------------ schema
class _Section(BaseModel):
    # Khóa lạ (gõ nhầm "cooldwon") báo lỗi thay vì bị lặng lẽ bỏ qua
    model_config = ConfigDict(extra="forbid")


class AppSettings(_Section):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]

    @field_validator("log_level", mode="before")
    @classmethod
    def _viet_hoa(cls, v: Any) -> Any:
        return v.upper() if isinstance(v, str) else v


class PathSettings(_Section):
    data_dir: Path
    assets_dir: Path


class WhisperSettings(_Section):
    model: str
    language: str
    device: Literal["cuda", "cpu", "auto"]
    compute_type: str
    beam_size: int = Field(ge=1)
    vad_filter: bool
    condition_on_previous_text: bool


class LLMSettings(_Section):
    backend: Literal["ollama", "claude"]


class OllamaSettings(_Section):
    host: str
    model: str


class ClaudeSettings(_Section):
    model: str


class AnalyzerSettings(_Section):
    previous_segments: int = Field(ge=0, le=10)
    next_segments: int = Field(ge=0, le=10)
    timing_delay: float = Field(ge=0, le=2.0)
    max_tokens: int = Field(ge=128, le=8192)


class MemeSearchSettings(_Section):
    base_url: str
    token: str
    top_k: int = Field(ge=1, le=20)
    max_download_mb: float = Field(gt=0, le=500)


class EditingSettings(_Section):
    max_memes_per_minute: float = Field(gt=0)
    cooldown: float = Field(ge=0)
    threshold: float = Field(ge=0, le=1)


class MemeSettings(_Section):
    library_file: Path
    duration_min: float = Field(ge=0.5, le=5.0)
    duration_max: float = Field(ge=0.5, le=5.0)
    scale_default: float = Field(ge=0.05, le=1.0)
    position_default: Literal["top-left", "top-right", "bottom-left", "bottom-right", "center"]
    margin_ratio: float = Field(ge=0, le=0.2)

    @model_validator(mode="after")
    def _min_khong_vuot_max(self) -> MemeSettings:
        if self.duration_min > self.duration_max:
            raise ValueError(f"duration_min ({self.duration_min}) lớn hơn "
                             f"duration_max ({self.duration_max})")
        return self


class SfxSettings(_Section):
    enabled: bool
    library_file: Path
    volume: float = Field(ge=0, le=1)
    score_threshold: float = Field(ge=0, le=1)
    cooldown: float = Field(ge=0)
    max_per_minute: float = Field(gt=0)
    duration_max: float = Field(gt=0, le=5)


class RankingSettings(_Section):
    semantic_weight: float = Field(ge=0, le=1)
    emotion_weight: float = Field(ge=0, le=1)
    style_weight: float = Field(ge=0, le=1)
    quality_weight: float = Field(ge=0, le=1)
    novelty_weight: float = Field(ge=0, le=1)
    duplicate_penalty: float = Field(ge=0, le=1)
    recent_window: float = Field(gt=0)

    @model_validator(mode="after")
    def _tong_trong_so_bang_mot(self) -> RankingSettings:
        total = (
            self.semantic_weight + self.emotion_weight + self.style_weight
            + self.quality_weight + self.novelty_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"tổng năm trọng số phải bằng 1.0 (đang là {total:g})")
        return self


class DownloadSettings(_Section):
    max_height: int = Field(ge=144, le=4320)
    max_duration: float = Field(gt=0)
    max_filesize_mb: int = Field(ge=1)
    js_runtime: Literal["auto", "deno", "node", "bun", "none"]
    clip_seconds: float = Field(gt=0)
    own_channels: list[str] = Field(default_factory=list)

    @field_validator("own_channels", mode="before")
    @classmethod
    def _tach_danh_sach(cls, v: Any) -> Any:
        # .env chỉ chứa chuỗi: "@kenh1, UCabc…" → ["@kenh1", "UCabc…"]
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v


class OutputSettings(_Section):
    video_codec: str
    audio_codec: str
    crf: int = Field(ge=0, le=51)
    preset: str


class Settings(_Section):
    app: AppSettings
    paths: PathSettings
    whisper: WhisperSettings
    llm: LLMSettings
    ollama: OllamaSettings
    claude: ClaudeSettings
    analyzer: AnalyzerSettings
    meme_search: MemeSearchSettings
    editing: EditingSettings
    meme: MemeSettings
    sfx: SfxSettings
    ranking: RankingSettings
    download: DownloadSettings
    output: OutputSettings


# Tên biến môi trường (SPEC §14) → (mục, khóa) trong cấu hình
ENV_MAP: dict[str, tuple[str, str]] = {
    "LOG_LEVEL": ("app", "log_level"),
    "WHISPER_MODEL": ("whisper", "model"),
    "WHISPER_LANGUAGE": ("whisper", "language"),
    "WHISPER_DEVICE": ("whisper", "device"),
    "WHISPER_COMPUTE_TYPE": ("whisper", "compute_type"),
    "WHISPER_BEAM_SIZE": ("whisper", "beam_size"),
    "WHISPER_VAD_FILTER": ("whisper", "vad_filter"),
    "WHISPER_CONDITION_ON_PREVIOUS_TEXT": ("whisper", "condition_on_previous_text"),
    "LLM_BACKEND": ("llm", "backend"),
    "OLLAMA_HOST": ("ollama", "host"),
    "OLLAMA_MODEL": ("ollama", "model"),
    "CLAUDE_MODEL": ("claude", "model"),
    "MEME_TIMING_DELAY": ("analyzer", "timing_delay"),
    "MEME_SEARCH_BASE_URL": ("meme_search", "base_url"),
    "MEME_SEARCH_TOKEN": ("meme_search", "token"),
    "MEME_SEARCH_TOP_K": ("meme_search", "top_k"),
    "MEME_SEARCH_MAX_DOWNLOAD_MB": ("meme_search", "max_download_mb"),
    "MEME_LIBRARY_FILE": ("meme", "library_file"),
    "MEME_MIN_DURATION": ("meme", "duration_min"),
    "MEME_MAX_DURATION": ("meme", "duration_max"),
    "MEME_COOLDOWN": ("editing", "cooldown"),
    "MEME_SCORE_THRESHOLD": ("editing", "threshold"),
    "MAX_MEMES_PER_MINUTE": ("editing", "max_memes_per_minute"),
    "SFX_ENABLED": ("sfx", "enabled"),
    "SFX_LIBRARY_FILE": ("sfx", "library_file"),
    "SFX_VOLUME": ("sfx", "volume"),
    "SFX_SCORE_THRESHOLD": ("sfx", "score_threshold"),
    "SFX_COOLDOWN": ("sfx", "cooldown"),
    "MAX_SFX_PER_MINUTE": ("sfx", "max_per_minute"),
    "SFX_MAX_DURATION": ("sfx", "duration_max"),
    "VIDEO_CODEC": ("output", "video_codec"),
    "AUDIO_CODEC": ("output", "audio_codec"),
    "OUTPUT_CRF": ("output", "crf"),
    "OUTPUT_PRESET": ("output", "preset"),
    "YOUTUBE_OWN_CHANNELS": ("download", "own_channels"),
}

_TEN_PROFILE = re.compile(r"^[\w-]+$")


# ------------------------------------------------------------------ nạp
def load_settings(profile: str | None = None, overrides: Mapping[str, Any] | None = None, *,
                  configs_dir: Path = CONFIGS_DIR, env: Mapping[str, str] | None = None,
                  root: Path = PROJECT_ROOT) -> Settings:
    """Ghép các lớp cấu hình rồi kiểm tra kiểu.

    `overrides` là dict lồng nhau từ cờ CLI, ví dụ {"editing": {"max_memes_per_minute": 3}}.
    `env` mặc định là .env + biến môi trường thật (biến thật thắng); test truyền dict riêng.
    Đường dẫn tương đối trong `paths` được tính từ `root`.
    """
    data = _read_yaml(configs_dir / "default.yaml")
    if profile and profile != "default":
        if not _TEN_PROFILE.match(profile):
            raise ConfigError(f"Tên profile không hợp lệ: {profile!r}")
        path = configs_dir / f"{profile}.yaml"
        if not path.exists():
            co_san = ", ".join(list_profiles(configs_dir)) or "(chưa có)"
            raise ConfigError(f"Không có profile '{profile}'. Có sẵn: {co_san}")
        data = deep_merge(data, _read_yaml(path))
    data = deep_merge(data, env_overrides(read_env() if env is None else env))
    if overrides:
        data = deep_merge(data, overrides)

    try:
        settings = Settings.model_validate(data)
    except ValidationError as e:
        raise ConfigError(
            "Cấu hình không hợp lệ (giá trị có thể đến từ configs/, .env hoặc cờ CLI):\n"
            + format_validation_error(e)
        ) from None
    settings.paths.data_dir = resolve_path(settings.paths.data_dir, root)
    settings.paths.assets_dir = resolve_path(settings.paths.assets_dir, root)
    settings.meme.library_file = resolve_path(settings.meme.library_file, root)
    settings.sfx.library_file = resolve_path(settings.sfx.library_file, root)
    return settings


def list_profiles(configs_dir: Path = CONFIGS_DIR) -> list[str]:
    return sorted(p.stem for p in configs_dir.glob("*.yaml") if p.stem != "default")


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Ghép dict lồng nhau: khóa của `override` đè `base`; dict con được ghép tiếp chứ không
    bị thay cả khối. Không sửa hai dict đầu vào."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def env_overrides(env: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """Biến có trong ENV_MAP → dict lồng nhau. Giá trị rỗng = không ghi đè."""
    out: dict[str, dict[str, str]] = {}
    for name, (section, key) in ENV_MAP.items():
        value = env.get(name)
        if value is not None and str(value).strip():
            out.setdefault(section, {})[key] = str(value).strip()
    return out


def read_env(env_file: Path = ENV_FILE) -> dict[str, str]:
    """Giá trị trong .env, bị biến môi trường thật đè lên."""
    from dotenv import dotenv_values

    values: dict[str, str] = {}
    if env_file.exists():
        values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    values.update(os.environ)
    return values


def format_validation_error(e: ValidationError) -> str:
    lines = []
    for err in e.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(gốc)"
        value = err.get("input")
        shown = "" if isinstance(value, dict) else f" (đang là {value!r})"
        lines.append(f"  - {where}: {err['msg']}{shown}")
    return "\n".join(lines)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise ConfigError(f"Không thấy file cấu hình {path}") from None
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name} sai cú pháp YAML: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} phải là bảng dạng `khóa: giá trị`")
    return data
