"""Backend faster-whisper (chạy trên CTranslate2, không cần PyTorch).

`faster_whisper` chỉ được import bên trong hàm: test và các lệnh khác vẫn chạy được trên máy
chưa cài nó.
"""
from __future__ import annotations

import gc
import os
import sys
from pathlib import Path
from typing import Any

from ..config import WhisperSettings
from ..utils.logger import log
from .base import Transcriber

CHUA_CAI = ('Chưa cài faster-whisper. Chạy: python -m pip install -e ".[asr-cuda]" '
            '(máy không có GPU NVIDIA thì dùng ".[asr]" và đặt WHISPER_DEVICE=cpu).')


class FasterWhisperTranscriber(Transcriber):
    """Model được nạp ở lần nhận dạng đầu tiên, không nạp lúc khởi tạo."""

    def __init__(self, cfg: WhisperSettings) -> None:
        self.cfg = cfg
        self._model: Any = None

    def transcribe(self, audio: Path) -> dict[str, Any]:
        cfg = self.cfg
        model = self._load()
        log.info("Nhận dạng %s (ngôn ngữ %s)...", audio.name, cfg.language)
        from ..workspace import hotwords_text

        goi_y = hotwords_text(cfg) or None
        if goi_y:
            log.info("Gợi ý từ vựng cho Whisper: %s", cfg.hotwords_file)
        segments, info = model.transcribe(
            str(audio),
            language=cfg.language,
            beam_size=cfg.beam_size,
            vad_filter=cfg.vad_filter,
            condition_on_previous_text=cfg.condition_on_previous_text,
            # hotwords đi vào mọi cửa sổ; initial_prompt chỉ tác động 30 giây đầu khi
            # condition_on_previous_text=false (xem faster_whisper/transcribe.py)
            hotwords=goi_y,
            word_timestamps=True,
        )
        tong = float(getattr(info, "duration", 0.0) or 0.0)
        ra: list[dict[str, Any]] = []
        moc = 0.0
        # `segments` là generator: việc nhận dạng thật sự diễn ra trong vòng lặp này
        for seg in segments:
            ra.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                # để lọc câu bịa ở đoạn im lặng (normalize.drop_hallucinations)
                "no_speech_prob": getattr(seg, "no_speech_prob", None),
                "avg_logprob": getattr(seg, "avg_logprob", None),
                "words": [{"w": w.word, "start": w.start, "end": w.end}
                          for w in (seg.words or [])],
            })
            if tong and seg.end - moc >= max(10.0, tong / 10):
                moc = seg.end
                log.info("  ... %.0f%% (%.0f/%.0f giây, %d đoạn)",
                         100 * seg.end / tong, seg.end, tong, len(ra))
        return {
            "language": getattr(info, "language", cfg.language),
            "duration": tong or None,
            "segments": ra,
        }

    def unload(self) -> None:
        """Trả VRAM lại trước khi gọi LLM — máy 8 GB không nạp được Whisper và LLM cùng lúc."""
        self._model = None
        gc.collect()

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        them_dll_cuda()
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise RuntimeError(CHUA_CAI) from e

        cfg = self.cfg
        log.info("Nạp Whisper %s (%s, %s) — lần đầu phải tải model, có thể mất vài phút.",
                 cfg.model, cfg.device, cfg.compute_type)
        try:
            self._model = WhisperModel(cfg.model, device=cfg.device,
                                       compute_type=cfg.compute_type)
        except Exception as e:
            raise RuntimeError(giai_thich_loi_model(e, cfg.device, cfg.compute_type)) from e
        return self._model


def them_dll_cuda() -> None:
    """Windows: cho hệ điều hành thấy DLL CUDA mà pip cài trong site-packages/nvidia/*/bin.

    Các thư mục đó không nằm trong PATH nên CTranslate2 không tự tìm ra — đây chính là
    nguyên nhân của lỗi kinh điển "Could not locate cudnn_ops64_9.dll".
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return  # cài kiểu [asr] (không kèm CUDA), hoặc CUDA đã cài sẵn ngoài hệ thống
    for goc in nvidia.__path__:
        for bin_dir in sorted(Path(goc).glob("*/bin")):
            if not bin_dir.is_dir():
                continue
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            log.debug("Thêm thư mục DLL CUDA: %s", bin_dir)


def giai_thich_loi_model(e: Exception, device: str, compute_type: str) -> str:
    """Đổi lỗi khó hiểu của CTranslate2 thành câu tiếng Việt nói rõ phải làm gì. Hàm thuần."""
    loi = str(e)
    thap = loi.lower()
    if "cudnn" in thap or "cublas" in thap or "could not locate" in thap:
        return ("Thiếu thư viện CUDA (cuDNN/cuBLAS). Cài: "
                'python -m pip install -e ".[asr-cuda]" — hoặc chạy CPU bằng '
                "WHISPER_DEVICE=cpu và WHISPER_COMPUTE_TYPE=int8. Chi tiết: " + loi)
    if "out of memory" in thap:
        return (f"GPU hết VRAM khi nạp model với compute_type={compute_type}. Thử "
                "WHISPER_COMPUTE_TYPE=int8_float16, hoặc model nhỏ hơn "
                "(WHISPER_MODEL=large-v3-turbo). Chi tiết: " + loi)
    if "no cuda-capable device" in thap or "cuda driver" in thap or "cuda runtime" in thap:
        return ("Không dùng được GPU (thiếu driver NVIDIA?). Kiểm tra bằng `nvidia-smi`, hoặc "
                "chạy CPU: WHISPER_DEVICE=cpu, WHISPER_COMPUTE_TYPE=int8. Chi tiết: " + loi)
    if "compute type" in thap:
        return (f"compute_type={compute_type} không chạy được trên device={device}. Dùng "
                "float16 cho GPU, int8 cho CPU. Chi tiết: " + loi)
    if "connection" in thap or "timed out" in thap or "resolve" in thap:
        return "Không tải được model (kiểm tra mạng). Chi tiết: " + loi
    return "Không nạp được model Whisper: " + loi
