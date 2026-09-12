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

## 2. Hiện trạng — Stage A–G hoàn thành ở cấp code

### Module

| File | Vai trò | Ghi chú |
|---|---|---|
| `src/automeme/cli.py` | CLI Typer | `doctor`, `install-memes`, `install-gifs`, `transcribe`, `analyze`, `inspect`, `render`, `run` chạy được. `bootstrap(profile)` nạp cấu hình + bật file log cho mọi lệnh thật |
| `src/automeme/pipeline.py` | Nối các bước | `transcribe_video(...)`, `analyze_video(...)`, `build_video_timeline(...)`, `render_timeline(...)`, `run_video(...)`; các backend đều tiêm được để test offline |
| `src/automeme/cache.py` | Cache/invalidation | Manifest strict, hash ổn định, nhận biết fresh/stale/file bị sửa; manifest nằm ngoài artifact người dùng chỉnh |
| `src/automeme/analyzer/context.py` | Context window | `build_context_windows`: mặc định 2 đoạn trước + 1 đoạn sau, cấu hình được |
| `src/automeme/analyzer/schema.py` | Structured output | `MemeTiming`, `MemeOpportunity`, `Analysis`, load/save và tóm tắt; mọi model `extra="forbid"` |
| `src/automeme/analyzer/llm.py` | Adapter LLM | Interface `StructuredLLM`; `OllamaLLM` dùng JSON Schema + `think=False`; `ClaudeLLM` dùng structured output |
| `src/automeme/analyzer/detector.py` | Phân tích + bộ lọc | JSON sai thử lại 1 lần rồi bỏ riêng câu; code quyết định confidence, timing, duration, cooldown, mật độ |
| `src/automeme/analyzer/prompt.py` | Prompt manager | Nạp `prompts/meme_detector.txt`, điền context và JSON Schema, giữ UTF-8 |
| `src/automeme/memes/local.py` | Thư viện local | Đọc `library.jsonl` theo từng dòng, tìm theo metadata/tên file, tự quét media và bỏ asset `safe=false` |
| `src/automeme/memes/popular.py` + `catalog/` | Kho meme phổ biến | Catalog 100 template + ontology Việt–Anh; tải HTTPS có giới hạn/MIME, upsert nguyên tử, ghi nguồn và chặn 3 mục nhạy cảm khỏi auto-select |
| `src/automeme/memes/animated.py` + `catalog/` | Kho GIF động | 30 reaction GIF từ GitHub ghim SHA; kiểm tra allowlist/MIME/kích thước/số frame, nhãn semantic và 2 mục `safe=false` |
| `src/automeme/memes/meme_search.py` | Meme Search API v1 | Vector search qua HTTP, bearer token, fallback local; chỉ tải ứng viên đã chọn vào cache bằng file tạm |
| `src/automeme/memes/ranker.py` | Xếp hạng | Hàm thuần kết hợp semantic, emotion, style, quality, novelty và phạt meme vừa dùng |
| `src/automeme/timeline/builder.py` | Sinh timeline | Xếp hạng top-K, thử ứng viên tiếp theo nếu materialize lỗi, giới hạn thời lượng theo video |
| `src/automeme/review/` | Web UI local | Preview video/meme/transcript; accept/reject/replace/chỉnh timing; API loopback có token; nút render |
| `src/automeme/studio/` | UI/UX đầy đủ | Dashboard, upload nguyên tử, job pipeline nền, editor waveform, transcript, render/download và CRUD metadata kho meme |
| `src/automeme/timeline/schema.py` | Định dạng timeline | pydantic `Timeline`/`MemeEvent` (`extra="forbid"`), `load/save_timeline`, lỗi chỉ rõ "sự kiện #n → khóa" |
| `src/automeme/timeline/validator.py` | Ràng buộc cứng (SPEC §54) | `validate_timeline` → (lỗi chặn render, cảnh báo); `resolve_asset`; `format_timeline_table` cho lệnh inspect |
| `src/automeme/rendering/filters.py` | Dựng filtergraph | `build_render_plan` (hàm thuần) → tham số `-i` + `filter_complex`; `vi_tri_overlay`, `input_cho_meme` |
| `src/automeme/rendering/renderer.py` | Gọi FFmpeg | `build_ffmpeg_cmd` (thuần) + `render` ghi file tạm rồi đổi tên; copy audio gốc, chỉ encode lại khi copy hỏng |
| `src/automeme/workspace.py` | Đường dẫn + khóa cache | `video_fingerprint` (kích thước + 1 MB đầu/cuối), `asr_key`, `slug`, `paths_for` |
| `src/automeme/transcription/base.py` | Interface `Transcriber` | `transcribe(audio) -> dict thô`, `unload()` trả VRAM |
| `src/automeme/transcription/whisper.py` | Backend faster-whisper | Nạp model ở lần dùng đầu; `them_dll_cuda()` (Windows tìm DLL cuDNN/cuBLAS trong site-packages); `giai_thich_loi_model` dịch lỗi CTranslate2 sang tiếng Việt |
| `src/automeme/transcription/normalize.py` | Chuẩn hóa + kiểm tra | `normalize_transcript`, `validate_transcript`, `format_transcript_summary` — hàm thuần |
| `src/automeme/config.py` | Nạp cấu hình | `load_settings(profile, overrides, *, configs_dir, env, root)`; pydantic `extra="forbid"`; `ENV_MAP` ánh xạ tên biến SPEC §14 → khóa |
| `src/automeme/doctor.py` | `automeme doctor` | Python, cấu hình, `.env`, ffmpeg/ffprobe + phiên bản, faster-whisper, GPU (nvidia-smi), Ollama (GET `/api/tags` + có model chưa) hoặc Claude, docker, git, UTF-8 |
| `src/automeme/media/ffmpeg.py` | Chạy lệnh ngoài | `which` (tìm cả `Scripts/` của venv), `require_binary`, `run_cmd` (list args, log DEBUG nguyên lệnh), `CommandError` |
| `src/automeme/media/probe.py` | ffprobe | `probe()` → `MediaInfo` (thời lượng, kích thước, fps, audio, sample rate, kênh, định dạng); `parse_probe` là hàm thuần, bỏ qua ảnh bìa |
| `src/automeme/media/audio.py` | Tách audio | WAV PCM 16-bit mono 16 kHz; bỏ qua nếu đã có; ghi file `.part` rồi đổi tên |
| `src/automeme/utils/files.py` | Đường dẫn, JSON | `PROJECT_ROOT`, `CONFIGS_DIR`, `PROMPTS_DIR`; `write_json` UTF-8, ghi file tạm rồi đổi tên |
| `src/automeme/utils/timestamps.py` | Thời gian | `format_ts(13.2) → "00:13.20"`, `parse_ts` |
| `src/automeme/utils/logger.py` | Log | `setup_logging(level)` (gọi lại được), `add_file_log` → `data/logs/automeme.log` (DEBUG, xoay vòng 5 MB × 3) |

