"""Bước 2 — Tiền xử lý: transcript theo từ, chuẩn hóa chat, âm lượng theo giây."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .common import Job, log, read_json, write_json

BOT_NAMES = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot"}


def preprocess(job: Job, settings: dict) -> None:
    if job.chat_raw.exists() and not job.chat.exists():
        msgs = parse_chat(job.chat_raw, job.platform)
        write_json(job.chat, msgs)
        log.info("Chat: %d tin nhắn", len(msgs))

    if not job.loudness.exists():
        write_json(job.loudness, compute_loudness(job.audio))

    if not job.words.exists():
        words, segments = transcribe(job.audio, settings["asr"])
        write_json(job.words, words)
        write_json(job.segments, segments)
        log.info("Transcript: %d từ, %d câu", len(words), len(segments))
        if segments and not words:
            log.warning(
                "KHÔNG có timestamp theo từ! Phụ đề karaoke và việc cắt đúng ranh giới từ sẽ "
                "không dùng được. Cách xử lý: đặt `asr.align_model` (model wav2vec2 tiếng Việt "
                "trên Hugging Face) trong config/settings.yaml, hoặc đổi `asr.backend` sang "
                "faster-whisper rồi xóa transcript/ và chạy lại bước preprocess."
            )

    log.info("Bước 2 xong.")


# ------------------------------------------------------------------ chat
def parse_chat(path: Path, platform: str) -> list[dict]:
    """Trả về danh sách {t, user, text} sắp theo thời gian, đã bỏ bot."""
    msgs = _parse_youtube(path) if platform == "youtube" else _parse_twitch(path)
    msgs = [m for m in msgs if m["user"].lower() not in BOT_NAMES and m["t"] >= 0]
    return sorted(msgs, key=lambda m: m["t"])


def _parse_youtube(path: Path) -> list[dict]:
    """File .live_chat.json của yt-dlp: mỗi dòng là một JSON."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                action = json.loads(line)["replayChatItemAction"]
                t = int(action.get("videoOffsetTimeMsec", -1)) / 1000
                for a in action.get("actions", []):
                    r = a.get("addChatItemAction", {}).get("item", {}).get("liveChatTextMessageRenderer")
                    if not r:
                        continue  # bỏ qua superchat/membership/sự kiện hệ thống
                    text = "".join(
                        run.get("text") or _emoji_text(run.get("emoji"))
                        for run in r.get("message", {}).get("runs", [])
                    )
                    out.append({"t": t, "user": r.get("authorName", {}).get("simpleText", ""), "text": text})
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    return out


def _emoji_text(emoji: dict | None) -> str:
    if not emoji:
        return ""
    shortcuts = emoji.get("shortcuts") or []
    return shortcuts[0] if shortcuts else ""


def _parse_twitch(path: Path) -> list[dict]:
    """File JSON của TwitchDownloaderCLI chatdownload."""
    data = read_json(path)
    return [
        {
            "t": float(c["content_offset_seconds"]),
            "user": c.get("commenter", {}).get("display_name", ""),
            "text": c.get("message", {}).get("body", ""),
        }
        for c in data.get("comments", [])
    ]


# ------------------------------------------------------------------ âm lượng
def compute_loudness(audio: Path) -> list[float]:
    """RMS (dB) cho từng giây. Đọc theo khối nên không tốn RAM với VOD dài."""
    import soundfile as sf

    info = sf.info(str(audio))
    sr = info.samplerate
    out = []
    for block in sf.blocks(str(audio), blocksize=sr, dtype="float32", fill_value=0.0):
        if block.ndim > 1:
            block = block.mean(axis=1)
        rms = float(np.sqrt(np.mean(block ** 2)) + 1e-9)
        out.append(round(20 * np.log10(rms), 2))
    log.info("Âm lượng: %d giây", len(out))
    return out


# ------------------------------------------------------------------ transcript
def transcribe(audio: Path, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Trả về (words, segments). words: {w, start, end}; segments: {start, end, text}."""
    backend = cfg.get("backend", "whisperx")
    log.info("Transcript bằng %s (%s)... bước chậm nhất", backend, cfg["model"])
    try:
        if backend == "whisperx":
            return _whisperx(audio, cfg)
        return _faster_whisper(audio, cfg)
    except ImportError as e:
        raise RuntimeError(
            f"Chưa cài backend '{backend}'. Chạy: pip install -r requirements-asr.txt "
            f"(cài PyTorch bản CUDA trước). Chi tiết: {e}"
        ) from e


def _whisperx(audio: Path, cfg: dict):
    import whisperx

    device = cfg["device"]
    model = whisperx.load_model(cfg["model"], device, compute_type=cfg["compute_type"],
                                language=cfg["language"])
    wav = whisperx.load_audio(str(audio))
    result = model.transcribe(wav, batch_size=cfg["batch_size"])
    # WhisperX không có sẵn model căn chỉnh cho mọi ngôn ngữ. Với tiếng Việt thường phải
    # chỉ tên một model wav2vec2 cụ thể qua `asr.align_model` trong settings.yaml.
    align_kwargs = {"model_name": cfg["align_model"]} if cfg.get("align_model") else {}
    try:
        align_model, meta = whisperx.load_align_model(language_code=cfg["language"], device=device,
                                                      **align_kwargs)
        result = whisperx.align(result["segments"], align_model, meta, wav, device,
                                return_char_alignments=False)
    except Exception as e:
        log.warning("Căn chỉnh theo từ thất bại (%s) — dùng timestamp theo câu.", e)

    segments, words = [], []
    for seg in result["segments"]:
        segments.append({"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()})
        for w in seg.get("words", []):
            if "start" in w and "end" in w:  # từ không căn được sẽ thiếu timestamp
                words.append({"w": w["word"], "start": w["start"], "end": w["end"]})
    return words, segments


def _faster_whisper(audio: Path, cfg: dict):
    from faster_whisper import WhisperModel

    model = WhisperModel(cfg["model"], device=cfg["device"], compute_type=cfg["compute_type"])
    seg_iter, _ = model.transcribe(str(audio), language=cfg["language"],
                                   word_timestamps=True, vad_filter=True)
    segments, words = [], []
    for seg in seg_iter:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "start": w.start, "end": w.end})
    return words, segments
