import re
import shutil

import pytest
import yaml

from automeme.config import (
    ENV_MAP,
    ConfigError,
    deep_merge,
    env_overrides,
    list_profiles,
    load_settings,
)
from automeme.utils.files import CONFIGS_DIR, PROJECT_ROOT

NO_ENV: dict[str, str] = {}  # không để .env / biến môi trường của máy lọt vào test


def test_default_yaml_hop_le_va_du_khoa():
    s = load_settings(env=NO_ENV)
    assert s.whisper.model == "large-v3"
    assert s.whisper.language == "vi"
    assert s.llm.backend == "ollama"
    assert s.ollama.model == "qwen3:8b"
    assert s.analyzer.previous_segments == 2
    assert s.analyzer.timing_delay == 0.15
    assert s.meme_search.max_download_mb == 25
    assert s.meme.library_file == (PROJECT_ROOT / "assets/memes/library.jsonl").resolve()
    assert s.ranking.semantic_weight == 0.45
    assert s.editing.cooldown == 7.0
    assert s.meme.duration_max == 2.5


@pytest.mark.parametrize("profile", list_profiles())
def test_moi_profile_deu_hop_le(profile):
    load_settings(profile, env=NO_ENV)


def test_co_du_ba_profile_cua_spec():
    assert {"subtle", "funny", "chaotic"} <= set(list_profiles())


def test_profile_chi_de_khoa_no_ghi():
    s = load_settings("subtle", env=NO_ENV)
    assert s.editing.max_memes_per_minute == 2
    assert s.editing.threshold == 0.8
    assert s.meme.duration_max == 1.5
    assert s.whisper.model == "large-v3"  # profile không ghi → giữ mặc định


def test_profile_khong_ton_tai_liet_ke_profile_co_san():
    with pytest.raises(ConfigError, match="subtle"):
        load_settings("khong_co", env=NO_ENV)


def test_ten_profile_la_duong_dan_bi_chan():
    with pytest.raises(ConfigError, match="không hợp lệ"):
        load_settings("../default", env=NO_ENV)


def test_bien_moi_truong_de_len_profile():
    s = load_settings("subtle", env={"MEME_COOLDOWN": "3", "WHISPER_DEVICE": "cpu"})
    assert s.editing.cooldown == 3.0
    assert s.whisper.device == "cpu"
    assert s.editing.max_memes_per_minute == 2  # khóa khác của profile vẫn giữ


def test_bien_rong_khong_ghi_de():
    s = load_settings(env={"MEME_COOLDOWN": "", "OLLAMA_MODEL": "   "})
    assert s.editing.cooldown == 7.0
    assert s.ollama.model == "qwen3:8b"


def test_co_cli_de_len_tat_ca():
    s = load_settings("subtle", {"editing": {"max_memes_per_minute": 4}},
                      env={"MAX_MEMES_PER_MINUTE": "8"})
    assert s.editing.max_memes_per_minute == 4


def test_log_level_khong_phan_biet_hoa_thuong():
    assert load_settings(env={"LOG_LEVEL": "debug"}).app.log_level == "DEBUG"


def test_gia_tri_sai_bao_ro_khoa_va_gia_tri():
    with pytest.raises(ConfigError, match=r"editing\.threshold.*1\.5"):
        load_settings(env={"MEME_SCORE_THRESHOLD": "1.5"})


def test_duration_min_lon_hon_max_bi_bat():
    with pytest.raises(ConfigError, match="duration_min"):
        load_settings(env={"MEME_MIN_DURATION": "3", "MEME_MAX_DURATION": "1"})


def test_tong_trong_so_ranking_phai_bang_mot():
    with pytest.raises(ConfigError, match="tổng năm trọng số"):
        load_settings(overrides={"ranking": {"semantic_weight": 0.5}}, env=NO_ENV)


def test_top_k_tuan_theo_gioi_han_api():
    with pytest.raises(ConfigError, match=r"meme_search\.top_k"):
        load_settings(env={"MEME_SEARCH_TOP_K": "21"})


def test_khoa_go_nham_bi_bat(tmp_path):
    shutil.copy(CONFIGS_DIR / "default.yaml", tmp_path / "default.yaml")
    (tmp_path / "typo.yaml").write_text("editing:\n  cooldwon: 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="cooldwon"):
        load_settings("typo", configs_dir=tmp_path, env=NO_ENV)


def test_yaml_sai_cu_phap_bao_loi_de_hieu(tmp_path):
    shutil.copy(CONFIGS_DIR / "default.yaml", tmp_path / "default.yaml")
    (tmp_path / "hong.yaml").write_text("editing: [chưa đóng\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_settings("hong", configs_dir=tmp_path, env=NO_ENV)


def test_duong_dan_tuong_doi_tinh_tu_goc(tmp_path):
    s = load_settings(env=NO_ENV, root=tmp_path)
    assert s.paths.data_dir == (tmp_path / "data").resolve()
    assert s.paths.assets_dir == (tmp_path / "assets").resolve()


def test_deep_merge_ghep_long_nhau_va_khong_sua_dau_vao():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    over = {"a": {"y": 3}, "c": 4}
    assert deep_merge(base, over) == {"a": {"x": 1, "y": 3}, "b": 1, "c": 4}
    assert base == {"a": {"x": 1, "y": 2}, "b": 1}


def test_env_overrides_chi_lay_bien_da_biet():
    out = env_overrides({"MEME_COOLDOWN": "5", "PATH": "C:/Windows", "OLLAMA_HOST": " http://x "})
    assert out == {"editing": {"cooldown": "5"}, "ollama": {"host": "http://x"}}


def test_env_map_tro_toi_khoa_co_that():
    """Mọi biến trong ENV_MAP phải trỏ tới một khóa có trong default.yaml."""
    data = yaml.safe_load((CONFIGS_DIR / "default.yaml").read_text(encoding="utf-8"))
    for name, (section, key) in ENV_MAP.items():
        assert key in data.get(section, {}), name


def test_env_example_chi_dung_bien_da_biet():
    """Biến trong .env.example (kể cả dòng đang comment) đều phải có trong ENV_MAP."""
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    names = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))
    assert names, "không đọc được biến nào — regex hỏng?"
    assert names - set(ENV_MAP) - {"ANTHROPIC_API_KEY"} == set()


def test_env_example_de_comment_tham_so_dung_video():
    """Nếu .env đặt sẵn MEME_COOLDOWN… thì --profile mất tác dụng — phải để dạng comment."""
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    profile_keys = [n for n, (section, _) in ENV_MAP.items() if section in ("editing", "meme")]
    for name in profile_keys:
        assert not re.search(rf"^{name}=", text, flags=re.MULTILINE), name
