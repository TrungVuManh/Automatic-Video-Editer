"""Bước 4a — Claude chọn và cắt clip từ các ứng viên."""
from __future__ import annotations

from .claude_api import call_tool, log_prompt_size, make_client
from .common import FEEDBACK_FILE, PROMPTS_DIR, Job, fmt_time, log, read_json, read_jsonl, write_json

LOAI = ["hài", "clutch", "cay cú", "fail", "khác"]

SUBMIT_TOOL = {
    "name": "submit_clips",
    "description": "Nộp danh sách clip đã chọn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "clips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string", "description": "id ứng viên, ví dụ k03"},
                        "start": {"type": "number", "description": "giây tính từ đầu VOD"},
                        "end": {"type": "number"},
                        "loai": {"type": "string", "enum": LOAI},
                        "diem": {"type": "integer", "minimum": 1, "maximum": 10},
                        "tieu_de": {"type": "string", "description": "tiêu đề gợi tò mò, dưới 60 ký tự"},
                        "hook": {"type": "string", "description": "câu mở đầu cho Shorts"},
                        "ly_do": {"type": "string", "description": "vì sao chọn, 1 câu"},
                    },
                    "required": ["candidate_id", "start", "end", "loai", "diem", "tieu_de", "hook", "ly_do"],
                },
            }
        },
        "required": ["clips"],
    },
}


def select_clips(job: Job, settings: dict, streamer: dict) -> list[dict]:
    cands = read_json(job.candidates)
    segments = read_json(job.segments) if job.segments.exists() else []
    words = read_json(job.words) if job.words.exists() else []
    chat = read_json(job.chat) if job.chat.exists() else []
    if not words:
        log.warning("words.json rỗng — không snap được vào ranh giới từ, clip có thể cắt giữa từ.")

    prompt = build_prompt(cands, segments, chat, settings, streamer, job.streamer)
    job.path("candidates", "prompt_last.md").write_text(prompt, encoding="utf-8")  # ghi trước khi gọi, để debug cả khi API lỗi
    log_prompt_size(prompt)

    model = settings["models"]["select"]
    log.info("Gửi %d ứng viên cho %s...", len(cands), model)
    raw = call_tool(make_client(), model=model, tool=SUBMIT_TOOL, content=prompt,
                    max_tokens=8000, job=job, step="select")["clips"]

    clips, problems = validate_clips(raw, cands, settings["clips"])
    for p in problems:
        log.warning("Loại/sửa clip: %s", p)
    clips = [snap_to_words(c, words) for c in clips]

    write_json(job.clips, clips)
    log.info("Bước 4 xong: %d clip → %s", len(clips), job.clips)
    return clips


# ------------------------------------------------------------------ prompt
def build_prompt(cands, segments, chat, settings, streamer, streamer_key) -> str:
    template = (PROMPTS_DIR / "select_clips.md").read_text(encoding="utf-8")
    ccfg = settings["clips"]
    return template.format(
        ten=streamer.get("ten", ""),
        game_chinh=", ".join(streamer.get("game_chinh", [])),
        phong_cach=streamer.get("phong_cach", ""),
        khong_duoc_dung="; ".join(streamer.get("khong_duoc_dung", [])) or "không có",
        n_candidates=len(cands),
        max_clips=ccfg["max_clips"], min_sec=ccfg["min_sec"], max_sec=ccfg["max_sec"],
        feedback_block=feedback_block(streamer_key),
        candidates_block="\n\n".join(candidate_text(c, segments, chat) for c in cands),
    )


