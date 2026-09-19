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
| `src/automeme/cli.py` | CLI Typer | Có thêm `install-sfx`; các lệnh doctor/install/transcribe/analyze/inspect/render/run/studio chạy được |
| `src/automeme/pipeline.py` | Nối các bước | `transcribe_video(...)`, `analyze_video(...)`, `build_video_timeline(...)`, `render_timeline(...)`, `run_video(...)`; các backend đều tiêm được để test offline |
| `src/automeme/cache.py` | Cache/invalidation | Manifest strict, hash ổn định, nhận biết fresh/stale/file bị sửa; manifest nằm ngoài artifact người dùng chỉnh |
| `src/automeme/analyzer/context.py` | Context window | `build_context_windows`: mặc định 2 đoạn trước + 1 đoạn sau, cấu hình được; `split_long_segments` tách đoạn Whisper dài theo khoảng lặng giữa các từ (hàm thuần, không sửa transcript) |
| `src/automeme/analyzer/schema.py` | Structured output | `MemeTiming`, `MemeOpportunity`, `Analysis`, load/save và tóm tắt; mọi model `extra="forbid"`; `insert_meme=false` thì `timing.duration` ngoài khoảng được kẹp lại thay vì loại cả câu trả lời |
| `src/automeme/analyzer/llm.py` | Adapter LLM | Interface `StructuredLLM`; `OllamaLLM` dùng JSON Schema + `think=False`; `ClaudeLLM` dùng structured output |
| `src/automeme/analyzer/detector.py` | Phân tích + bộ lọc | JSON sai thử lại 1 lần rồi bỏ riêng câu; code quyết định confidence, timing, duration, cooldown, mật độ |
| `src/automeme/analyzer/prompt.py` | Prompt manager | Nạp `prompts/meme_detector.txt`, điền context và JSON Schema, giữ UTF-8 |
| `src/automeme/memes/local.py` | Thư viện local | Đọc `library.jsonl` theo từng dòng, tìm theo metadata/tên file, tự quét media và bỏ asset `safe=false` |
| `src/automeme/memes/popular.py` + `catalog/` | Kho meme phổ biến | Catalog 100 template + ontology Việt–Anh; tải HTTPS có giới hạn/MIME, upsert nguyên tử, ghi nguồn và chặn 3 mục nhạy cảm khỏi auto-select |
| `src/automeme/memes/animated.py` + `catalog/` | Kho GIF động | 30 reaction GIF từ GitHub ghim SHA; kiểm tra allowlist/MIME/kích thước/số frame, nhãn semantic và 2 mục `safe=false` |
| `src/automeme/sfx/` + `catalog/` | Kho SFX CC0 | 30 âm Kenney có nhãn Việt–Anh; downloader ghim SHA/allowlist, kiểm tra MIME/kích thước/OggS, provider local tìm semantic |
| `src/automeme/memes/meme_search.py` | Meme Search API v1 | Vector search qua HTTP, bearer token, fallback local; chỉ tải ứng viên đã chọn vào cache bằng file tạm |
| `src/automeme/memes/matching.py` | So khớp tìm kiếm | `match_score(query, fields)`: giữ dấu tiếng Việt, khớp cụm âm tiết (quy hoạch động), âm tiết lẻ 0,5 điểm; dùng cho meme local, ranker và SFX |
| `src/automeme/memes/ranker.py` | Xếp hạng | Hàm thuần kết hợp semantic, emotion, style, quality, novelty và phạt meme vừa dùng |
| `src/automeme/timeline/builder.py` | Sinh timeline | Xếp hạng top-K, thử ứng viên tiếp theo nếu materialize lỗi, giới hạn thời lượng theo video; `pick_cutaways` (cú cắt tràn màn hình), `prefer_animated`, `punch_zoom`, SFX chống lặp + truy vấn dự phòng cho cú cắt, loại `exclude_styles`, luân phiên `position_cycle` |
| `src/automeme/review/` | Web UI local | Preview video/meme/transcript; accept/reject/replace/chỉnh timing, chế độ góc/tràn màn hình, độ phóng zoom; API loopback có token; nút render. `service.py` là lõi chung với Studio: `EventPatch` (thêm `mode`, `factor`), `rank_suggestions`, `ReviewSession.suggestions/add_meme/asset_file`, `new_event_id` |
| `src/automeme/studio/` | UI/UX đầy đủ | Dashboard, upload nguyên tử, job pipeline nền, editor waveform, transcript, render/download và CRUD metadata kho meme; editor có công tắc góc/tràn màn hình, lưới gợi ý meme (`/api/suggestions`), chèn meme tại playhead (`/api/events/add`), chỉnh zoom, xem trước khớp render |
| `src/automeme/timeline/schema.py` | Định dạng timeline | Union phân biệt theo `type` (`meme` mặc định/`sfx`/`zoom`), `extra="forbid"`, tương thích timeline meme cũ; `MemeEvent.mode` = `overlay`/`cutaway`; `ZoomEvent` không có asset (`has_asset`) |
| `src/automeme/timeline/validator.py` | Ràng buộc cứng (SPEC §54) | `validate_timeline` → (lỗi chặn render, cảnh báo); `resolve_asset`; `format_timeline_table` cho lệnh inspect; meme trùng giờ với cú cắt tràn màn hình và hai zoom trùng giờ là lỗi |
| `src/automeme/rendering/filters.py` | Dựng filtergraph | `build_render_plan` (hàm thuần) → tham số `-i` + `filter_complex`; `vi_tri_overlay`, `input_cho_meme`; `cutaway_chain` (nền mờ + meme 92% + phóng nhẹ + mờ dần), `zoom_expr`, `duck_expr` (giảm tiếng gốc), `alimiter`; `CutawayStyle` lấy từ `configs/` |
| `src/automeme/rendering/renderer.py` | Gọi FFmpeg | Overlay hình/GIF/video và delay + mix SFX; audio gốc chỉ encode lại khi cần lọc/mix |
| `src/automeme/workspace.py` | Đường dẫn + khóa cache | `video_fingerprint` (kích thước + 1 MB đầu/cuối), `asr_key`, `slug`, `paths_for` |
| `src/automeme/transcription/base.py` | Interface `Transcriber` | `transcribe(audio) -> dict thô`, `unload()` trả VRAM |
| `src/automeme/transcription/whisper.py` | Backend faster-whisper | Nạp model ở lần dùng đầu; `them_dll_cuda()` (Windows tìm DLL cuDNN/cuBLAS trong site-packages); `giai_thich_loi_model` dịch lỗi CTranslate2 sang tiếng Việt |
| `src/automeme/transcription/normalize.py` | Chuẩn hóa + kiểm tra | `normalize_transcript`, `validate_transcript`, `format_transcript_summary` — hàm thuần |
| `src/automeme/config.py` | Nạp cấu hình | `load_settings(profile, overrides, *, configs_dir, env, root)`; pydantic `extra="forbid"`; `ENV_MAP` ánh xạ tên biến SPEC §14 → khóa |
| `src/automeme/doctor.py` | `automeme doctor` | Python, cấu hình, `.env`, ffmpeg/ffprobe + phiên bản, faster-whisper, GPU (nvidia-smi), Ollama (GET `/api/tags` + có model chưa) hoặc Claude, docker, git, UTF-8 |
| `src/automeme/media/youtube.py` | Tải video YouTube | yt-dlp; hàm thuần `parse_youtube_url` (chỉ YouTube, chuẩn hóa về `watch?v=`), `parse_section`, `check_limits`, `pick_js_runtime`, `build_ydl_options`, `output_name`, `source_record`, `explain_download_error`; `download_youtube(..., ydl_factory)` đọc metadata trước, tải vào `data/temp` rồi đổi tên sang `data/input` |
| `src/automeme/media/ffmpeg.py` | Chạy lệnh ngoài | `which` (tìm cả `Scripts/` của venv), `require_binary`, `run_cmd` (list args, log DEBUG nguyên lệnh), `CommandError` |
| `src/automeme/media/probe.py` | ffprobe | `probe()` → `MediaInfo` (thời lượng, kích thước, fps, audio, sample rate, kênh, định dạng); `parse_probe` là hàm thuần, bỏ qua ảnh bìa |
| `src/automeme/media/audio.py` | Tách audio | WAV PCM 16-bit mono 16 kHz; bỏ qua nếu đã có; ghi file `.part` rồi đổi tên |
| `src/automeme/utils/files.py` | Đường dẫn, JSON | `PROJECT_ROOT`, `CONFIGS_DIR`, `PROMPTS_DIR`; `write_json` UTF-8, ghi file tạm rồi đổi tên |
| `src/automeme/utils/timestamps.py` | Thời gian | `format_ts(13.2) → "00:13.20"`, `parse_ts` |
| `src/automeme/utils/logger.py` | Log | `setup_logging(level)` (gọi lại được), `add_file_log` → `data/logs/automeme.log` (DEBUG, xoay vòng 5 MB × 3) |

