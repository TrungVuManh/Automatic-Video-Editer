"""Cài bộ template meme phổ biến đã gắn nhãn ngữ nghĩa Việt–Anh."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from ..config import Settings
from ..utils.files import read_json
from ..utils.logger import log
from ..workspace import slug
from .local import tokenize, upsert_library_candidates
from .schema import MemeCandidate

CATALOG_PATH = Path(__file__).with_name("catalog") / "popular_imgflip.json"
POPULAR_HOST = "i.imgflip.com"
MAX_TEMPLATE_BYTES = 15 * 1024 * 1024


class PopularTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: HttpUrl
    labels: list[str] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(min_length=10)
    quality: float = Field(ge=0, le=1)
    safe: bool = True


class InstallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    installed: int
    reused: int
    failed: int
    errors: list[str]


def load_popular_catalog(path: Path = CATALOG_PATH) -> list[PopularTemplate]:
    rows = read_json(path)
    if not isinstance(rows, list):
        raise ValueError("Catalog meme phổ biến phải là một mảng JSON.")
    templates = [PopularTemplate.model_validate(row) for row in rows]
    ids = [item.template_id for item in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("Catalog meme phổ biến có template_id bị trùng.")
    unknown = sorted({label for item in templates for label in item.labels} - set(SEMANTICS))
    if unknown:
        raise ValueError("Catalog có semantic label chưa định nghĩa: " + ", ".join(unknown))
    return templates


def install_popular_memes(
    settings: Settings,
    *,
    limit: int = 100,
    catalog_path: Path = CATALOG_PATH,
    client_factory: Callable[..., Any] | None = None,
) -> InstallResult:
    """Tải tối đa `limit` template và upsert nhãn vào library local.

    Một ảnh lỗi không làm hỏng cả batch. Metadata chỉ được upsert cho file tải thành công hoặc
    đã tồn tại, vì provider local tuyệt đối không được trỏ tới một asset chưa có.
    """
    if not 1 <= limit <= 100:
        raise ValueError("Số meme cần cài phải nằm trong khoảng 1–100.")
    catalog = load_popular_catalog(catalog_path)[:limit]
    project_root = settings.paths.assets_dir.parent.resolve()
    target_dir = settings.paths.assets_dir / "memes" / "popular"
    target_dir.mkdir(parents=True, exist_ok=True)
    client = _client(client_factory)
    installed = reused = 0
    errors: list[str] = []
    candidates: list[MemeCandidate] = []
    try:
        for item in catalog:
            suffix = Path(urlparse(str(item.url)).path).suffix.casefold()
            filename = f"{slug(item.name)}-{item.template_id}{suffix}"
            output = target_dir / filename
            try:
                if output.is_file():
                    reused += 1
                else:
                    _download_template(client, str(item.url), output)
                    installed += 1
                candidates.append(_to_candidate(item, output, project_root))
            except Exception as exc:
                output.with_name(output.name + ".part").unlink(missing_ok=True)
                message = f"{item.name}: {exc}"
                errors.append(message)
                log.warning("Không cài được meme phổ biến %s", message)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    upsert_library_candidates(settings.meme.library_file, candidates)
    return InstallResult(
        total=len(catalog),
        installed=installed,
        reused=reused,
        failed=len(errors),
        errors=errors,
    )


def _client(factory: Callable[..., Any] | None):
    if factory is not None:
        return factory(timeout=30, follow_redirects=False)
    import httpx

    return httpx.Client(timeout=30, follow_redirects=False)


def _download_template(client: Any, url: str, output: Path) -> None:
    _validate_template_url(url)
    part = output.with_name(output.name + ".part")
    part.unlink(missing_ok=True)
    with client.stream("GET", url) as response:
        if 300 <= response.status_code < 400:
            raise ValueError("nguồn trả redirect")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError(f"MIME không hỗ trợ: {content_type or '?'}")
        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_TEMPLATE_BYTES:
            raise ValueError("file vượt giới hạn 15 MB")
        size = 0
        with open(part, "xb") as handle:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_TEMPLATE_BYTES:
                    raise ValueError("file vượt giới hạn khi đang tải")
                handle.write(chunk)
        if size == 0:
            raise ValueError("file rỗng")
    part.replace(output)


def _validate_template_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.scheme.casefold() != "https" or hostname != POPULAR_HOST or parsed.username:
        raise ValueError("URL template phải là HTTPS từ i.imgflip.com")


def _to_candidate(item: PopularTemplate, output: Path, project_root: Path) -> MemeCandidate:
    tags: set[str] = set(tokenize(item.name))
    emotions: set[str] = set()
    styles: set[str] = set()
    intensities = []
    for label in item.labels:
        semantic = SEMANTICS[label]
        tags.update(semantic["tags"])
        emotions.update(semantic["emotion"])
        styles.update(semantic["style"])
        intensities.append(semantic["intensity"])
    tags.update(item.aliases)
    return MemeCandidate(
        id=f"popular-imgflip-{item.template_id}",
        filename=output.resolve().relative_to(project_root).as_posix(),
        type="image",
        tags=sorted(tags),
        emotion=sorted(emotions),
        style=sorted(styles),
        description=item.description,
        intensity=max(intensities),
        quality=item.quality,
        safe=item.safe,
        language="none",
        source="local",
        source_url=str(item.url),
        license_note=(
            "User-generated template via Imgflip; quyền sử dụng chưa được Imgflip xác minh. "
            "Người dùng cần tự kiểm tra trước khi xuất bản thương mại."
        ),
    )


# Ontology nhỏ, song ngữ: LLM có thể sinh query Việt hoặc Anh mà local search vẫn tìm ra.
# Mỗi nhãn mở rộng đồng thời ba trục mà ranker đang dùng: semantic, emotion và style.
SEMANTICS: dict[str, dict[str, Any]] = {
    "agreement": {
        "tags": ["agreement", "teamwork", "đồng ý", "hợp tác", "điểm chung"],
        "emotion": ["approval", "unity", "hài lòng"],
        "style": ["comparison", "wholesome"],
        "intensity": 0.55,
    },
    "anger": {
        "tags": ["anger", "shouting", "tức giận", "quát", "bực mình"],
        "emotion": ["anger", "frustration", "bức xúc"],
        "style": ["reaction", "dialogue"],
        "intensity": 0.9,
    },
    "awkward": {
        "tags": ["awkward", "caught", "silence", "ngượng", "quê", "im lặng"],
        "emotion": ["awkward", "embarrassment", "xấu hổ"],
        "style": ["reaction", "silent"],
        "intensity": 0.55,
    },
    "bad-luck": {
        "tags": ["bad luck", "unfortunate", "xui xẻo", "đen đủi", "thất bại"],
        "emotion": ["sadness", "embarrassment", "bất lực"],
        "style": ["reaction", "self-deprecating"],
        "intensity": 0.65,
    },
    "bad-logic": {
        "tags": ["bad logic", "loophole", "lý luận ngược", "mẹo giả", "lách luật"],
        "emotion": ["smug", "confidence", "đắc ý"],
        "style": ["ironic", "advice"],
        "intensity": 0.55,
    },
    "bargain": {
        "tags": ["bargain", "low offer", "mặc cả", "trả giá", "đề nghị tệ"],
        "emotion": ["smug", "disappointment"],
        "style": ["offer", "dialogue"],
        "intensity": 0.5,
    },
    "blocked": {
        "tags": ["blocked", "escaping", "missed goal", "bị cản", "đuổi theo", "xa vời"],
        "emotion": ["desperation", "frustration", "bất lực"],
        "style": ["story", "reaction"],
        "intensity": 0.72,
    },
    "boredom": {
        "tags": ["boring", "nothing to do", "chán", "không quan tâm", "buồn tẻ"],
        "emotion": ["boredom", "indifference"],
        "style": ["reaction", "comparison"],
        "intensity": 0.4,
    },
    "celebration": {
        "tags": ["celebration", "cheers", "well done", "ăn mừng", "chúc mừng", "tuyệt vời"],
        "emotion": ["joy", "approval", "phấn khích"],
        "style": ["reaction", "celebration"],
        "intensity": 0.7,
    },
    "chaos": {
        "tags": ["chaos", "disaster", "hỗn loạn", "thảm họa", "gây chuyện"],
        "emotion": ["mischief", "shock"],
        "style": ["dark-humor", "reaction"],
        "intensity": 0.8,
    },
    "choice": {
        "tags": ["choice", "options", "lựa chọn", "chọn", "phương án"],
        "emotion": ["confusion", "uncertainty", "phân vân"],
        "style": ["choice", "comparison"],
        "intensity": 0.55,
    },
    "classy": {
        "tags": ["classy", "fancy", "upgrade", "sang chảnh", "nâng cấp", "quý tộc"],
        "emotion": ["pride", "approval"],
        "style": ["comparison", "classy"],
        "intensity": 0.5,
    },
    "confusion": {
        "tags": ["confused", "wrong", "what", "bối rối", "ngơ ngác", "nhận nhầm"],
        "emotion": ["confusion", "surprise"],
        "style": ["question", "reaction"],
        "intensity": 0.52,
    },
    "conspiracy": {
        "tags": ["conspiracy", "overthinking", "clues", "thuyết âm mưu", "suy diễn", "xâu chuỗi"],
        "emotion": ["obsession", "panic", "ám ảnh"],
        "style": ["explanation", "chaotic"],
        "intensity": 0.82,
    },
    "control": {
        "tags": ["control", "boss", "authority", "kiểm soát", "sếp", "nắm quyền"],
        "emotion": ["dominance", "confidence", "quyết đoán"],
        "style": ["power", "reaction"],
        "intensity": 0.75,
    },
    "danger": {
        "tags": ["danger", "threat", "hiding", "nguy hiểm", "đe dọa", "trốn"],
        "emotion": ["fear", "anxiety", "hoảng sợ"],
        "style": ["dramatic", "reaction"],
        "intensity": 0.82,
    },
    "debate": {
        "tags": ["debate", "opinion", "hot take", "tranh luận", "quan điểm", "phản biện"],
        "emotion": ["confident", "provocative"],
        "style": ["statement", "debate"],
        "intensity": 0.58,
    },
    "denial": {
        "tags": ["denial", "pretend okay", "ổn mà", "chối bỏ", "giả vờ bình thường"],
        "emotion": ["denial", "anxiety", "bất lực"],
        "style": ["ironic", "dark-humor"],
        "intensity": 0.68,
    },
    "dilemma": {
        "tags": ["dilemma", "hard choice", "khó chọn", "tiến thoái lưỡng nan", "lo lắng"],
        "emotion": ["anxiety", "confusion"],
        "style": ["choice", "reaction"],
        "intensity": 0.7,
    },
    "difficult": {
        "tags": ["difficult", "not easy", "impossible", "khó", "không đơn giản", "bất khả thi"],
        "emotion": ["serious", "warning"],
        "style": ["statement", "classic"],
        "intensity": 0.5,
    },
    "dislike": {
        "tags": ["dislike", "hate", "reject", "ghét", "không ưa", "tẩy chay"],
        "emotion": ["disgust", "disapproval", "bất mãn"],
        "style": ["reaction", "announcement"],
        "intensity": 0.68,
    },
    "duplicate": {
        "tags": ["same", "duplicate", "identical", "giống nhau", "bản sao", "cùng một kiểu"],
        "emotion": ["confusion", "surprise"],
        "style": ["comparison", "reaction"],
        "intensity": 0.58,
    },
    "escalation": {
        "tags": ["escalation", "argument", "getting worse", "leo thang", "cãi nhau", "căng thẳng"],
        "emotion": ["anger", "frustration"],
        "style": ["story", "dialogue"],
        "intensity": 0.88,
    },
    "excluded": {
        "tags": ["excluded", "left out", "unfair", "bị ra rìa", "bất công", "không có phần"],
        "emotion": ["surprise", "sadness", "tủi thân"],
        "style": ["comparison", "reaction"],
        "intensity": 0.52,
    },
    "giveaway": {
        "tags": ["everyone gets", "giveaway", "ai cũng có", "phát quà", "chia đều"],
        "emotion": ["excitement", "generosity"],
        "style": ["celebration", "reaction"],
        "intensity": 0.75,
    },
    "hidden-pain": {
        "tags": ["fake smile", "hidden pain", "cười gượng", "giấu nỗi đau", "ổn giả"],
        "emotion": ["sadness", "awkward", "đau khổ"],
        "style": ["ironic", "reaction"],
        "intensity": 0.55,
    },
    "imagination": {
        "tags": ["imagination", "creative", "magic", "tưởng tượng", "sáng tạo", "mơ mộng"],
        "emotion": ["wonder", "delight"],
        "style": ["whimsical", "reaction"],
        "intensity": 0.5,
    },
    "jealousy": {
        "tags": ["jealous", "watching others", "ghen tị", "nhìn người khác", "bị bỏ lại"],
        "emotion": ["jealousy", "sadness", "cô đơn"],
        "style": ["comparison", "reaction"],
        "intensity": 0.5,
    },
    "levels": {
        "tags": ["levels", "upgrade", "evolution", "cấp độ", "nâng cấp", "tiến hóa"],
        "emotion": ["amazement", "enlightenment"],
        "style": ["comparison", "chart"],
        "intensity": 0.65,
    },
    "lonely": {
        "tags": ["lonely", "alone", "cô đơn", "trống vắng", "một mình"],
        "emotion": ["loneliness", "sadness"],
        "style": ["reaction", "melancholy"],
        "intensity": 0.42,
    },
    "missing": {
        "tags": ["missing", "wish I had", "empty", "không có", "ước gì", "chỗ trống"],
        "emotion": ["sadness", "frustration", "tiếc nuối"],
        "style": ["self-deprecating", "reaction"],
        "intensity": 0.48,
    },
    "mocking": {
        "tags": ["mocking", "sarcasm", "cà khịa", "nhại lại", "châm chọc"],
        "emotion": ["sarcasm", "annoyance", "mỉa mai"],
        "style": ["mocking", "reaction"],
        "intensity": 0.7,
    },
    "neglect": {
        "tags": ["neglect", "favoritism", "ignored", "bỏ mặc", "thiên vị", "ưu tiên sai"],
        "emotion": ["frustration", "injustice"],
        "style": ["comparison", "story"],
        "intensity": 0.72,
    },
    "plan-fail": {
        "tags": ["plan fails", "backfire", "kế hoạch thất bại", "phản tác dụng", "ngớ người"],
        "emotion": ["shock", "confusion", "regret"],
        "style": ["story", "multi-panel"],
        "intensity": 0.72,
    },
    "praise": {
        "tags": ["masterpiece", "amazing", "peak", "tuyệt phẩm", "đỉnh cao", "quá hay"],
        "emotion": ["admiration", "awe", "thán phục"],
        "style": ["praise", "reaction"],
        "intensity": 0.78,
    },
    "preference": {
        "tags": ["preference", "approve", "reject", "thích", "không thích", "ưu tiên"],
        "emotion": ["approval", "disapproval"],
        "style": ["comparison", "reaction"],
        "intensity": 0.6,
    },
    "protect": {
        "tags": ["protect", "sacrifice", "shield", "bảo vệ", "hy sinh", "gánh thay"],
        "emotion": ["determination", "care", "cảm động"],
        "style": ["wholesome", "dramatic"],
        "intensity": 0.7,
    },
    "quick-fix": {
        "tags": ["quick fix", "patch", "temporary", "vá lỗi", "sửa tạm", "chữa cháy"],
        "emotion": ["desperation", "confidence"],
        "style": ["product", "reaction"],
        "intensity": 0.62,
    },
    "recurring": {
        "tags": ["again", "recurring", "zero days", "lại nữa", "tái diễn", "không được ngày nào"],
        "emotion": ["resignation", "annoyance", "ngán ngẩm"],
        "style": ["status", "ironic"],
        "intensity": 0.48,
    },
    "request": {
        "tags": ["request", "ask again", "support", "xin giúp", "nhờ", "kêu gọi"],
        "emotion": ["hopeful", "persistent", "tha thiết"],
        "style": ["request", "reaction"],
        "intensity": 0.48,
    },
    "reveal": {
        "tags": ["reveal", "true identity", "mask", "lật mặt", "hóa ra", "bản chất thật"],
        "emotion": ["surprise", "suspicion"],
        "style": ["reveal", "story"],
        "intensity": 0.7,
    },
    "revelation": {
        "tags": [
            "revelation",
            "always true",
            "plot twist",
            "hóa ra",
            "sự thật",
            "từ trước đến giờ",
        ],
        "emotion": ["shock", "betrayal", "ngỡ ngàng"],
        "style": ["plot-twist", "dramatic"],
        "intensity": 0.8,
    },
    "schadenfreude": {
        "tags": ["celebrate failure", "rival lost", "hả hê", "đối thủ thua", "ăn mừng thất bại"],
        "emotion": ["schadenfreude", "joy"],
        "style": ["dark-humor", "celebration"],
        "intensity": 0.68,
    },
    "secret": {
        "tags": ["secret", "nobody knows", "outsider", "bí mật", "họ không biết", "lạc lõng"],
        "emotion": ["loneliness", "smug"],
        "style": ["internal-monologue", "reaction"],
        "intensity": 0.4,
    },
    "self-sabotage": {
        "tags": ["self sabotage", "own fault", "blame others", "tự hại", "tự gây ra", "đổ lỗi"],
        "emotion": ["denial", "frustration", "quê"],
        "style": ["ironic", "story"],
        "intensity": 0.7,
    },
    "scream": {
        "tags": ["scream", "shout", "outburst", "hét", "gào", "bùng nổ"],
        "emotion": ["anger", "excitement", "kích động"],
        "style": ["loud", "reaction"],
        "intensity": 0.92,
    },
    "suspicious": {
        "tags": ["suspicious", "doubt", "skeptical", "nghi ngờ", "hoài nghi", "khó tin"],
        "emotion": ["suspicion", "confusion"],
        "style": ["question", "reaction"],
        "intensity": 0.5,
    },
    "temptation": {
        "tags": ["temptation", "distraction", "cám dỗ", "xao nhãng", "ham cái mới"],
        "emotion": ["temptation", "jealousy"],
        "style": ["comparison", "story"],
        "intensity": 0.65,
    },
    "then-now": {
        "tags": ["then versus now", "strong weak", "ngày xưa ngày nay", "mạnh yếu", "xuống cấp"],
        "emotion": ["pride", "embarrassment", "hoài niệm"],
        "style": ["comparison", "reaction"],
        "intensity": 0.62,
    },
    "waiting": {
        "tags": ["waiting forever", "delay", "late", "chờ mãi", "quá lâu", "trễ"],
        "emotion": ["boredom", "impatience", "mệt mỏi"],
        "style": ["exaggeration", "reaction"],
        "intensity": 0.5,
    },
}