### Luồng dữ liệu (chốt ở Iteration 1)

```
data/input/<video>                              video người dùng chép vào
data/cache/<ten-video>-<hash8>/audio.wav        WAV mono 16 kHz
data/cache/<ten-video>-<hash8>/transcript-<asr8>.json   cache theo tham số ASR
data/cache/meme-search/<id>.<ext>              media đã chọn và tải từ Meme Search
data/cache/manifests/<stage>-<hash>.json       cache key + vân tay output, không chứa token
data/transcripts/<ten-video>.json               bản mới nhất — các bước sau đọc file này
data/analysis/<ten-video>.json                  cơ hội meme đã qua schema + bộ lọc cứng
data/timelines/<ten-video>.timeline.json       bản dựng: meme nào, lúc nào, ở đâu (người sửa được)
data/output/<ten-video>_automeme.mp4           video hoàn chỉnh
```

`hash8` = vân tay video (kích thước + 1 MB đầu + 1 MB cuối); `asr8` = hash của model, ngôn ngữ,
compute_type, beam_size, vad_filter, condition_on_previous_text. Đổi model → file cache mới,
không dùng nhầm bản cũ. `--force` bắt chạy lại.

Schema transcript: `{video, language, duration, model, segments[{id,start,end,text}], words[{w,start,end}]}`.

Schema analysis: `{version, video, backend, model, opportunities[MemeOpportunity]}`; mỗi
`MemeOpportunity` theo SPEC §24. Timing lưu trong file đã được code chuẩn hóa, không dùng thẳng
anchor/delay do LLM đề xuất.

Schema timeline (SPEC §34): `{version, video, events[{id, type:"meme", start, duration, asset,
mode:"overlay", position?, scale?, status, confidence?, query?, reason?}]}`. `status` là
`pending|accepted|rejected`; renderer bỏ qua rejected. Bỏ trống `position`/`scale`
thì lấy `meme.position_default` / `meme.scale_default` trong cấu hình. Đường dẫn `asset` tương
đối được hiểu từ thư mục gốc dự án, rồi thử tiếp từ `assets/`.

### Làm được gì rồi