### Luồng dữ liệu (chốt ở Iteration 1)

```
data/input/<video>                              video người dùng chép vào
data/input/<tieu-de>-<id>[-<từ>s-<đến>s].mp4    video tải từ YouTube (automeme download)
data/input/<cùng tên>.source.json               link, kênh, giấy phép, đoạn cắt, thời điểm tải
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
mode:"overlay"|"cutaway", position?, scale?, status, confidence?, query?, reason?}]}`; thêm
`{type:"sfx", asset, volume}` và `{type:"zoom", factor}` (không có asset). `status` là
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
| `automeme analyze` (Ollama/Claude) | Xong | Test offline; **2026-09-17 chạy thật với Ollama `qwen3:8b`**: chọn đúng câu punchline, lý do tiếng Việt hợp lý, structured output hợp lệ |
| **Nghiệm thu livestream tiếng Việt thật** | Chạy được; mật độ và timing đã sửa | 2026-09-17: `automeme run <link> --from 36:00 --to 37:30` trên VOD 2 giờ 28 phút của người dùng → MP4 trong 3 phút 59 giây. 2026-09-19 chạy lại với `--profile pro`: 7 meme + 4 SFX → 4 meme (2 cú cắt tràn màn hình + zoom) + 2 SFX khác nhau; meme sớm hơn ~6 s nhờ tách câu; đỉnh âm 0,0 → −0,8 dB. Chọn câu đùa vẫn phụ thuộc qwen3:8b |
| Meme tràn màn hình + zoom + SFX khi cắt (profile `pro`) | Xong | Test render thật (PSNR khung tràn màn hình), trích 8 khung trên livestream; đo âm lượng: tiếng gốc −9 dB lúc cắt, SFX cắt đỉnh −9,5 dB |
| Web: người duyệt tự quyết meme | Xong | Test service + HTTP thật (gợi ý, xem trước asset, đổi chế độ, thêm meme, zoom); Chrome headless chụp editor với dự án thật |
| Tải video YouTube (CLI + Studio) | Xong | 2026-09-17 tải thật Big Buck Bunny (CC-BY): đoạn 0:30–1:00 qua CLI hết 29 s, đoạn 1:00–1:20 qua API Studio hết 17 s; H.264 1920×1080 60fps + AAC, thời lượng đúng; 70 test không cần mạng |
| Nghiệm thu `automeme run` với model thật | Xong (trừ tiếng Việt) | 2026-09-17: Whisper large-v3 + qwen3:8b + kho 130 meme thật → MP4 trong 1 phút 51 giây; kiểm tra khung hình meme hiện đúng lúc, đúng góc |
| Thư viện local + Meme Search API v1 | Xong | Test metadata hỏng từng dòng, safe filter, tìm local, request vector, token, cache và các chặn bảo mật |
| Catalog 100 meme phổ biến có nhãn | Xong | Đã tải thật 100/100; test catalog, tải/tái sử dụng, nhãn song ngữ, safe filter, CLI và Studio API |
| Catalog 30 reaction GIF có nhãn | Xong | Đã tải thật 30/30; mọi file 7–293 frame, test parser GIF, URL ghim SHA, semantic search, CLI và Studio API |
| Catalog 30 sound effect CC0 | Xong | Đã tải thật 30/30 và chạy lại reuse 30/30; OggS/ffprobe hợp lệ, AI schema + timeline + FFmpeg mix + Studio audio preview |
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
| Chạy trọn pipeline với Meme Search thật | Dịch vụ Meme Search chưa được khởi chạy; đã nghiệm thu với local provider |
| Tìm kiếm local hiểu từ đồng nghĩa | Local provider so khớp chữ: "tiết lộ" không khớp "bị nói trúng", nên khi nghiệm thu meme lý tưởng (Monkey Puppet) chưa được chọn. Hướng xử lý: Meme Search (vector), hoặc mở rộng truy vấn bằng ontology Việt–Anh sẵn có — cần người dùng chọn |
| Chất lượng `search_query` của qwen3:8b | Ra dạng từ khóa ("ngượng bất ngờ tiết lộ") vì prompt cố ý hướng về taxonomy cho tìm kiếm chữ; `trigger` ghi nhãn ("reveal") thay vì câu thoại như SPEC §20 |
| Quyền sử dụng media trong kho local | Đã cài 100 template UGC có nguồn/cảnh báo; người dùng vẫn phải tự xác minh quyền trước khi xuất bản, nhất là thương mại |
| Tải video cần đăng nhập (riêng tư, giới hạn tuổi, hội viên) | Chưa hỗ trợ cookie — báo lỗi rõ |
| **Chọn câu đùa còn yếu** | qwen3:8b cho mọi đề xuất 0,85 → thứ tự cú cắt dựa vào luật phụ. Đã thử qwen3:14b (phiên 16): điểm có phân biệt nhưng chọn kém hơn (3/6 vs 5/6) và chậm 2,6× → **giữ 8b**. Giới hạn chính là transcript (sai từ lóng, không dấu câu, không thấy hình). Hướng tiếp: Claude qua `LLM_BACKEND=claude` (tốn phí), cải thiện transcript, lọc câu Whisper bịa |
| **Một số template vẫn có vùng chữ trống** | Đã loại 12 nhãn phong cách cần chữ (profile `pro`), nhưng ảnh như Monkey Puppet vẫn có dải trắng phía trên. Cần gắn nhãn thủ công trong kho hoặc cắt dải trắng |
| Nhận dạng từ mượn tiếng Anh / từ lóng | "live được hai nền tảng" → "lấy lại được hai nền tảng"; "đổi gió" → "đổi giống như". Có thể thử `initial_prompt` (từ vựng stream + dấu câu) |
| Caption, zoom độc lập (không đi kèm cú cắt) | SPEC §71–73 — `cutaway`, `sfx`, `zoom` đã có; caption và zoom theo nhịp gameplay chưa làm |
| File `LICENSE` | Người dùng chưa chọn MIT hay Apache-2.0; repo đang public nên cần sớm |

