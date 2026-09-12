"""Test phần thuần của backend Whisper — không cần cài faster-whisper hay có GPU."""
import pytest

from automeme.config import load_settings
from automeme.transcription.whisper import FasterWhisperTranscriber, giai_thich_loi_model


@pytest.mark.parametrize("loi, mong_doi", [
    ("Could not locate cudnn_ops64_9.dll", "asr-cuda"),
    ("Library cublas64_12.dll is not found", "asr-cuda"),
    ("CUDA failed with error out of memory", "int8_float16"),
    ("no CUDA-capable device is detected", "nvidia-smi"),
    ("Requested compute type float16 is not supported", "float16 cho GPU"),
    ("Connection timed out", "mạng"),
    ("chuyện lạ chưa từng thấy", "Không nạp được model Whisper"),
])
def test_dich_loi_sang_huong_dan_cu_the(loi, mong_doi):
    assert mong_doi in giai_thich_loi_model(RuntimeError(loi), "cuda", "float16")


def test_dich_loi_giu_nguyen_van_loi_goc():
    goc = "Could not locate cudnn_ops64_9.dll"
    assert goc in giai_thich_loi_model(RuntimeError(goc), "cuda", "float16")


def test_khoi_tao_khong_nap_model(tmp_path):
    """Tạo đối tượng phải rẻ: model chỉ nạp khi thật sự nhận dạng."""
    t = FasterWhisperTranscriber(load_settings(env={}, root=tmp_path).whisper)
    assert t._model is None
    t.unload()  # gọi khi chưa nạp cũng không sao
    assert t._model is None
