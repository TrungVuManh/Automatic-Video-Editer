"""Lớp mỏng bao quanh Anthropic SDK.

Gom vào một chỗ: tạo client (có retry), gọi tool và lấy JSON, ghi token vào
usage.json, dịch lỗi API sang thông báo tiếng Việt hữu ích. Các bước gọi Claude
(chọn clip, chèn meme, metadata) đều đi qua đây.
"""
from __future__ import annotations

from typing import Any

from .common import Job, log, record_usage

MAX_RETRIES = 3  # SDK tự thử lại 429/5xx với backoff lũy thừa


def make_client(max_retries: int = MAX_RETRIES):
    """Tạo client. API key lấy từ biến môi trường ANTHROPIC_API_KEY (nạp từ .env)."""
    import anthropic

    return anthropic.Anthropic(max_retries=max_retries)


def call_tool(client, *, model: str, tool: dict, content: Any, max_tokens: int = 8000,
              job: Job | None = None, step: str = "") -> dict:
    """Gọi Claude, ép trả lời bằng `tool`, trả về dict đối số của tool.

    `content` là chuỗi prompt hoặc danh sách content block (khi có ảnh).
    """
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        raise RuntimeError(explain_error(e)) from e

    if job is not None:
        record_usage(job, step or tool["name"], model, resp.usage)

    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError("Claude từ chối yêu cầu này. Xem lại nội dung prompt/ứng viên.")
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError(f"Claude không gọi tool '{tool['name']}' (stop_reason="
                       f"{getattr(resp, 'stop_reason', '?')}). Thử lại hoặc rút gọn prompt.")


def explain_error(e: Exception) -> str:
    """Đổi lỗi SDK thành câu tiếng Việt nói rõ phải làm gì."""
    try:
        import anthropic

        if isinstance(e, anthropic.AuthenticationError):
            return "API key sai hoặc thiếu — kiểm tra ANTHROPIC_API_KEY trong file .env."
        if isinstance(e, anthropic.PermissionDeniedError):
            return "API key không có quyền dùng model này."
        if isinstance(e, anthropic.NotFoundError):
            return "Không có model này — kiểm tra mục `models` trong config/settings.yaml."
        if isinstance(e, anthropic.RateLimitError):
            return (f"Bị giới hạn tốc độ sau {MAX_RETRIES} lần thử lại. Đợi vài phút rồi chạy "
                    f"lại (bước đã xong sẽ được bỏ qua).")
        if isinstance(e, anthropic.BadRequestError):
            return (f"Yêu cầu không hợp lệ, thường do prompt quá dài — giảm `candidates.top_k` "
                    f"trong settings.yaml. Chi tiết: {e}")
        if isinstance(e, anthropic.APIConnectionError):
            return "Không kết nối được tới API Anthropic — kiểm tra mạng/proxy."
        if isinstance(e, anthropic.APIStatusError):
            return f"Lỗi API ({e.status_code}) sau {MAX_RETRIES} lần thử lại: {e}"
    except Exception:  # anthropic chưa cài hoặc bị giả lập trong test
        pass
    return str(e)


def log_prompt_size(prompt: str) -> None:
    """Ước lượng thô số token vào để cảnh báo sớm trước khi gửi (~3.5 ký tự/token)."""
    approx = len(prompt) // 3.5
    log.info("Prompt: %d ký tự (~%.0f token)", len(prompt), approx)
    if approx > 60_000:
        log.warning("Prompt rất dài (~%.0fk token). Cân nhắc giảm `candidates.top_k`.", approx / 1000)