| Việc | Trạng thái | Đã kiểm chứng thế nào |
|---|---|---|
| `automeme doctor` | Xong | Chạy trên máy người dùng, bắt đúng thứ còn thiếu |
| Cấu hình 4 lớp + 3 profile | Xong | 25 test, có test giữ `.env.example` khớp `ENV_MAP` |
| Log console + file DEBUG | Xong | `data/logs/automeme.log` ghi đúng tiếng Việt, kèm nguyên lệnh FFmpeg |
| Tách audio mono 16 kHz | Xong | Test chạy FFmpeg thật |
| `automeme transcribe` | Xong | Chạy thật trên GPU: model large-v3, 11,7 giây audio hết ~3 giây |
| Cache theo vân tay video + tham số ASR | Xong | Test; chạy lại lần hai bỏ qua nhận dạng |
| Schema + kiểm tra timeline | Xong | 25 test, thông báo lỗi chỉ rõ "sự kiện #n → khóa" |
| `automeme inspect` | Xong | Chạy thật, cảnh báo đúng cooldown và mật độ |
| `automeme render` (ảnh, GIF, vùng trong suốt) | Xong | Chạy thật; trích khung hình kiểm tra meme hiện đúng lúc, đúng góc; giữ nguyên tiếng gốc |
| `automeme analyze` (Ollama/Claude) | Xong | 18 test mới chạy offline: schema, context, retry, bộ lọc, resume, CLI và adapter |
| Thư viện local + Meme Search API v1 | Xong | Test metadata hỏng từng dòng, safe filter, tìm local, request vector, token, cache và các chặn bảo mật |
| Catalog 100 meme phổ biến có nhãn | Xong | Đã tải thật 100/100; test catalog, tải/tái sử dụng, nhãn song ngữ, safe filter, CLI và Studio API |
| Catalog 30 reaction GIF có nhãn | Xong | Đã tải thật 30/30; mọi file 7–293 frame, test parser GIF, URL ghim SHA, semantic search, CLI và Studio API |
| Xếp hạng + dựng timeline | Xong | Test trọng số, novelty/phạt trùng, fallback ứng viên và giới hạn cuối video |
| `automeme run` | Xong | Test toàn luồng với backend AI giả và FFmpeg thật: video → transcript → analysis → timeline → MP4 |
| Cache/invalidation toàn pipeline | Xong | Analysis, timeline và render có input key riêng; đổi config làm mới đúng bước, timeline/output sửa ngoài được bảo vệ |
| `automeme review` | Xong | Test service + HTTP server thật: auth, media Range, chỉnh timeline và render callback |
| `automeme studio` | Xong | Edge headless mở UI thật; test dashboard/upload/job/library/auth; frontend OSS vendoring chạy offline |

### Chưa làm được

| Việc | Vì sao / khi nào |
|---|---|
| Chất lượng nhận dạng **tiếng Việt** | Chưa có video tiếng Việt thật để đo. Windows của người dùng không có giọng đọc tiếng Việt nên mẫu thử phải dùng giọng tiếng Anh |
| Tốc độ trên video dài (vài phút trở lên) | Mới thử video 11,7 giây |
| Đường chạy CPU (`WHISPER_DEVICE=cpu`) | Chưa thử; máy có GPU nên mặc định chạy GPU |
| Chạy `automeme analyze` với model thật | Máy chưa cài ứng dụng Ollama/model `qwen3:8b`; code và SDK Python đã sẵn sàng |
| Chạy trọn pipeline với Ollama + Meme Search thật | Máy chưa có ứng dụng/model Ollama và dịch vụ Meme Search chưa được khởi chạy; local provider vẫn dùng được |
| Quyền sử dụng media trong kho local | Đã cài 100 template UGC có nguồn/cảnh báo; người dùng vẫn phải tự xác minh quyền trước khi xuất bản, nhất là thương mại |
| Mode `cutaway`, sự kiện `sfx`/`zoom`/caption | SPEC §36, §71–73 — để sau MVP |
| File `LICENSE` | Người dùng chưa chọn MIT hay Apache-2.0; repo đang public nên cần sớm |

### Cấu hình

`configs/default.yaml` (đủ mọi khóa) → `configs/<profile>.yaml` → biến môi trường/`.env` →
cờ CLI. Tên biến môi trường theo SPEC §14, danh sách đầy đủ trong `config.ENV_MAP`. Biến rỗng
= không ghi đè. Có test giữ `.env.example` và `ENV_MAP` luôn khớp nhau.

### Test

`pytest -q` — **252 test**, chạy không cần GPU, Ollama, faster-whisper, API key hay mạng. Các test cần FFmpeg (tách audio,
render thật, kiểm tra meme hiện đúng lúc bằng cách so khung hình) tự bỏ qua nếu máy không có
FFmpeg; CI có cài nên chạy cả chúng. CI (GitHub Actions) chạy `ruff check src tests` + `pytest -q` mỗi lần push lên
https://github.com/TrungVuManh/Automatic-Video-Editer (remote `origin`, nhánh `main`).

### Máy người dùng (đo 2026-09-11)

- Windows 11. Python trên PATH là bản *embeddable* 3.13 (không có venv) → dự án dùng `.venv`
  dựng từ Python 3.11.9. **Venv không được kích hoạt sẵn**: gọi qua `.venv\Scripts\...`.
- FFmpeg 9.0.1 (winget), GPU RTX 4060 Laptop **8 GB VRAM**, Docker, gh, git.
- **Đã có SDK Python:** `ollama==0.6.2`, `anthropic==1.4.0`. **Chưa có:** ứng dụng Ollama/model, file `.env`.
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
4. Bỏ `requests`, `opencv-python`, `Pillow`, `orjson`; dùng `httpx` trực tiếp cho Meme Search.
   ffprobe đọc được kích thước ảnh/GIF.
