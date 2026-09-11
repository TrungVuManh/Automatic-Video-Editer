# HANDOFF — Tài liệu bàn giao dự án automeme

> Dành cho **Claude Code** (và người phát triển). Đọc toàn bộ ở đầu mỗi phiên. Sau mỗi việc
> hoàn thành, cập nhật **Checklist** (mục 6) và **Nhật ký tiến độ** (mục 8).
> Đặc tả gốc: [`SPEC.md`](SPEC.md). Khi hai file mâu thuẫn, file này đúng (xem mục 4).

---

## 1. Mục tiêu

Công cụ Python chạy trên Windows, local-first: nhận một video tiếng Việt, tìm khoảnh khắc nên
chèn meme/reaction, tìm meme theo ngữ nghĩa, sinh `timeline.json` để người duyệt, rồi dùng
FFmpeg render.

**MVP xong khi** (SPEC §61): với video tiếng Việt 30–90 giây, hệ thống tự transcribe, giữ
timestamp, tìm khoảnh khắc, sinh query reaction, lấy meme ứng viên, chọn meme, chặn chèn quá
dày, xuất timeline sửa được, render, giữ nguyên audio gốc, xuất MP4 — không phải sửa code.

**Ưu tiên** (SPEC §84): đúng lúc > nhiều tính năng; 3 meme rất đúng > 15 meme gần đúng.

---

## 2. Hiện trạng — Stage A xong

### Module

| File | Vai trò | Ghi chú |
|---|---|---|
| `src/automeme/cli.py` | CLI Typer | `doctor` chạy được; `transcribe/analyze/inspect/render/run` là khung, thoát mã 1 và báo thuộc iteration nào. Callback nạp cấu hình mặc định để đặt mức log + bật file log |
| `src/automeme/config.py` | Nạp cấu hình | `load_settings(profile, overrides, *, configs_dir, env, root)`; pydantic `extra="forbid"`; `ENV_MAP` ánh xạ tên biến SPEC §14 → khóa |
| `src/automeme/doctor.py` | `automeme doctor` | Python, cấu hình, `.env`, ffmpeg/ffprobe + phiên bản, faster-whisper, GPU (nvidia-smi), Ollama (GET `/api/tags` + có model chưa) hoặc Claude, docker, git, UTF-8 |
| `src/automeme/media/ffmpeg.py` | Chạy lệnh ngoài | `which` (tìm cả `Scripts/` của venv), `require_binary`, `run_cmd` (list args, log DEBUG nguyên lệnh), `CommandError` |
| `src/automeme/media/probe.py` | ffprobe | `probe()` → `MediaInfo` (thời lượng, kích thước, fps, audio, sample rate, kênh, định dạng); `parse_probe` là hàm thuần, bỏ qua ảnh bìa |
| `src/automeme/media/audio.py` | Tách audio | WAV PCM 16-bit mono 16 kHz; bỏ qua nếu đã có; ghi file `.part` rồi đổi tên |
| `src/automeme/utils/files.py` | Đường dẫn, JSON | `PROJECT_ROOT`, `CONFIGS_DIR`, `PROMPTS_DIR`; `write_json` UTF-8, ghi file tạm rồi đổi tên |
| `src/automeme/utils/timestamps.py` | Thời gian | `format_ts(13.2) → "00:13.20"`, `parse_ts` |
| `src/automeme/utils/logger.py` | Log | `setup_logging(level)` (gọi lại được), `add_file_log` → `data/logs/automeme.log` (DEBUG, xoay vòng 5 MB × 3) |

### Cấu hình

`configs/default.yaml` (đủ mọi khóa) → `configs/<profile>.yaml` → biến môi trường/`.env` →
cờ CLI. Tên biến môi trường theo SPEC §14, danh sách đầy đủ trong `config.ENV_MAP`. Biến rỗng
= không ghi đè. Có test giữ `.env.example` và `ENV_MAP` luôn khớp nhau.

### Test

`pytest -q` — **73 test**, chạy không cần GPU, Ollama, API key hay mạng. Test tách audio thật
(`test_tach_audio_that_tren_video_tu_sinh`) tự bỏ qua nếu không có FFmpeg; CI cài FFmpeg nên
chạy cả nó. CI (GitHub Actions) chạy `ruff check src tests` + `pytest -q`.

### Máy người dùng (đo 2026-09-11)

- Windows 11. Python trên PATH là bản *embeddable* 3.13 (không có venv) → dự án dùng `.venv`
  dựng từ Python 3.11.9. **Venv không được kích hoạt sẵn**: gọi qua `.venv\Scripts\...`.
