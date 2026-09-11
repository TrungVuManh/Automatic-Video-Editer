"""Đổi qua lại giữa số giây và chuỗi thời gian dạng `00:13.20` (dạng SPEC dùng)."""
from __future__ import annotations

_DANG_DUNG = "dạng đúng: 13.2, 00:13.20 hoặc 1:02:03.5"


def format_ts(sec: float) -> str:
    """13.2 → '00:13.20'. Từ 1 giờ trở lên thêm phần giờ: '1:02:03.50'."""
    cs = int(round(max(0.0, float(sec)) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    if h:
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    return f"{m:02d}:{s:02d}.{cs:02d}"


def parse_ts(value: str | float | int) -> float:
    """'13.2' | '00:13.20' | '1:02:03.5' | 13.2 → số giây (làm tròn tới mili giây)."""
    if isinstance(value, int | float):
        nums = [float(value)]
    else:
        parts = str(value).strip().split(":")
        if len(parts) > 3 or any(not p.strip() for p in parts):
            raise ValueError(f"Thời gian không hợp lệ: {value!r} ({_DANG_DUNG})")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"Thời gian không hợp lệ: {value!r} ({_DANG_DUNG})") from None

    # Phút và giây phía sau phải < 60; không có số âm
    if any(n < 0 for n in nums) or any(n >= 60 for n in nums[1:]):
        raise ValueError(f"Thời gian không hợp lệ: {value!r} ({_DANG_DUNG})")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return round(total, 3)