5. Bỏ `APP_ENV` — không có gì dùng.
6. SPEC §33 và §50 lệch nhau về chaotic (8 hay 9 meme/phút) — theo §50 (9).
7. Thêm `automeme doctor` và `data/logs/` (SPEC không có).
8. `requirements.txt` chỉ chứa `-e .[dev]`; nguồn thật là `pyproject.toml`.
9. **2026-09-12 — Iteration 4:** API Meme Search v1 đã được kiểm tra theo tài liệu chính thức:
   `GET /api/v1/search`, `mode=vector`, `limit` tối đa 20, bearer token cần `search:read` và
   `media:read` để lấy `content_url`. Dịch vụ chỉ nên chạy loopback. Adapter chỉ ánh xạ trường
   cần dùng, bỏ qua trường mới, chặn redirect/cross-origin và giới hạn dung lượng tải.
10. **2026-09-12 — Iteration 3:** Ollama nhận `MemeOpportunity.model_json_schema()` qua
    `format`, `temperature=0`, `think=False`; Claude nhận schema đã transform qua
    `output_config.format`. JSON vẫn được pydantic kiểm tra lại. Timing cuối câu, duration,
    confidence, cooldown và mật độ do code quyết định. Mục 9 đã được kiểm tra cho Ollama.
11. **2026-09-12 — Stage F:** manifest cache nằm ở `data/cache/manifests/`, không đổi schema
    public. Analysis key phụ thuộc video/transcript/prompt/LLM/bộ lọc; timeline key phụ thuộc
    analysis/provider/thư viện/ranking; render key phụ thuộc video/timeline/assets/codec. Timeline
    hoặc output bị sửa ngoài automeme được giữ lại, chỉ `--force` mới ghi đè.

**2026-09-12 — Iteration 2:**