- FFmpeg 9.0.1 (winget), GPU RTX 4060 Laptop **8 GB VRAM**, Docker, gh, git.
- **Chưa có:** Ollama, faster-whisper, file `.env`.
- 8 GB VRAM đủ cho Whisper large-v3 *hoặc* qwen3:8b, không đủ nạp cả hai cùng lúc → phải giải
  phóng Whisper trước khi gọi Ollama (Ollama giữ model trong VRAM ~5 phút sau lần gọi cuối).

---

## 3. Quy tắc làm việc

1. **Lập kế hoạch trước khi code** mỗi hạng mục: file tạo/sửa, hàm chính, định dạng JSON/config
   mới, test sẽ viết. Chờ người dùng đồng ý.
2. **Hàm thuần tách khỏi I/O**: dựng filtergraph, chuẩn hóa transcript, lọc cơ hội meme, xếp hạng
   là hàm thuần có test; phần gọi FFmpeg/Ollama/API mỏng nhất có thể.
3. **Import nặng bên trong hàm** (faster_whisper, ctranslate2, ollama, anthropic, torch).
4. **Không tin LLM** (SPEC §24, §51, §53): output qua model pydantic + `validate_*`; JSON hỏng thì
   thử lại 1 lần rồi bỏ ứng viên, không làm hỏng cả pipeline. Ràng buộc cứng (cooldown, số
   meme/phút, giới hạn thời lượng, chồng lấn, file tồn tại, timestamp hợp lệ) do **code** quyết định.
5. **Mọi component có interface** (SPEC §13): `Transcriber`, LLM, `MemeProvider`, renderer.
6. **Không đổi định dạng JSON đã có** mà không cập nhật test, mục 2 file này và mọi chỗ đọc nó.
   Khóa JSON theo tiếng Anh như SPEC.
7. **Tham số** dựng video trong `configs/`, tham số máy trong `.env`, prompt trong `prompts/`.
8. **Mỗi bước bỏ qua nếu output đã tồn tại**; ghi ra file tạm rồi đổi tên.
9. **FFmpeg chỉ gọi qua `automeme.media`**, lệnh dạng list. File media đưa vào bằng `-i`, không
   nhét đường dẫn vào chuỗi filter; filter nào buộc phải có tên file thì chạy với `cwd`.
10. Log và comment tiếng Việt; tên hàm/biến tiếng Anh.
11. `pytest -q` + `ruff check src tests` xanh trước khi đề xuất commit. Chỉ commit khi người dùng
    đồng ý. Không commit `.env`, media, `data/`.
12. **Hỏi trước khi cài thư viện mới.**

---

## 4. Quyết định đã chốt

**2026-09-11 — chuyển dự án** (người dùng đồng ý cả 4 điểm):

- Dự án theo `docs/SPEC.md`. Code cũ (cắt highlight stream game) chuyển nguyên vào
  `legacy/stream_editor/` — vẫn chạy được (58 test xanh khi chạy trong thư mục đó), nhưng không
  nằm trong CI và không bảo trì.
- LLM: **Ollama mặc định** (`qwen3:8b`), **Claude là adapter tùy chọn** (`llm.backend: claude`)
  — port từ `legacy/stream_editor/pipeline/claude_api.py` ở Iteration 3.
- Snapshot git: commit `295a69f`.

**Chỗ làm khác SPEC, và lý do:**

1. Import `faster_whisper`/`ollama` bên trong hàm (SPEC §16 import đầu file) — test không cần GPU.
2. Tham số dựng video chỉ nằm trong profile YAML; `.env.example` để các khóa `MEME_*`,
   `MAX_MEMES_PER_MINUTE` dạng comment. Nếu không, `.env` luôn đè profile và `--profile` mất
   tác dụng (mâu thuẫn giữa SPEC §14 và §50).
3. **Không dùng pydantic-settings** (dù đã được đồng ý cài): tên biến SPEC §14 không theo quy
   ước lồng nhau của nó (`MEME_COOLDOWN` → `editing.cooldown`), nên dùng bảng `ENV_MAP` +
   python-dotenv (có sẵn).
4. Bỏ `requests` (dùng `httpx` khi cần), `opencv-python`, `Pillow`, `orjson` — MVP chưa cần;
   ffprobe đọc được kích thước ảnh/GIF.