def candidate_text(c: dict, segments: list[dict], chat: list[dict], max_chat: int = 15) -> str:
    s, e = c["start"], c["end"]
    lines = [f"### {c['id']}  ({fmt_time(s)} → {fmt_time(e)}, giây {s}–{e}; đỉnh tại {c['peaks']})"]

    if chat:
        in_span = [m for m in chat if s <= m["t"] < e]
        buckets = [0] * max(1, int((e - s) // 10) + 1)
        for m in in_span:
            buckets[min(len(buckets) - 1, int((m["t"] - s) // 10))] += 1
        lines.append(f"Chat mỗi 10s: {buckets}")
        # Tin nhắn gần đỉnh nhất; gộp tin trùng nội dung (spam "KKKK") thành một dòng có số lần
        near = sorted(in_span, key=lambda m: min(abs(m["t"] - p) for p in c["peaks"]))
        groups: dict[str, tuple[str, list[float]]] = {}
        for m in near:
            text = m["text"].strip()[:80]
            key = text.lower()
            if key and (key in groups or len(groups) < max_chat):
                groups.setdefault(key, (text, []))[1].append(m["t"])
        for text, ts in sorted(groups.values(), key=lambda g: min(g[1])):
            times = f"{min(ts):.0f}" if len(ts) == 1 else f"{min(ts):.0f}–{max(ts):.0f}, ×{len(ts)}"
            lines.append(f"  [chat {times}] {text}")

    lines.append("Transcript:")
    spoken = [seg for seg in segments if seg["end"] > s and seg["start"] < e]
    lines += [f"  [{seg['start']:.1f}] {seg['text']}" for seg in spoken] or ["  (không có lời nói)"]
    return "\n".join(lines)


def feedback_block(streamer_key: str, limit: int = 10) -> str:
    fb = [r for r in read_jsonl(FEEDBACK_FILE) if r.get("streamer") == streamer_key and r.get("kind") == "clip"]
    if not fb:
        return ""
    fb = fb[-limit:]
    rows = []
    for r in fb:
        tag = "ĐƯỢC DUYỆT" if r["approved"] else "BỊ LOẠI"
        note = f" — ghi chú: {r['note']}" if r.get("note") else ""
        rows.append(f"- [{tag}] ({r['loai']}) {r['tieu_de']}: {r['ly_do']}{note}")
    return "## Gu của kênh (từ các lần duyệt trước)\n" + "\n".join(rows)


# ------------------------------------------------------------------ kiểm tra
def validate_clips(raw: list[dict], cands: list[dict], ccfg: dict, slack: float = 5.0):
    """Chặn lỗi của model: id bịa, thời gian ngoài ứng viên, độ dài sai, clip trùng nhau."""
    by_id = {c["id"]: c for c in cands}
    ok, problems = [], []
    for c in raw:
        cand = by_id.get(c.get("candidate_id"))
        if cand is None:
            problems.append(f"id ứng viên không tồn tại: {c.get('candidate_id')}")
            continue
        start = max(float(c["start"]), cand["start"] - slack, 0.0)
        end = min(float(c["end"]), cand["end"] + slack)
        dur = end - start
        if dur < ccfg["min_sec"] * 0.8 or dur > ccfg["max_sec"] * 1.2:
            problems.append(f"{c['candidate_id']}: độ dài {dur:.0f}s ngoài khoảng cho phép")
            continue
        if any(start < o["end"] and end > o["start"] for o in ok):
            problems.append(f"{c['candidate_id']}: trùng thời gian với clip khác")
            continue
        ok.append({**c, "start": round(start, 2), "end": round(end, 2), "approved": None})

    ok.sort(key=lambda c: -c["diem"])
    ok = ok[: ccfg["max_clips"]]
    for i, c in enumerate(sorted(ok, key=lambda c: c["start"]), 1):
        c["id"] = f"c{i:02d}"
    return sorted(ok, key=lambda c: c["start"]), problems


def snap_to_words(clip: dict, words: list[dict], pad_in: float = 0.15, pad_out: float = 0.35) -> dict:
    """Không cắt giữa từ: kéo điểm đầu về đầu từ, điểm cuối ra hết từ."""
    if not words:
        return clip
    s, e = clip["start"], clip["end"]
    for w in words:
        if w["start"] <= s < w["end"]:
            s = w["start"]
        if w["start"] < e <= w["end"]:
            e = w["end"]
    return {**clip, "start": round(max(0.0, s - pad_in), 2), "end": round(e + pad_out, 2)}