### Cấu hình

`configs/default.yaml` (đủ mọi khóa) → `configs/<profile>.yaml` → biến môi trường/`.env` →
cờ CLI. Tên biến môi trường theo SPEC §14, danh sách đầy đủ trong `config.ENV_MAP`. Biến rỗng
= không ghi đè. Có test giữ `.env.example` và `ENV_MAP` luôn khớp nhau.

### Test

`pytest -q` — **425 test**, chạy không cần GPU, Ollama, faster-whisper, API key hay mạng. Các test cần FFmpeg (tách audio,
render thật, kiểm tra meme hiện đúng lúc bằng cách so khung hình) tự bỏ qua nếu máy không có
FFmpeg; CI có cài nên chạy cả chúng. CI (GitHub Actions) chạy `ruff check src tests` + `pytest -q` mỗi lần push lên
https://github.com/TrungVuManh/Automatic-Video-Editer (remote `origin`, nhánh `main`).

### Máy người dùng (đo 2026-09-11)

- Windows 11. Python trên PATH là bản *embeddable* 3.13 (không có venv) → dự án dùng `.venv`
  dựng từ Python 3.11.9. **Venv không được kích hoạt sẵn**: gọi qua `.venv\Scripts\...`.
- FFmpeg 9.0.1 (winget), GPU RTX 4060 Laptop **8 GB VRAM**, Docker, gh, git.
- **Đã có SDK Python:** `ollama==0.6.2`, `anthropic==1.4.0`.
- **JS runtime cho yt-dlp:** có Node.js (`C:\Program Files\nodejs`), chưa có Deno/Bun;
  `yt-dlp-ejs 0.8.0` đã cài (2026-09-17), khớp yt-dlp 2026.8.19.
- **Người dùng chỉ tải lại livestream của chính mình** (xác nhận 2026-09-17) — không vướng bản
  quyền; bản ghi dài hàng giờ nên luôn tải theo đoạn.
- **Đã có (kiểm tra 2026-09-17):** ứng dụng Ollama 0.34.0 (chưa tự chạy khi mở máy — cần mở app
  hoặc `ollama serve`) và model `qwen3:8b` 5,2 GB. **Chưa có:** file `.env`.