5. Bỏ `APP_ENV` — không có gì dùng.
6. SPEC §33 và §50 lệch nhau về chaotic (8 hay 9 meme/phút) — theo §50 (9).
7. Thêm `automeme doctor` và `data/logs/` (SPEC không có).
8. `requirements.txt` chỉ chứa `-e .[dev]`; nguồn thật là `pyproject.toml`.
9. Sắp tới: transcript giữ thêm `words` (timestamp theo từ) ngoài `segments` của SPEC §17;
   Ollama dùng structured output (`format=` JSON schema từ pydantic); kiểm tra lại repo và API
   của Meme Search trước Iteration 4, làm `LocalMemeProvider` trước (SPEC §29).

---

## 5. Lộ trình — theo SPEC §80, mỗi iteration duyệt kế hoạch riêng

### Iteration 1 — Transcription (SPEC §15–17, Milestone 1)  ← TIẾP THEO

- `src/automeme/transcription/{base,whisper}.py`: interface `Transcriber` (SPEC §13),
  `FasterWhisperTranscriber` (VAD, `word_timestamps=True`, beam theo config).
- Hàm thuần `normalize_transcript(...)` → schema SPEC §17 (`video, language, duration,
  segments[id,start,end,text]`) + `words[w,start,end]`. Bỏ đoạn rỗng, đảm bảo timestamp tăng dần.
- Nơi lưu và khóa cache: SPEC §17 ghi `data/transcripts/<tên>.json`, §48 ghi
  `cache/<hash>/…` phụ thuộc hash video + model + ngôn ngữ. Chốt một cách trong kế hoạch.
- Nối vào CLI: hàm `bootstrap(profile)` (nạp cấu hình theo profile), lệnh `transcribe`.
- Giải phóng model sau khi xong (để VRAM cho Ollama).
- **Rủi ro số 1:** faster-whisper chạy GPU trên Windows cần thêm cuBLAS + cuDNN 9 cho CUDA 12
  (pip `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` rồi thêm thư mục `bin` vào PATH), không thì
  chạy CPU `int8`. Hỏi trước khi cài.
- Xong khi: `automeme transcribe video.mp4` ra transcript tiếng Việt đúng dấu trên video thật.

### Iteration 2 — Timeline + renderer (SPEC §34–41, §54, Milestone 3)

- `timeline/schema.py` (event tổng quát SPEC §73: `meme`, sau này `sfx`, `zoom`…),
  `timeline/validator.py` (SPEC §54), `rendering/filters.py` (hàm thuần dựng filtergraph),
  `rendering/renderer.py`.
- Overlay 5 vị trí, rộng 30% khung (SPEC §37–38), `enable='between(t,a,b)'`; ảnh tĩnh
  `-loop 1`, GIF lặp (`-ignore_loop 0`) + dời PTS về thời điểm bắt đầu; audio gốc giữ nguyên.
- Lệnh `render <video> --timeline <file>`, `inspect <timeline>`.
- Test: chuỗi filter, validator; tích hợp với video 5 giây sinh bằng lavfi + PNG tự sinh (SPEC §57).
- Xong khi: timeline viết tay chèn đúng PNG/JPG/GIF.

### Iteration 3 — Phân tích bằng LLM (SPEC §18–24, §51–53)

- `analyzer/context.py` (cửa sổ: 2 đoạn trước, 1 đoạn sau — đưa vào config), `analyzer/llm.py`
  (`OllamaLLM`, `ClaudeLLM`), `prompts/meme_detector.txt` (SPEC §21), model `MemeOpportunity`
  (SPEC §24), hàm thuần lọc: ngưỡng confidence, cooldown, mật độ, kẹp thời lượng.
- Cần cài: ứng dụng Ollama + `ollama pull qwen3:8b`, thư viện `ollama` (hỏi trước). qwen3 có
  chế độ "thinking" — tắt khi cần JSON.
- Test: context window, validate, bộ lọc, LLM giả lập trả JSON hỏng → thử lại → bỏ qua.

### Iteration 4 — Tìm meme, xếp hạng, `automeme run` (SPEC §25–33, §43)

- `memes/base.py` (`MemeProvider`), `memes/local.py` (metadata SPEC §26, tìm theo tag/từ khóa),
  `memes/ranker.py` (trọng số SPEC §30 đưa vào config, phạt trùng SPEC §31),
  `timeline/builder.py` (thời điểm SPEC §52: cuối câu + 0.10–0.30 s), `pipeline.py`, lệnh `run`.
- `memes/meme_search.py` (HTTP) sau khi xác minh API thật.
- Xong khi: đạt định nghĩa MVP ở mục 1.

### Sau MVP

Stage F (cache, resume, xử lý lỗi, integration test), Stage G (giao diện duyệt) — SPEC §79.
Code tái dùng được trong `legacy/`: `subtitles.py` (phụ đề karaoke → `CaptionEvent`),
`layout.py` (khung dọc 9:16), `claude_api.py`.