- Mỗi meme là một input `-i` riêng, đường dẫn **không** nằm trong chuỗi filter → không phải
  escape `:` và `\` trên Windows.
- Ảnh tĩnh dùng `-loop 1`, GIF dùng `-ignore_loop 0`, video meme dùng `-stream_loop -1`; tất cả
  kèm `-t <thời lượng>`. `setpts=PTS-STARTPTS+start/TB` để GIF chạy từ khung đầu đúng lúc meme hiện.
- `overlay=...:enable='between(t,a,b)':eof_action=pass` — `eof_action=pass` để video chính không
  bị cắt ngắn khi meme hết.
- Vị trí dùng biểu thức W/H/w/h của FFmpeg nên không cần biết trước cỡ meme sau khi scale.
- Audio: copy nguyên bản; chỉ khi copy lỗi mới encode lại theo `output.audio_codec` (SPEC §61).
- Validator phân biệt **lỗi** (chặn render: thiếu file, vượt thời lượng video, trùng mã, hai meme
  cùng vị trí trùng giờ) và **cảnh báo** (cooldown, mật độ, thời lượng ngoài khoảng) — timeline
  viết tay là quyền của người dùng, không chặn.
- Thêm `meme.scale_default`, `meme.position_default`, `meme.margin_ratio` vào `configs/`.

**2026-09-12 — Iteration 1** (người dùng đồng ý cả 4 điểm):

- Cài `faster-whisper` kèm CUDA (`[asr-cuda]` = faster-whisper + nvidia-cublas-cu12 +
  nvidia-cudnn-cu12). Không cần CUDA Toolkit, không cần PyTorch.
- Cache: `data/cache/<ten>-<hash8>/` + bản chính thức `data/transcripts/<ten>.json`.
- Model mặc định `large-v3` (không dùng `large-v3-turbo`).
- Transcript có thêm `words` và `model` so với SPEC §17.
- Thêm hai khóa cấu hình SPEC không có: `whisper.vad_filter` (mặc định `true`) và
  `whisper.condition_on_previous_text` (mặc định **`false`** — mặc định của Whisper là `true`
  nhưng hay làm model lặp một câu mãi ở đoạn nhạc/im lặng).
- `them_dll_cuda()` trong `transcription/whisper.py`: trên Windows, DLL cuDNN/cuBLAS do pip cài
  nằm trong `site-packages/nvidia/*/bin`, không có trong PATH nên CTranslate2 không tự thấy.
  Không có hàm này thì lỗi `Could not locate cudnn_ops64_9.dll`.

---

## 5. Lộ trình — theo SPEC §80, mỗi iteration duyệt kế hoạch riêng

### Iteration 1 — Transcription (SPEC §15–17, Milestone 1)  ✅ XONG 2026-09-12

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

### Iteration 2 — Timeline + renderer (SPEC §34–41, §54, Milestone 3)  ✅ XONG 2026-09-12

- `timeline/schema.py` (event tổng quát SPEC §73: `meme`, sau này `sfx`, `zoom`…),
  `timeline/validator.py` (SPEC §54), `rendering/filters.py` (hàm thuần dựng filtergraph),
  `rendering/renderer.py`.
- Overlay 5 vị trí, rộng 30% khung (SPEC §37–38), `enable='between(t,a,b)'`; ảnh tĩnh
  `-loop 1`, GIF lặp (`-ignore_loop 0`) + dời PTS về thời điểm bắt đầu; audio gốc giữ nguyên.
- Lệnh `render <video> --timeline <file>`, `inspect <timeline>`.
- Test: chuỗi filter, validator; tích hợp với video 5 giây sinh bằng lavfi + PNG tự sinh (SPEC §57).
- Xong khi: timeline viết tay chèn đúng PNG/JPG/GIF.

### Iteration 3 — Phân tích bằng LLM (SPEC §18–24, §51–53)  ✅ XONG 2026-09-12

- `analyzer/context.py` (cửa sổ: 2 đoạn trước, 1 đoạn sau — đưa vào config), `analyzer/llm.py`
  (`OllamaLLM`, `ClaudeLLM`), `prompts/meme_detector.txt` (SPEC §21), model `MemeOpportunity`
  (SPEC §24), hàm thuần lọc: ngưỡng confidence, cooldown, mật độ, kẹp thời lượng.
- Cần cài: ứng dụng Ollama + `ollama pull qwen3:8b`, thư viện `ollama` (hỏi trước). qwen3 có
  chế độ "thinking" — tắt khi cần JSON.
- Test: context window, validate, bộ lọc, LLM giả lập trả JSON hỏng → thử lại → bỏ qua.

- Đã triển khai đủ các mục trên. Output chính thức: `data/analysis/<slug>.json`; SDK Ollama là
  extra `[llm]`. Chưa smoke test model thật vì máy chưa cài ứng dụng Ollama/qwen3:8b.

### Iteration 4 — Tìm meme, xếp hạng, `automeme run` (SPEC §25–33, §43)  ✅ XONG 2026-09-12

- `memes/base.py` (`MemeProvider`), `memes/local.py` (metadata SPEC §26, tìm theo tag/từ khóa),
  `memes/ranker.py` (trọng số SPEC §30 đưa vào config, phạt trùng SPEC §31),
  `timeline/builder.py` (thời điểm SPEC §52: cuối câu + 0.10–0.30 s), `pipeline.py`, lệnh `run`.
- `memes/meme_search.py` dùng API v1 đã xác minh; local-first khi không có token và tự fallback
  local khi dịch vụ lỗi. Media từ API chỉ tải sau khi ứng viên được chọn.
- Đã đạt định nghĩa MVP ở cấp code và integration test; còn cần smoke-test chất lượng với video
  tiếng Việt, Ollama và kho meme thật của người dùng.

### Stage F — Cache, resume và hardening  ✅ XONG 2026-09-12

- Manifest cache strict, ghi nguyên tử; tự vô hiệu từng bước theo đúng đầu vào.
- Giữ timeline người dùng chỉnh, không tự ghi đè output không còn khớp fingerprint.
- Test đổi video/cấu hình/ranking/timeline, manifest hỏng và pipeline FFmpeg thật.

### Stage G — Giao diện duyệt  ✅ XONG 2026-09-12

- `automeme review <video>` mở web UI loopback, không cần framework/dependency mới.
- Preview video + meme + transcript; accept/reject có thể hoàn tác; thay asset local; chỉnh
  start/duration/position/scale; render trực tiếp.
- API POST yêu cầu token phiên, không có CORS; media hỗ trợ Range để tua video.

### AutoMeme Studio — UI/UX đầy đủ  ✅ XONG 2026-09-12

- `automeme studio` mở app shell responsive gồm Tổng quan, Tạo video, Biên tập, Kho meme và
  Thiết lập; vẫn giữ lệnh `review` cho luồng duyệt nhanh.
- Upload video/meme ghi `.part` rồi đổi tên, chặn traversal/đuôi/dung lượng; pipeline chạy nền
  một job GPU, báo tiến độ bốn stage và tận dụng cache hiện có.
- Editor dùng Plyr + WaveSurfer Regions/Timeline; kho meme quản lý metadata strict. FilePond,
  SortableJS và Lucide hoàn thiện upload, kéo-thả và icon. Toàn bộ vendor chạy offline.
- Phiên bản/license nằm trong `THIRD_PARTY_NOTICES.md`; toàn văn license được đóng vào package.

### Tiếp theo

Chạy nghiệm thu bằng video tiếng Việt, Ollama và kho meme thật; kiểm tra thêm media meme dạng
video. Sau đó mới mở rộng cutaway/SFX/caption hoặc scene understanding nếu cần.
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
- [x] Extract audio
- [x] Whisper model loading
- [~] Vietnamese transcription — pipeline chạy thật trên GPU với giọng tiếng Anh (Windows không
      có giọng đọc tiếng Việt để tự sinh mẫu); **còn chờ video tiếng Việt thật của người dùng**
- [x] Timestamp normalization
- [x] Save transcript.json

**Stage C**
- [x] Timeline schema
- [x] Manual timeline
- [x] PNG overlay (cả vùng trong suốt)
- [x] JPG overlay (chung nhánh với PNG)
- [x] GIF overlay
- [x] MP4 output

**Stage D**
- [x] Ollama adapter
- [x] Prompt manager
- [x] Context windows
- [x] Meme opportunity detection
- [x] JSON validation

**Stage E**
- [~] Meme Search installation — Docker có sẵn, dịch vụ chưa được clone/chạy trên máy
- [x] Meme Search adapter
- [x] Semantic query
- [x] Top-K retrieval
- [x] Ranking
- [x] Duplicate penalty

**Stage F**
- [x] Complete pipeline
- [x] Cache
- [x] Resume
- [x] Error handling
- [x] Integration tests

**Stage G**
- [x] Preview UI
- [x] Accept/reject meme
- [x] Replace meme
- [x] Adjust timestamp
- [x] Render

**Studio UI/UX**
- [x] Dashboard dự án và môi trường
- [x] Kéo-thả video + tiến trình pipeline
- [x] Editor video/waveform/transcript
- [x] Quản lý kho meme và metadata
- [x] Cài catalog 100 meme có taxonomy Việt–Anh và safe filter
- [x] Cài catalog 30 reaction GIF động, xác minh frame và ưu tiên bằng style `animated`
- [x] Vendor OSS offline + third-party notices

---

## 7. Việc người dùng cần tự làm

- Tạo `.env`: `Copy-Item .env.example .env` (chưa bắt buộc — thiếu thì dùng mặc định).
- Chọn license cho code (MIT hoặc Apache-2.0) — chưa có file `LICENSE`.
- Để chạy `analyze` thật: cài Ollama, mở server, rồi `ollama pull qwen3:8b`.
- Chuẩn bị 1–2 video tiếng Việt 30–90 giây để chạy thật từ Iteration 1.
- Rà soát quyền sử dụng của template đã cài trước khi xuất bản; thêm asset riêng có quyền nếu cần.
- Nếu muốn semantic search: clone/chạy Meme Search trên loopback và tạo token có scope
  `search:read,media:read`; nếu không, pipeline tự dùng thư viện local.

---

## 8. Nhật ký tiến độ

> Claude Code: thêm một mục sau mỗi phiên — đã làm gì, quyết định gì, vấn đề còn tồn tại.
> Mới nhất ở trên cùng. Nhật ký giai đoạn stream-auto-editor: `legacy/stream_editor/HANDOFF.md`.

### 2026-09-12 (phiên 9) — Kho reaction GIF động (Codex)

**Đã làm.** Thêm `automeme install-gifs`, nút **Cài 30 GIF động** trong Studio và catalog 30
reaction GIF: cười, vỗ tay, ăn mừng, bối rối, nhún vai, chờ đợi, cảm ơn, phản đối, gõ phím…
Metadata dùng chung ontology Việt–Anh; prompt đặt style `animated` khi chuyển động làm phản ứng
rõ hơn, nên ranker có thể ưu tiên GIF thay cho ảnh tĩnh.

**Nguồn và an toàn.** URL raw GitHub được ghim SHA của `cheesits456/ReactionPics` và
`snipe/animated-gifs`; downloader chỉ nhận đúng host/repo/revision allowlist, MIME GIF, tối đa
15 MB, file nguyên tử và ít nhất hai frame. Hai asset có chữ thô tục/nhân vật chính trị đặt
`safe=false`. Source URL cùng trạng thái giấy phép được lưu trên từng item.

**Kiểm chứng.** Đã tải thật 30/30 (~27 MB), tổng 1.366 frame, mỗi file 7–293 frame; xem contact
sheet thủ công. Test bao phủ catalog, parser, tải/tái sử dụng, tìm semantic, CLI và Studio;
toàn bộ **252 test** và lint/frontend checks đều xanh.

### 2026-09-12 (phiên 8) — Kho 100 meme có nhãn ngữ nghĩa (Codex)

**Đã làm.** Thêm catalog cố định 100 template phổ biến và lệnh `automeme install-memes`; Studio
có nút cài trực tiếp. Mỗi mục có nhãn taxonomy Việt–Anh, alias, mô tả ngữ cảnh, emotion/style,
intensity và quality để local search + ranker chọn theo ý nghĩa thay vì phụ thuộc tên file.
Prompt LLM dùng cùng taxonomy để tạo query tương thích.

**An toàn và nguồn.** Chỉ tải HTTPS từ `i.imgflip.com`, không theo redirect, giới hạn 15 MB,
kiểm tra MIME và đổi tên file `.part` nguyên tử. Metadata giữ URL nguồn cùng cảnh báo UGC;
3 template nhạy cảm đặt `safe=false`. Media tải thật nằm trong `assets/` bị gitignore.

**Kiểm chứng.** Đã cài thật 100/100 (~12 MB), chạy lại tái sử dụng đủ 100 file. Test bao phủ
catalog, năm truy vấn ngữ nghĩa Việt–Anh, safe filter, tải giả lập, CLI, API/UI Studio; Ruff,
Node syntax và toàn bộ **244 test** đều xanh.

### 2026-09-12 (phiên 7) — AutoMeme Studio UI/UX (Codex)

**Đã làm.** Thêm lệnh `automeme studio` và giao diện responsive đầy đủ cho người không muốn
dùng CLI: dashboard, upload video, chọn profile, tiến trình pipeline, editor waveform +
transcript, render/download và kho meme có metadata editor. `run_video` có callback tiến độ
không phá API cũ.

**Mã nguồn mở.** Vendor offline Plyr 3.8.4 (MIT), WaveSurfer.js 7.12.12 (BSD-3-Clause),
SortableJS 1.15.7 (MIT), Lucide 1.45.0 (ISC), FilePond 4.32.12 (MIT). Node chỉ là build-time;
Python runtime không thêm dependency. Có script build, lockfile, notices và toàn văn license.

**An toàn và kiểm chứng.** Studio chỉ bind loopback, token + cookie SameSite, CSP, media Range;
upload atomic, giới hạn loại/dung lượng và không ghi đè. Ruff sạch, **237 test** xanh, npm audit
0 lỗ hổng; Edge headless 1440×1000 tải dashboard thật với project smoke-test và asset local.

### 2026-09-12 (phiên 6) — Stage G: review UI local (Codex)

**Đã làm.** Thêm `automeme review`, studio web responsive để phát video kèm overlay preview,
đọc transcript, accept/reject, thay asset, chỉnh timing/vị trí/tỉ lệ và render. Timeline có trường
`status`; event rejected được giữ để hoàn tác nhưng không validate asset hay đưa vào renderer.

**Quyết định.** Dùng HTTP server thư viện chuẩn, không thêm dependency. Chỉ bind `127.0.0.1`;
POST cần token ngẫu nhiên của phiên, CSP chặt, không CORS. Asset thay thế phải thuộc thư viện;
media endpoint hỗ trợ byte range để video tua được.

**Đã kiểm chứng.** 210 → **222 test**; test service, auth HTTP, Range, chỉnh/lưu timeline,
render callback, CLI, logic bỏ event rejected và render meme video MP4 thật đều xanh.
`automeme review --help` đúng; Edge headless mở UI thật trên smoke-test, server trả 2 event/1
asset. Request media bị trình duyệt hủy khi tua/đóng tab được xử lý im lặng, không in traceback.
Root `automeme --help` cũng có regression test với console CP1252 để không vỡ tiếng Việt.

**Còn tồn tại.** Cần nghiệm thu UX trên trình duyệt thật cùng video tiếng Việt/kho meme thật;
máy vẫn chưa có Ollama server/model.

### 2026-09-12 (phiên 5) — Stage F: cache/invalidation toàn pipeline (Codex)

**Đã làm.** Thêm `cache.py` và manifest nội bộ cho analysis, timeline, render. Cache key bao phủ
đầu vào và cấu hình thật sự ảnh hưởng từng bước; video cùng tên nhưng đổi nội dung không còn lặng
lẽ dùng analysis cũ. Timeline chỉnh tay và output bị sửa ngoài automeme được nhận biết, giữ nguyên.

**Quyết định.** Manifest nằm tập trung trong `data/cache/manifests/` thay vì sidecar cạnh output;
chỉ lưu hash, tuyệt đối không lưu token Meme Search. Artifact do automeme tạo và chưa bị sửa sẽ
tự làm mới khi stale; artifact người dùng đụng vào cần `--force` để ghi đè.

**Đã kiểm chứng.** 200 → **210 test**; test cache thuần, invalidation theo config/video/ranking,
bảo vệ timeline/output chỉnh tay và render FFmpeg thật đều xanh. Ruff và `git diff --check` sạch.

**Việc tiếp theo:** Stage G — giao diện duyệt timeline.

### 2026-09-12 (phiên 4) — Iteration 4: tìm meme, xếp hạng và pipeline MVP (Codex)

**Đã làm.** Thêm interface/provider local, adapter Meme Search API v1 có fallback, schema metadata,
hàm xếp hạng có phạt trùng, timeline builder và lệnh `automeme run`. Thêm cấu hình trọng số,
`MEME_LIBRARY_FILE`, giới hạn tải, metadata mẫu và dependency `httpx`. 178 → **200 test**.

**Quyết định.** Local provider luôn dùng được và là fallback khi API lỗi. API search dùng vector,
top-K tối đa 20; chỉ ứng viên thắng mới được tải. URL media phải cùng origin, redirect bị chặn,
dung lượng có trần và cache được ghi `.part` rồi đổi tên. Response API được ánh xạ qua các trường
ổn định để server thêm field không làm vỡ client.

**Đã kiểm chứng.** Toàn bộ test và Ruff sạch. Integration test chạy FFmpeg thật với video sinh
tại chỗ, backend ASR/LLM/provider giả, rồi kiểm tra pipeline tạo transcript, analysis, timeline và
MP4. Local provider tìm được asset `soc.png` trong workspace.

**Còn tồn tại.** Chưa chạy Ollama/Meme Search thật vì máy chưa có server/model tương ứng; chưa có
video tiếng Việt và kho meme đủ lớn để đánh giá chất lượng. Bước tiếp theo là chạy smoke-test thật,
sau đó hoàn thiện cache invalidation Stage F.

### 2026-09-12 (phiên 3) — Iteration 3: LLM meme detector (Codex)

**Đã làm.** Thêm `analyzer/`: context window, schema pydantic, prompt manager, interface LLM,
adapter Ollama/Claude và bộ lọc cứng. Hoàn thiện `analyze_video` + lệnh `automeme analyze`,
output `data/analysis/<slug>.json`, `--profile`, `--force`; cài extra `[llm]` với
`ollama==0.6.2`. 160 → **178 test**.

**Quyết định.** Gọi từng context bằng JSON Schema; JSON sai thử lại đúng một lần rồi bỏ riêng
câu. LLM chỉ đề xuất ngữ nghĩa. Code lấy `segment.end + analyzer.timing_delay`, kẹp duration,
lọc threshold/cooldown/mật độ và bỏ cơ hội không còn đủ thời gian trước cuối video. Ưu tiên
confidence cao khi hai cơ hội xung đột.

**Đã kiểm chứng.** `178 passed`; Ruff sạch; chữ ký `ollama.Client.chat` bản 0.6.2 có đủ
`format` và `think`. Test adapter giả lập kiểm tra schema được gửi đúng, không cần mạng/API key.

**Còn tồn tại.** Máy chưa có ứng dụng Ollama và model `qwen3:8b`, nên chưa chạy model thật.
Video smoke-test hiện có là tiếng Anh. Cần cài/mở Ollama rồi chạy `/chay-that` để đánh giá chất
lượng prompt tiếng Việt.

**Việc tiếp theo:** Iteration 4 — thư viện meme local, tìm kiếm/xếp hạng, dựng timeline và
`automeme run`.

### 2026-09-12 (phiên 2) — Iteration 2: timeline + render meme (Claude Code)

**Đã làm.** `timeline/` (schema pydantic + validator ràng buộc cứng), `rendering/` (dựng
filtergraph thuần + lớp gọi FFmpeg), `render_timeline` trong pipeline, hai lệnh `inspect` và
`render`, ba khóa cấu hình mới cho meme. 114 → **160 test**.

**Đã chạy thật.** Viết tay `data/timelines/smoke-test.timeline.json` (2 meme) rồi:

```powershell
automeme inspect data\timelines\smoke-test.timeline.json --video data\input\smoke-test.mp4
automeme render data\input\smoke-test.mp4
```

`inspect` in bảng và cảnh báo đúng (cách nhau 3,5s < cooldown 7s; 10,3 meme/phút > 5). Video ra
giữ nguyên 11,68 giây, 640×360, còn audio. Trích khung hình kiểm tra bằng mắt: 3,6s có meme góc
dưới phải, 8,6s có meme góc trên trái, 6,0s không có meme — đúng như timeline. Vùng trong suốt
của PNG hiển thị đúng (thử với ảnh nền trong suốt).

**Còn tồn tại.** Chưa làm mode `cutaway` (SPEC §36) và sự kiện `sfx`/`zoom` (SPEC §71–73) —
để sau MVP. Chưa thử meme là video (.webm/.mp4): code có nhánh `-stream_loop` nhưng chưa chạy thật.

**Việc tiếp theo:** Iteration 3 — Ollama tìm khoảnh khắc nên chèn meme.

### 2026-09-12 — Iteration 1: lệnh `transcribe` (Claude Code)

**Đã làm.** `transcription/` (interface `Transcriber`, backend faster-whisper, chuẩn hóa +
kiểm tra transcript), `workspace.py` (vân tay video, khóa ASR, đường dẫn), `pipeline.py`
(`transcribe_video`), `bootstrap()` + lệnh `transcribe` trong CLI, hai khóa cấu hình whisper
mới, dòng `CTranslate2 CUDA` trong `doctor`, cập nhật README + GUIDE. 73 → **114 test**.

**Đã chạy thật trên GPU.** Máy Windows không có giọng đọc tiếng Việt nên tôi tạo video mẫu
11,7 giây bằng giọng đọc tiếng Anh của Windows (SAPI) rồi chạy:

```powershell
$env:WHISPER_LANGUAGE="en"; automeme -v transcribe data\input\smoke-test.mp4
```

Kết quả: tải model large-v3 và nạp lên GPU mất ~42 giây (lần đầu), nhận dạng 11,7 giây audio
hết ~3 giây, ra 2 đoạn / 25 từ, chữ đúng với câu đã đọc. `them_dll_cuda()` chạy đúng (log DEBUG
cho thấy ba thư mục DLL được thêm). **Chưa kiểm chứng chất lượng tiếng Việt** — cần video thật
của người dùng.

**Còn tồn tại.** Chưa đo tốc độ trên video dài; chưa biết chất lượng tiếng Việt; chưa thử
đường CPU (`WHISPER_DEVICE=cpu`).

**Việc tiếp theo:** Iteration 2 — timeline + renderer overlay.

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

- 2026-09-12: gắn remote `origin` = https://github.com/TrungVuManh/Automatic-Video-Editer
  (repo **public**, trước đó trống), push `main`. CI lần đầu trên Linux: ruff sạch, 73 test
  xanh (kể cả test FFmpeg thật). Cảnh báo phụ: `actions/checkout@v4`, `setup-python@v5` dùng
  Node 20 đã lỗi thời — nâng lên bản mới khi tiện.

**Còn tồn tại.** Chưa có Ollama, faster-whisper, `.env`. **Chưa có `LICENSE`** — repo đã
public nên việc này giờ gấp hơn. `-v` chỉ nhận khi đặt trước tên lệnh (`automeme -v doctor`)
— đã ghi trong GUIDE.

**Việc tiếp theo:** Iteration 1 — transcription.