- **Ổ C chỉ còn ~5,5 GB trống** (đo 2026-09-19; model Whisper/HF cache và Ollama đều nằm ở C).
  RAM 16 GB. `qwen3:14b` (9,3 GB) đã tải vào **`D:\OllamaModels`** để thử — ứng dụng Ollama
  thường không thấy thư mục này; muốn dùng thì chạy
  `$env:OLLAMA_MODELS='D:\OllamaModels'; $env:OLLAMA_HOST='127.0.0.1:11435'; ollama serve`
  rồi đặt `OLLAMA_HOST=http://127.0.0.1:11435`, `OLLAMA_MODEL=qwen3:14b` khi chạy automeme.
  Không dùng nữa thì xoá thư mục đó.
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

**2026-09-19 — dựng kiểu chuyên nghiệp** (người dùng: "hãy tự quyết định, hoặc hoàn thành bản
web để tự quyết định meme"):

- Meme tràn màn hình (`mode: cutaway`): video gốc **vẫn chạy bên dưới** (không đổi thời lượng),
  tiếng gốc giảm còn 35% rồi trở lại, meme chiếm 92% khung trên nền mờ tối của chính nó, phóng
  1,06 → 1 trong 0,15 s, mờ dần vào/ra. Cả bài qua `alimiter` −1 dB.
- Zoom 1,1× vào gameplay trong 0,3 s ngay trước mỗi cú cắt; mỗi cú cắt có một SFX riêng
  (`cutaway.sfx_volume` 0,6, to hơn SFX thường) — không tính vào mật độ SFX thường.
- Cú cắt do **code** chọn: `cutaway.mode: auto`, confidence ≥ 0,8, tối đa 2/phút, cách nhau
  ≥ 15 s (đầu → đầu), **không quá 50% số meme** (`max_share`). Bằng điểm thì ưu tiên khoảnh
  khắc AI cũng đề xuất SFX, rồi đến khoảnh khắc sớm hơn. Mặc định `mode: never`; profile mới
  `pro` bật `auto`, các profile khác giữ nguyên.
- Meme trùng giờ với cú cắt tràn màn hình là **lỗi** (renderer vẽ theo thứ tự sự kiện nên meme
  góc sẽ đè lên cú cắt). Đổi quyết định trong commit `ff44c38` ("meme góc lúc cắt vẫn được").
- Tách đoạn Whisper dài hơn 4 s tại khoảng lặng ≥ 0,3 s giữa các từ (im lặng ≥ 1 s luôn là ranh
  giới) trước khi dựng context; transcript trên đĩa giữ nguyên. Prompt có thang điểm confidence.
- Web: người duyệt đổi chế độ, chọn meme gợi ý (xếp theo truy vấn AI, bù phần còn lại của thư
  viện; tự gõ từ khóa thì chỉ kết quả khớp), chèn meme mới tại playhead (được chấp nhận sẵn,
  validator vẫn chặn chồng lấn). Chỉ chọn được asset trong `assets/memes` và `assets/gifs`.

**2026-09-17 — tải video YouTube** (người dùng đồng ý cả 5 điểm):

- Công cụ: **yt-dlp** (Unlicense), khai báo là phụ thuộc chính trong `pyproject.toml`; JS runtime
  tự chọn deno → node → bun (`download.js_runtime: auto`).
- Script giải thử thách: người dùng chọn cài gói **`yt-dlp-ejs`** (không dùng
  `remote_components` tải script lúc chạy). yt-dlp ghim **đúng** một bản ejs, nên
  `pyproject.toml` chỉ ghi `>=0.8.0` còn `doctor` đọc bản yt-dlp ghim (`importlib.metadata.requires`)
  và báo lệch kèm lệnh cài chính xác. Không dùng `yt-dlp[default]` vì kéo thêm 7 gói ngoài phạm vi
  đã duyệt.
- Livestream: `is_live`, `is_upcoming`, `post_live` (vừa kết thúc, đang xử lý bản ghi) bị chặn với
  thông báo riêng từng trường hợp; `was_live` tải bình thường.
- **Kênh của bạn** (người dùng: "just do your best"): `YOUTUBE_OWN_CHANNELS` trong `.env` →
  `download.own_channels`. Đặt ở `.env` chứ không ở `configs/` vì là thông tin riêng, không commit.
  So khớp `channel_id`, `uploader_id` (@handle), `channel_url`, `uploader_url` sau khi chuẩn hóa;
  link tab kênh (`/@kenh/streams`, `/channel/UC…/videos`) lấy đúng đoạn định danh.
- **Mốc `t=` trong link** (`t=3750`, `t=1h2m30s`, `start=`, `#t=`): chỉ điền `--from` còn trống;
  thiếu `--to` thì lấy `download.clip_seconds` (90 s), kẹp theo thời lượng video. `--from` người
  dùng nhập luôn thắng. Link vẫn được chuẩn hóa (bỏ `t=`) trước khi đưa cho yt-dlp.
- **Chỉ nhận link YouTube**, chuẩn hóa về `https://www.youtube.com/watch?v=<id>` trước khi đưa
  cho yt-dlp (bỏ `list=` và tham số lạ, `noplaylist`). Lý do: extractor "generic" của yt-dlp tải
  được URL bất kỳ, nên Studio nhận mọi URL thì có thể bị lợi dụng tải từ mạng nội bộ.
- Tải một đoạn bằng `download_ranges` + `force_keyframes_at_cuts` (cắt đúng khung hình).
  Kiểm tra giới hạn (`max_duration` 600 s, livestream) **trước** khi tải, dựa trên metadata.
- Ưu tiên H.264 + AAC trong MP4 (`format_sort`), tối đa 1080p: xem được ngay trong Studio.
- Tên file `<tiêu đề rút gọn ≤40 ký tự tại ranh giới chữ>-<id>[-<từ>s-<đến>s].mp4`; không slug
  mã video (mã phân biệt hoa thường). Không phải Creative Commons thì cảnh báo, không chặn.
- CLI: `automeme download` và `automeme run <link> --from --to`. Studio: `POST /api/videos/youtube`
  dùng chung hàng đợi một job với pipeline (`JobState.kind = "download"`, `percent`).
- Sửa kèm lỗi có sẵn trong Studio: `updateJob` ↔ `loadDashboard` ↔ `renderDashboard` lặp vô hạn
  khi job cuối đã xong. Giờ việc khi job kết thúc chạy đúng một lần cho mỗi (job, trạng thái);
  dashboard gọi `updateJob(..., {silent: true})`. Đo bằng Edge headless: mở trang chỉ gọi
  `/api/dashboard` một lần.

**2026-09-17 — sửa lỗi phát hiện khi nghiệm thu:**

- So khớp tìm kiếm (meme local, ranker emotion/style, SFX) chuyển sang `memes/matching.py`:
  **giữ dấu tiếng Việt**, khớp theo cụm âm tiết bằng quy hoạch động, âm tiết khớp lẻ trong truy
  vấn nhiều âm tiết được 0,5 điểm; truy vấn gõ không dấu thì so ở dạng bỏ dấu như cũ.
  `local.tokenize` (bỏ dấu) giữ nguyên, chỉ còn dùng để sinh ID/tag từ tên file.
- Bỏ `phrase_bonus` cũ: với cách chấm mới, truy vấn khớp trọn đã đạt 1,0; còn phép `in` chuỗi
  con có thể cộng nhầm ("lo" nằm trong "lorem").
- Cảnh báo mật độ trong `validate_timeline` dùng cùng công thức với `analyzer/detector.py`:
  `max(1, floor(thời lượng × meme/phút / 60))`.
- Timing trong analysis làm tròn tới mili giây.

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

Đã nghiệm thu với Ollama + kho meme thật (2026-09-17) và dựng kiểu `pro` trên livestream
(2026-09-19). Còn: chọn câu đùa tốt hơn (qwen3:14b đã thử, không tốt hơn — thử Claude hoặc
cải thiện transcript; lọc câu Whisper bịa như "Cảm ơn các bạn đã theo dõi…");
cải thiện chọn meme khi không có Meme Search (tìm kiếm chữ không hiểu đồng nghĩa); caption và
zoom theo nhịp gameplay; kiểm tra thêm media meme dạng video.
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
- [x] Cài catalog 30 SFX Kenney CC0, AI chọn theo query, cooldown/mật độ/volume và FFmpeg mix
- [x] Vendor OSS offline + third-party notices
- [x] Tải video YouTube bằng yt-dlp: CLI `download`, `run <link>`, ô dán link trong Studio
- [x] Meme tràn màn hình + zoom trước cú cắt + SFX khi cắt + giảm tiếng gốc + limiter (profile `pro`)
- [x] Tách đoạn Whisper dài theo khoảng lặng; thang điểm confidence trong prompt
- [x] Web: đổi góc/tràn màn hình, gợi ý meme thay thế có tìm kiếm, chèn meme tại playhead, chỉnh zoom

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

### 2026-09-19 (phiên 16) — Thử model lớn hơn: qwen3:14b (Claude Code)

**Yêu cầu.** "Hãy thử model lớn hơn". Máy: RTX 4060 Laptop 8 GB, RAM 16 GB, ổ C còn 5,5 GB →
`qwen3:30b` (19 GB) không vừa; chọn `qwen3:14b` (9,3 GB, cùng họ nên so công bằng). Tải vào
`D:\OllamaModels` qua một server Ollama riêng ở cổng 11435 (không đổi cấu hình Ollama của người
dùng, không tốn chỗ ổ C). Không sửa code: model đã chỉnh được bằng `OLLAMA_MODEL`/`OLLAMA_HOST`.

**Cách đo.** Cùng transcript (28 câu sau khi tách), cùng prompt, `--profile pro`. Đáp án tham
chiếu lập trước khi chạy 14b, từ lời thoại + khung hình: **mạnh** — câu 20 (63,7 s, cảm thán
"…lôi đâu ra đấy" khi cười với chat), câu 9 (30,5 s, game hiện "Here's the first one…" — tìm được
cầu chì); **vừa** — câu 15 (51,6 s, đùa "ăn cứt"), câu 5 (14,8 s, kết chuyện "cậu ăn phở"). Meme
tính là trúng nếu bắt đầu trong khoảng [đầu câu − 1 s, cuối câu + 1,5 s].

| | qwen3:8b | qwen3:14b |
|---|---|---|
| Thời gian phân tích 28 câu | ~3,5 phút (7,5 s/câu) | 9 phút 14 s (~20 s/câu) |
| JSON hợp lệ | 26/28 | 28/28 |
| Điểm confidence | 0,85 ×4 | 0,85, 0,75 ×3 |
| Meme (cú cắt) | 6,6 · **14,9** · 33,8 · **67,5** | 51,7 · **63,8** · 73,2 · 86,9 |
| Trúng tham chiếu | câu 20, 9, 5 → **5/6**, thừa 1 | câu 20, 15 → **3/6**, thừa 2 |

14b có hai điểm tốt: điểm phân biệt nên luật `min_confidence 0,8` chỉ cho **một** cú cắt, đúng
khoảnh khắc mạnh nhất; không lỗi schema. Nhưng bỏ sót khoảnh khắc tìm cầu chì, lý do vẫn chung
chung ("mang tính mỉa mai" cho cả 4) và chèn ở 86,9 s vì hiểu "hình yêu" (lỗi nhận dạng) là chơi
chữ. **Kết luận: giữ qwen3:8b mặc định.** Một đoạn 90 s là mẫu nhỏ; kết luận chắc hơn cần thêm
đoạn. Output để so: `data/output/..._pro-qwen3-8b.mp4`, `..._pro-qwen3-14b.mp4` (bản
`_automeme.mp4` hiện là của 14b).

**Phát hiện thêm.** Whisper bịa câu cuối "Cảm ơn các bạn đã theo dõi và hẹn gặp lại." dài 0,04 s
(câu 27) — lỗi quen thuộc của Whisper ở đoạn im lặng; cả hai model đều không chọn câu này nhưng
nên lọc ở bước chuẩn hóa transcript (chưa làm, chờ duyệt).

**Dọn dẹp.** Đã tắt server Ollama tạm và ứng dụng Ollama (lỡ khởi động khi gọi `ollama list`).
`D:\OllamaModels` (9,3 GB) được giữ lại — xoá nếu không dùng.

### 2026-09-19 (phiên 15) — Dựng kiểu chuyên nghiệp + người duyệt tự quyết meme (Claude Code)

**Yêu cầu.** "Chỉnh lại edit kèm sound effect, chèn meme và GIF tràn màn hình, trông chuyên
nghiệp nhất có thể" → "tự quyết định, hoặc hoàn thành bản web để tự quyết định meme". Quyết định
đã chốt ở mục 4 (2026-09-19).

**Đã làm (4 giai đoạn, commit `ff44c38` cho giai đoạn 1–2):**
1. Render: cú cắt tràn màn hình, zoom trước cú cắt, giảm tiếng gốc, limiter; FPS meme theo video.
2. Quyết định dựng: `pick_cutaways`, ưu tiên GIF cho cú cắt, SFX kèm cú cắt và chống lặp file,
   loại template cần chữ, luân phiên góc; profile `pro`.
3. Bám câu đùa: `split_long_segments` + thang điểm confidence trong prompt.
4. Web: API gợi ý/xem trước asset/thêm meme; Studio có công tắc chế độ, lưới gợi ý có tìm kiếm,
   chèn meme tại playhead, chỉnh zoom, xem trước tràn màn hình (backdrop blur) và zoom, meme góc
   bị giới hạn chiều cao như render; `automeme review` hỗ trợ chế độ + zoom.

**Nghiệm thu trên livestream (đoạn 36:00–37:30, `--profile pro`).**

| | Trước (`funny`, 17/9) | Sau (`pro`) |
|---|---|---|
| Meme / SFX | 7 / 4 (cùng một âm "punch") | 4 (2 tràn màn hình + 2 góc) / 2 âm khác nhau |
| Câu gửi LLM | 11 đoạn 6–17 s | 28 câu ngắn; giữ 4/26 |
| Meme đầu tiên | 12,8 s | 6,6 s (sau câu nói ở 6,46 s) |
| Đỉnh âm cả bài | 0,0 dB | −0,8 dB |

Trích 8 khung: zoom thấy rõ, cú cắt tràn màn hình nền mờ, meme góc luân phiên không che facecam.
Đo âm: tiếng gốc −9 dB trong cú cắt; SFX cắt ban đầu chỉ đỉnh −14 dB → thêm `cutaway.sfx_volume`
(0,6), giờ −9,5 dB. Bản cũ giữ ở `data/output/..._truoc-pro.mp4` để so.

**Lỗi tìm ra khi chạy thật, đã sửa kèm test tái hiện:**
- `split_long_segments`: `pieces[-2] += pieces.pop()` lỗi IndexError khi mẩu cuối quá ngắn;
  im lặng 6 s bị gộp vì mẩu trước chưa đủ 3 từ → im lặng ≥ 1 s luôn là ranh giới.
- qwen3 trả `timing.duration=0` khi `insert_meme=false` → cả câu bị loại hai lần (2/28 câu).
- 3/4 meme thành cú cắt vì điểm bằng nhau → thêm `cutaway.max_share` + ưu tiên có SFX.
- Cú cắt thứ hai mất SFX (file khớp nhất vừa dùng) → thử thêm `cutaway.sfx_query`.
- Gợi ý web chỉ 2–3 meme vì truy vấn AI khớp ít → bù phần còn lại của thư viện.
- Web: ảnh xem trước trong bảng sự kiện bị cắt (lỗi cũ); meme góc khổ dọc ở bản xem trước cao
  gần hết khung trong khi render giới hạn 45% → state trả `display` từ cấu hình.

405 → **425 test**, ruff sạch.

**Còn lại:** qwen3:8b vẫn cho 0,85 cho mọi đề xuất (xem mục 2 "Chưa làm được"); Monkey Puppet
có dải trắng phía trên; caption chưa làm.

### 2026-09-17 (phiên 14) — Phân tích phong cách HK15 và dựng bản demo thủ công (Codex)

**Tham chiếu.** Phân tích hai đoạn mở đầu 90 giây từ kênh HK15:
`NUdAnKxsIQo` và `Tp4YsPEWZ8Y`. Sau màn cảnh báo khoảng 15 giây, ngưỡng scene-change 0,22 cho
thấy nhịp đổi hình trung bình 2,44 giây và 2,17 giây. Phần lớn nhịp đến từ gameplay, crop/zoom,
caption và facecam; reaction lớn/cutaway chỉ dùng tại punchline, thường dưới khoảng 1–1,5 giây.

**Triển khai.** Dùng video tiếng Việt 90 giây đã có trong workspace, tạo timeline thủ công
`data/timelines/bach-stream-dung-choi-tro-nay-tao-cu-gspiiw_g1bu-2160s-2250s.hk15.timeline.json`:
7 GIF ngắn 0,9–1,15 giây, 3 SFX khác nhau, timing bám timestamp theo từ thay vì cuối đoạn Whisper,
đổi giữa top-right/bottom-right/center để không che facecam góc dưới trái. Không dùng template
trống chữ và không dùng reaction chính trị.

**Kết quả.** Render ra
`data/output/bach-stream-dung-choi-tro-nay-tao-cu-gspiiw_g1bu-2160s-2250s_hk15-style.mp4`:
H.264/AAC, 1920×1080, đúng 90,000 giây. Đã trích khung tại cả 7 event để kiểm tra overlay; audio
giữ mean −21,5 dB, peak từ 0,0 dB nguồn thành −0,1 dB, không tăng clipping. Đây là bản dựng mẫu
đã duyệt thủ công; chưa thêm profile tự động hay tính năng caption/zoom/cutaway vào code.

### 2026-09-17 (phiên 13) — Nghiệm thu trên livestream tiếng Việt thật (Claude Code)

**Video.** `https://www.youtube.com/watch?v=GspiiW_G1BU` — livestream Gaming tiếng Việt, 2 giờ 28
phút, kênh `@zzstardragonzz` (người dùng xác nhận chỉ dùng livestream của mình).

**Chọn đoạn bằng dữ liệu, không đoán.** Không có heatmap (72 lượt xem). Tải riêng live chat (273
tin, 15 người) và phụ đề tự động (~18.900 từ) → phút 36–37 vừa nhiều lời nói (165/159 từ/phút) vừa
trùng lúc chat sôi nổi → chọn 36:00–37:30.

**Chạy.** Máy đang mở VALORANT (GPU đã dùng 4,9/8 GB, 87°C) → `WHISPER_COMPUTE_TYPE=int8_float16`;
Ollama tự chia một phần model sang CPU.

```powershell
$env:WHISPER_COMPUTE_TYPE="int8_float16"
automeme -v run "https://www.youtube.com/watch?v=GspiiW_G1BU" --from 36:00 --to 37:30 --profile funny
```

Tổng 3 phút 59 giây: tải 54 s → Whisper 48 s (10 đoạn, 228 từ) → qwen3:8b ~100 s (giữ 7/10) →
timeline + render 33 s. Video ra 1920×1080, đúng 90,000 s, còn tiếng, SFX được trộn (đỉnh âm tại
24,6 s tăng từ −11,0 lên −9,2 dB); meme ở góc dưới phải, không che facecam góc dưới trái.

**Đánh giá.** Transcript nghe ra đúng ý chính (so với phụ đề tự động của YouTube: 228 vs 256 từ)
nhưng sai từ mượn/từ lóng và không có dấu câu. Chất lượng dựng **chưa đạt**: quá dày, meme neo
cuối đoạn dài, template trống chữ, SFX lặp — chi tiết ở mục 2 "Chưa làm được".

**Lỗi đã sửa theo `/sua-loi`** (test tái hiện đỏ trước):
1. **Cooldown đo lệch:** analyzer/builder đo đầu→đầu (đúng ví dụ SPEC §32) nhưng validator (viết ở
   Iteration 2) đo cuối→đầu → timeline tự dựng bị chính validator cảnh báo "event_008 → event_010
   chỉ cách 5,4 s". Validator giờ đo đầu→đầu.
2. **Meme khổ dọc cao gần hết màn hình** (GIF Confused Travolta rộng 30% nhưng cao ~95% khung):
   thêm `meme.max_height_ratio` (0,45), filter `scale=w=…:h=…:force_original_aspect_ratio=decrease:
   force_divisible_by=2`. Render lại cùng timeline: GIF gọn trong 45% chiều cao.
3. Lệnh `render` báo "Đã chèn 11 meme" cho 7 meme + 4 SFX → giờ đếm riêng, bỏ sự kiện bị Reject.

377 → **380 test**, ruff sạch.

**Việc tiếp theo (chờ người dùng chọn):** tách đoạn transcript theo khoảng lặng; siết số meme
(điểm phân biệt + top-K); bỏ template trống chữ khỏi tự chọn; phạt SFX trùng.

### 2026-09-17 (phiên 12) — Tải video YouTube bằng yt-dlp (Claude Code)

**Đã làm.** `media/youtube.py` (hàm thuần + lớp gọi yt-dlp nhận `ydl_factory`), mục cấu hình
`download`, lệnh `automeme download`, `automeme run` nhận link kèm `--from/--to`, hai dòng
`doctor` (tuổi của yt-dlp; JS runtime + `yt-dlp-ejs`), job tải trong Studio + endpoint
`/api/videos/youtube` + ô dán link ở trang Tạo video; cập nhật GUIDE/README/THIRD_PARTY_NOTICES.
281 → **351 test**, ruff sạch. Bản sửa tìm kiếm tiếng Việt phiên 11 đã commit riêng (`b15b367`).

**Đã chạy thật.**
- CLI: tải đoạn 0:30–1:00 của `https://www.youtube.com/watch?v=aqz-KE-bpKQ` → 29 s, H.264
  1920×1080 60fps + AAC, dài đúng 30,000 s, 14,8 MB; `.source.json` ghi giấy phép "Creative
  Commons Attribution"; thư mục tạm đã dọn.
- Studio API (như trình duyệt gửi): link `http://192.168.1.1/admin` → 400 kèm thông báo tiếng
  Việt; link YouTube đoạn 1:00–1:20 → 202, xong sau 17 s, video hiện trong danh sách dự án.
- Edge headless chụp trang Tạo video: khối "hoặc tải từ YouTube" đúng phong cách; mở trang khi
  job cuối đã xong chỉ gọi `/api/dashboard` **một lần** (trước đây lặp vô hạn).

**Phát hiện khi chạy thật.**
- Nhận định lúc lập kế hoạch "có Node là đủ" **sai**: lần thử đó chỉ liệt kê định dạng. Khi tải
  thật, yt-dlp báo thiếu script giải thử thách ("n challenge solving failed"). Vẫn tải đủ 1080p
  nhưng có thể bị bóp tốc độ. `doctor` đã sửa để báo đúng (THIẾU, nêu gói `yt-dlp-ejs`).
- Tên file ban đầu xấu ("…4k---official-blender-foundat-…") → gộp gạch nối, cắt tại ranh giới chữ.
- Tải theo đoạn không có phần trăm (yt-dlp cắt bằng FFmpeg) → thêm dòng trạng thái "Đang tải đoạn…".

**Bổ sung cuối phiên** (người dùng: chỉ tải livestream của chính mình, "tiếp tục"): cài
`yt-dlp-ejs 0.8.0`; tải lại đoạn 1:00–1:20 → hết cảnh báo "n challenge", 15,6 s cả quy trình
(trước 17 s). `doctor` kiểm tra ejs khớp bản yt-dlp ghim. Thông báo riêng cho live đang phát /
chưa bắt đầu / vừa kết thúc. GUIDE thêm mục tải lại livestream. 351 → **355 test**.

**Bổ sung lần 2** (người dùng: "just do your best"): khai báo kênh của mình
(`YOUTUBE_OWN_CHANNELS`) để tắt cảnh báo bản quyền, và dán link có mốc `t=` để tải 90 giây từ
mốc đó — dành cho quy trình xem lại VOD, "Sao chép URL tại thời điểm hiện tại". Test viết cho
link tab kênh lộ ra lỗi thật: `/@kenh/streams` bị hiểu thành kênh `@streams` → đã sửa. Chạy thật:
link `?t=600` tải đúng 10:00–10:35 (kẹp theo cuối video); khai báo bằng link tab
`/@BlenderOfficial/streams` nhận đúng kênh từ metadata thật. 355 → **377 test**.

**Còn tồn tại.** Chưa hỗ trợ video cần đăng nhập (VOD riêng tư); chưa chạy trọn pipeline trên
livestream tiếng Việt thật của người dùng (cần link + mốc thời gian từ người dùng).

### 2026-09-17 (phiên 11) — Nghiệm thu với model thật + sửa tìm kiếm tiếng Việt (Claude Code)

**Kiểm tra đầu phiên.** 5 commit của phiên 6–10 chưa push; đã soát: không có file media, file
lớn hay khóa bí mật. 264 test xanh. Ollama 0.34.0 đã cài, `qwen3:8b` đã tải; server phải bật tay.

**Nghiệm thu thật** (video mẫu 11,68 giây giọng đọc tiếng Anh, vì vẫn chưa có video tiếng Việt):

```powershell
$env:WHISPER_LANGUAGE="en"; automeme -v run data\input\nghiem-thu-en.mp4 --profile funny
```

Toàn luồng 1 phút 51 giây: Whisper nạp 12 s + nhận dạng 3 s; Ollama nạp model lần đầu ~80 s,
mỗi đoạn sau ~6 s. qwen3 chọn **đúng** câu punchline "well my wife keeps it for me"
(confidence 0,9, lý do tiếng Việt hợp lý); meme đặt ở 10,55 s ngay sau câu nói. Video ra giữ
nguyên thời lượng và tiếng.

**Ba lỗi phát hiện, đã sửa theo quy trình `/sua-loi`** (test tái hiện đỏ trước, xanh sau):

1. **Chọn sai meme vì tìm kiếm bỏ dấu.** Truy vấn "ngượng bất ngờ tiết lộ" → token
   {nguong, bat, ngo, tiet, lo}; meme ba đầu rồng ("ngớ ngẩn nổi **bật**") được 0,60 điểm, còn
   Monkey Puppet ("ngượng ngùng, bị nói trúng") chỉ 0,20. Sửa bằng `memes/matching.py`; đã so
   sánh công thức trên kho thật với 10 truy vấn trước khi chọn. Sau sửa, cùng analysis đó chọn
   Anakin/Padme ("im lặng đáng ngờ", nhãn awkward) — hợp cảm xúc "ngượng" hơn hẳn.
2. **Báo nhầm mật độ:** 1 meme trong video 11,68 s bị cảnh báo "5,1 meme/phút > 5".
3. **Sai số float:** `analysis.json` ghi `duration: 1.129999999999999`.

264 → **281 test** (5 test tái hiện lỗi + 12 test cho `matching.py`), ruff sạch. Cập nhật GUIDE
(cách tìm kiếm local so khớp, công thức mật độ).

**Còn tồn tại.**
- Chất lượng nhận dạng tiếng Việt — vẫn cần video tiếng Việt thật.
- Tìm kiếm chữ không hiểu đồng nghĩa nên chưa chọn được meme lý tưởng (xem "Chưa làm được").
- `search_query` dạng từ khóa và `trigger` là nhãn thay vì câu thoại (prompt/schema).
- Ollama nạp model lần đầu ~80 s; cảnh báo timeline in hai lần (sau khi dựng và trước khi render).

**Việc tiếp theo:** người dùng cung cấp video tiếng Việt để nghiệm thu nốt; quyết định hướng cải
thiện chọn meme (Meme Search hay mở rộng truy vấn bằng ontology).

### 2026-09-13 (phiên 10) — Sound effect CC0 end-to-end (Codex)

**Đã làm.** Thêm catalog 30 SFX Kenney CC0 với nhãn Việt–Anh, `automeme install-sfx` và nút
**Cài 30 SFX CC0** trong Studio. Downloader chỉ nhận đúng HTTPS host/repo/revision đã ghim,
không theo redirect, giới hạn 5 MB và xác minh `OggS`; đã tải thật 30/30 và lần hai reuse 30/30.

Schema AI có `insert_sfx`/`sfx_query`; timeline hỗ trợ `SfxEvent`, vẫn đọc được timeline meme
cũ. Builder áp score threshold, cooldown, giới hạn âm/phút và master volume. Renderer FFmpeg
delay từng âm đến timestamp rồi `amix` với audio gốc; đã test render thật giữ nguyên thời lượng.
Studio liệt kê/nghe thử/lọc SFX và editor cho thay file, chỉnh timing, duration, volume,
Accept/Reject. Tổng kiểm thử sau thay đổi: **264 passed**, ruff sạch.

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