---

## 6. Checklist (SPEC §79)

**Stage A**
- [x] Project structure
- [x] Virtual environment
- [x] Configuration
- [x] Logging
- [x] FFmpeg detection

**Stage B**
- [~] Extract audio — hàm `extract_audio` có và đã test thật, chưa nối vào CLI
- [ ] Whisper model loading
- [ ] Vietnamese transcription
- [ ] Timestamp normalization
- [ ] Save transcript.json

**Stage C**
- [ ] Timeline schema
- [ ] Manual timeline
- [ ] PNG overlay
- [ ] JPG overlay
- [ ] GIF overlay
- [ ] MP4 output

**Stage D**
- [ ] Ollama adapter
- [ ] Prompt manager
- [ ] Context windows
- [ ] Meme opportunity detection
- [ ] JSON validation

**Stage E**
- [ ] Meme Search installation
- [ ] Meme Search adapter
- [ ] Semantic query
- [ ] Top-K retrieval
- [ ] Ranking
- [ ] Duplicate penalty

**Stage F**
- [ ] Complete pipeline
- [ ] Cache
- [ ] Resume
- [ ] Error handling
- [ ] Integration tests

**Stage G**
- [ ] Preview UI
- [ ] Accept/reject meme
- [ ] Replace meme
- [ ] Adjust timestamp
- [ ] Render

---

## 7. Việc người dùng cần tự làm

- Tạo `.env`: `Copy-Item .env.example .env` (chưa bắt buộc — thiếu thì dùng mặc định).
- Chọn license cho code (MIT hoặc Apache-2.0) — chưa có file `LICENSE`.
- Trước Iteration 3: cài Ollama, `ollama pull qwen3:8b`.
- Chuẩn bị 1–2 video tiếng Việt 30–90 giây để chạy thật từ Iteration 1.

---

## 8. Nhật ký tiến độ

> Claude Code: thêm một mục sau mỗi phiên — đã làm gì, quyết định gì, vấn đề còn tồn tại.
> Mới nhất ở trên cùng. Nhật ký giai đoạn stream-auto-editor: `legacy/stream_editor/HANDOFF.md`.

### 2026-09-11 — Chuyển sang automeme + Stage A (Claude Code)

**Đã làm.**
- `git init` + commit snapshot hiện trạng (`295a69f`) trước khi tái cấu trúc.
- Chuyển code cũ vào `legacy/stream_editor/` bằng `git mv`, kể cả HANDOFF cũ. Kiểm tra lại:
  58 test cũ vẫn xanh khi chạy trong thư mục đó.
- File README người dùng gửi → `docs/SPEC.md` (giữ nguyên văn, thêm 1 dòng ghi chú đầu file).
- Dựng khung theo SPEC §12: `pyproject.toml` (lệnh `automeme`, nhóm cài thêm `[asr]`, `[claude]`,
  `[dev]`), `src/automeme/` (cli, config, doctor, media/, utils/), `configs/` (default + 3
  profile), `.env.example`, `.gitignore`, `data/*`, `assets/*`, `prompts/`.
- Cài vào `.venv`: typer 0.27.2 (kéo theo rich 15), ruff 0.16.7, pytest-cov 7.1; automeme ở
  chế độ editable.
- Viết lại README.md, file này, CLAUDE.md, 3 skill, CI (thêm FFmpeg + ruff).
- Theo yêu cầu người dùng: viết `docs/GUIDE.md` — hướng dẫn chi tiết (cài đặt từng bước, bảng
  giải thích `doctor`, cấu hình + profile, quy trình dự kiến, log, xử lý sự cố, làm việc cùng
  Claude Code). Thêm quy tắc giữ GUIDE cập nhật vào CLAUDE.md và skill `/tiep-tuc`.
- Commit: `ed7d5a3` (tái cấu trúc), sau đó một commit riêng cho GUIDE.

**Kết quả.** 73 test xanh, ruff sạch. `automeme doctor` trên máy người dùng: bắt buộc đều đạt;
thiếu `.env`, faster-whisper, Ollama (đúng dự kiến). `automeme --help`,
`python -m automeme …` chạy được; file log ghi đúng tiếng Việt kèm lệnh DEBUG.

**Còn tồn tại.** Chưa có Ollama, faster-whisper, `.env`, `LICENSE`. Repo mới ở máy, chưa có
remote GitHub. `-v` chỉ nhận khi đặt trước tên lệnh (`automeme -v doctor`) — đã ghi trong GUIDE.

**Việc tiếp theo:** Iteration 1 — transcription.
