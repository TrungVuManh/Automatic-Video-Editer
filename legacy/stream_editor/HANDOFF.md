# HANDOFF — Tài liệu bàn giao dự án stream-auto-editor

> Tài liệu này dành cho **Claude Code** (và người phát triển) để làm tiếp dự án.
> Đọc toàn bộ trước khi bắt đầu một phiên mới. Sau mỗi việc hoàn thành, cập nhật
> **Checklist** và **Nhật ký tiến độ** ở cuối file.

---

## 1. Mục tiêu dự án

Tự động hóa việc edit video stream game cho streamer Việt Nam:

1. Từ một VOD dài (1–6 giờ) → tìm và cắt các khoảnh khắc hay (highlight).
2. Xuất hai định dạng: **ngang** (YouTube) và **dọc** (Shorts/TikTok), có phụ đề.
3. **Tự động chèn meme** (âm thanh, ảnh, video phông xanh, hiệu ứng) đúng thời điểm.
4. Sinh metadata: tiêu đề, mô tả, tags, chapter, thumbnail.
5. Người chỉ **duyệt** (15–20 phút/VOD), không edit tay.

**Nguyên tắc kiến trúc cốt lõi:** Claude (qua API) chỉ **ra quyết định** và trả JSON có cấu trúc
(tool use). Mọi xử lý media do **FFmpeg** làm. Mọi output của model đều phải qua hàm
`validate_*` trước khi dùng — model có thể bịa id, trả thời gian sai, vượt giới hạn.

---

## 2. Hiện trạng (đã xong tuần 1, phần code của 1.5, và tuần 2)

### Luồng dữ liệu

```
jobs/<job>/
├── job.json                     # tên job, streamer, nền tảng, url
├── raw/vod.mp4, audio.wav       # bước 1 (audio mono 16 kHz)
├── raw/chat_raw.json            # bước 1 (định dạng gốc YouTube/Twitch)
├── transcript/chat.json         # bước 2: [{t, user, text}]
├── transcript/words.json        # bước 2: [{w, start, end}]  (giây từ đầu VOD)
├── transcript/segments.json     # bước 2: [{start, end, text}]
├── transcript/loudness.json     # bước 2: [dB mỗi giây]
├── candidates/candidates.json   # bước 3: [{id:"k01", start, end, peaks:[...], score}]
├── candidates/prompt_last.md    # bước 4: prompt thực tế đã gửi (để debug)
├── clips.json                   # bước 4: [{id:"c01", candidate_id, start, end, loai, diem,
│                                #           tieu_de, hook, ly_do, approved: null|true|false}]
├── subs/c01_doc.ass             # bước 7: phụ đề karaoke, một file mỗi clip × định dạng
├── preview/  final/             # bước 7: c01_ngang.mp4, c01_doc.mp4, highlight_<đd>.mp4
├── usage.json                   # token vào/ra + ước tính USD từng lần gọi API
└── pipeline.log                 # log mức DEBUG (kèm nguyên lệnh FFmpeg) — gửi khi báo lỗi
```

### Module

| File | Vai trò | Ghi chú |
|---|---|---|
| `run.py` | CLI điều phối | `all`, `fetch`, `preprocess`, `candidates`, `select`, `review`, `render` |
| `pipeline/common.py` | Đường dẫn, `Job`, I/O JSON, `run_cmd` | Mọi đường dẫn file của job đi qua `Job` |
| `pipeline/s1_fetch.py` | Tải VOD + chat, tách audio | yt-dlp; Twitch chat qua TwitchDownloaderCLI |
| `pipeline/s2_preprocess.py` | Parse chat, âm lượng, ASR | WhisperX hoặc faster-whisper; âm lượng đọc theo khối |
| `pipeline/s3_candidates.py` | Chấm điểm cửa sổ 10s, chọn đỉnh | So với **mức nền cục bộ** (trung vị trượt 5 phút); mức tham chiếu cố định trong `settings.yaml → candidates.refs` |
| `pipeline/s4_select.py` | Gọi Claude chọn clip | Tool `submit_clips`; `validate_clips`; `snap_to_words`; đưa phản hồi cũ vào prompt |
| `pipeline/s4b_review.py` | Duyệt trên terminal | Ghi `feedback/examples.jsonl` (`kind: "clip"`) |
| `pipeline/claude_api.py` | Lớp bao SDK Anthropic | `make_client` (retry 3 lần), `call_tool`, dịch lỗi sang tiếng Việt |
| `pipeline/layout.py` | Filtergraph khung dọc 1080×1920 | Hàm thuần; quy đổi toạ độ preset theo độ phân giải nguồn; mọi cạnh chẵn |
| `pipeline/subtitles.py` | Dựng file `.ass` karaoke | Hàm thuần: gom dòng → tag `\k` → nội dung file |
| `pipeline/s7_render.py` | Render ngang/dọc + phụ đề + ghép | Encode lại để cắt chính xác; ghép bằng concat `-c copy` |
| `pipeline/diagnostics.py` | `doctor` (môi trường), `inspect` (bảng điểm tín hiệu) | Phần dựng bảng là hàm thuần, có test |

### Test

`pytest -q` — **58 test**, chạy không cần GPU, API key, FFmpeg hay mạng (Claude được giả lập
trong `tests/test_select_mock.py`). CI chạy trên GitHub Actions mỗi lần push.

### Đã chạy thật

- **Render ngang + dọc + phụ đề karaoke trên Windows** (FFmpeg 9.0.1, Python 3.11 trong `.venv`):
  video tự sinh bằng `lavfi`, kết quả đúng 1920×1080 và 1080×1920, chữ tiếng Việt đủ dấu, tô
  chữ theo lời nói đúng thời điểm. Cách dựng lại nằm ở Nhật ký mục 2026-09-10 (phiên 2).

### Những phần CHƯA được chạy thật (rủi ro cao nhất — xem mục 4)

- WhisperX với tiếng Việt (đặc biệt model căn chỉnh theo từ) — **rủi ro số 1**: `words.json`
  rỗng sẽ làm hỏng cả `snap_to_words` lẫn phụ đề karaoke. Code đã cảnh báo rõ khi gặp.
- Lệnh gọi Claude API thật (mới test bằng giả lập).
- yt-dlp tải live chat YouTube; TwitchDownloaderCLI.
- Layout dọc trên VOD thật: toạ độ `facecam` trong preset mới là số ví dụ, chưa đo.

---

## 3. Quy tắc làm việc cho Claude Code

1. **Lập kế hoạch trước khi code** mỗi hạng mục: liệt kê file sẽ tạo/sửa, hàm chính,
   định dạng JSON mới, test sẽ viết. Chờ người dùng đồng ý rồi mới làm.
2. **Hàm thuần tách khỏi I/O**: logic (dựng filtergraph, dựng file ASS, kiểm tra JSON)
   phải là hàm thuần có test; phần gọi FFmpeg/API mỏng nhất có thể.
3. **Import nặng bên trong hàm** (whisperx, faster_whisper, anthropic, torch) để test
   chạy được trên CI.
4. **Không đổi định dạng JSON đã có** mà không cập nhật: test, mục 2 của file này,
   và mọi module đọc định dạng đó.
5. **Tham số điều chỉnh được** đặt trong `config/settings.yaml` hoặc preset streamer,
   không hard-code trong code.
6. **Mỗi bước bỏ qua nếu output đã tồn tại** (chạy lại được từ giữa chừng). Giữ nguyên
   quy ước này cho các bước mới.
7. **Log và comment bằng tiếng Việt.** Tên hàm/biến bằng tiếng Anh; key JSON giữ theo
   quy ước hiện có (một số key tiếng Việt không dấu như `tieu_de`, `ly_do`).
8. `pytest -q` phải xanh trước khi đề xuất commit. Commit nhỏ, mỗi commit một ý.
   Chỉ commit khi người dùng đồng ý.
9. **Không bao giờ commit** `.env`, file media, thư mục `jobs/`.
10. **Hỏi trước khi cài thư viện mới**, nhất là thư viện nặng. Ưu tiên FFmpeg + stdlib.
11. Mọi prompt gửi Claude đặt trong `prompts/*.md`, không viết prompt dài trong code.
12. Mọi lệnh gọi API ghi lại token vào `jobs/<job>/usage.json` (xem tuần 4) để theo dõi chi phí.

### Những điều cần hỏi người dùng khi chưa rõ

- Streamer stream trên YouTube hay Twitch? Layout overlay (vị trí facecam) thế nào?
- Phong cách kênh, nội dung cấm (để điền preset).
- Máy có GPU NVIDIA không? Hệ điều hành (Windows/Linux)?

---

## 4. Tuần 1.5 — Chạy thật lần đầu & gia cố (LÀM TRƯỚC TIÊN)

Mục tiêu: pipeline tuần 1 chạy thành công trên **một VOD thật 30–60 phút** trên máy người dùng.
Dùng lệnh `/chay-that` để được hướng dẫn từng bước.

### Việc cần làm

- [x] Kiểm tra môi trường — đã có lệnh `python run.py doctor` làm hết (ffmpeg, ffprobe,
      ffplay, yt-dlp, TwitchDownloaderCLI, thư viện Python, backend ASR, CUDA, UTF-8, API key).
      Ba trạng thái: `[ HỎNG ]` phải sửa, `[THIẾU ]` tùy chọn, `[  OK  ]` đạt.
- [x] Trên Windows: `setup_logging()` tự ép `sys.stdout`/`stderr` về UTF-8; `doctor` cảnh báo
      nếu console không phải UTF-8. Mọi `open()` đều đã có `encoding="utf-8"`.
- [ ] Chạy từng bước một (`fetch` → `preprocess` → `candidates` → `select`), kiểm tra
      output mỗi bước trước khi sang bước sau.
- [ ] **WhisperX tiếng Việt** (cần GPU + VOD thật): xác nhận có model căn chỉnh cho `vi`.
      Đã chuẩn bị sẵn: khoá `asr.align_model` trong `settings.yaml` được truyền thẳng vào
      `load_align_model(model_name=...)`, và bước 2 cảnh báo to nếu `words.json` rỗng. Nếu `load_align_model`
      lỗi, code đã fallback về timestamp theo câu — nhưng khi đó `words.json` sẽ rỗng,
      làm hỏng `snap_to_words` và phụ đề karaoke. Cách xử lý: tìm model wav2vec2 tiếng Việt
      trên Hugging Face và truyền `model_name=` cho `load_align_model`; hoặc chuyển sang
      `faster-whisper` với `word_timestamps=True`. Ghi kết quả vào Nhật ký.
- [x] Lệnh `python run.py inspect --job X` đã có: in bảng giá trị thô (chat, mức nền chat,
      dB, dB trên nền, từ khóa) và điểm đã chuẩn hóa tại mỗi đỉnh.
- [ ] **Chất lượng ứng viên** (cần VOD thật): mở `candidates.json`, xem thử 5 ứng viên điểm
      cao nhất bằng ffplay. Nếu phần lớn là nhiễu, dùng `inspect` rồi chỉnh `refs`/`weights`.
- [ ] **Claude API thật**: kiểm tra `prompt_last.md` có hợp lý không; kích thước prompt
      (token vào). Nếu > 60k token, giảm `top_k` hoặc rút gọn transcript.
- [x] Lỗi API: `pipeline/claude_api.py` đặt `max_retries=3` (SDK tự backoff lũy thừa cho
      429/5xx) và dịch từng loại lỗi thành câu tiếng Việt nói rõ phải làm gì.
- [x] Cửa sổ cuối VOD ngắn hơn nửa `window_sec` đã bị bỏ (`compute_signals`), có test.
- [x] Log ghi ra `jobs/<job>/pipeline.log` ở mức DEBUG (kèm nguyên lệnh FFmpeg), console INFO.
- [x] Thêm: `usage.json` ghi token vào/ra và ước tính USD từng lần gọi API (mục 7.3 làm sớm).

**Tiêu chí xong:** có `final/highlight.mp4` từ VOD thật, người dùng thấy ít nhất một nửa
số clip Claude chọn là dùng được.

---

## 5. Tuần 2 — Định dạng dọc + phụ đề karaoke  ✅ ĐÃ XONG

> Khác đặc tả ban đầu ở ba chỗ, đều có lý do:
> 1. Toạ độ được làm tròn **xuống** số chẵn (không phải tròn gần nhất) — tròn lên có thể đẩy
>    vùng cắt vượt ra ngoài khung nguồn; test `test_vung_cat_luon_nam_trong_khung` bắt lỗi này.
> 2. Escape ASS: `{`, `}`, `\` được đổi thành `(`, `)`, `/` chứ không escape, vì libass không
>    có cách escape đáng tin cậy cho ba ký tự này. Lời nói tiếng Việt gần như không chứa chúng.
> 3. Phần "gửi phụ đề cho Haiku sửa lỗi chính tả" (cuối 5.2) **chưa làm** — để lại cho sau,
>    vì cần đo trên transcript thật mới biết có đáng không.

### 5.1 Layout dọc (1080×1920)

Module mới: `pipeline/layout.py` (hàm thuần dựng filtergraph) + mở rộng `s7_render.py`.

Preset streamer đã có `facecam: {x, y, w, h}` (tọa độ trên khung 1920×1080). Thêm:

```yaml
doc:
  kieu: cam_tren          # cam_tren | khong_cam
  gameplay_center_x: 960  # tâm vùng cắt gameplay theo chiều ngang
  ti_le_cam: 0.32         # facecam chiếm 32% chiều cao khung dọc
```

- **cam_tren**: facecam cắt từ preset → scale rộng 1080, cao `round(1920*ti_le_cam)` (giữ
  tỉ lệ bằng cách crop thêm nếu cần); gameplay cắt vùng có tỉ lệ `1080 : (1920 - h_cam)`
  quanh `gameplay_center_x`, full chiều cao nguồn → scale về 1080×(1920 − h_cam); `vstack`.
- **khong_cam** (streamer không bật cam): nền là chính khung hình phóng to + `boxblur`,
  gameplay giữ tỉ lệ đặt giữa.
- Nguồn không phải 1920×1080: đọc kích thước bằng `ffprobe`, quy đổi tọa độ preset theo tỉ lệ.
- Hàm `build_vertical_filter(src_w, src_h, preset) -> str` là hàm thuần, có test so khớp chuỗi
  và kiểm tra kích thước đầu ra luôn chẵn (libx264 yêu cầu).

### 5.2 Phụ đề karaoke (.ass)

Module mới: `pipeline/subtitles.py`.

- Input: `words.json` lọc trong khoảng `[clip.start, clip.end]`, đổi về thời gian tương đối.
- Gom từ thành dòng: tối đa ~5 từ hoặc ~28 ký tự; ngắt dòng khi khoảng lặng > 0.6s.
- Mỗi dòng một `Dialogue`; hiệu ứng tô chữ theo từ bằng tag `\k<centiseconds>` (tính từ
  độ dài mỗi từ + khoảng lặng trước nó). Có thể dùng thêm `\t` để phóng nhẹ từ đang nói.
- Escape ký tự đặc biệt trong ASS: `{`, `}`, `\`. Test riêng cho việc này.
- Style mặc định cho dọc: font hỗ trợ đầy đủ dấu tiếng Việt (ví dụ **Be Vietnam Pro** hoặc
  **Roboto** — đặt file font trong `assets/fonts/` và truyền `fontsdir`), cỡ ~80, viền 5,
  `PlayResX=1080, PlayResY=1920`, đặt ở ranh giới facecam/gameplay (`MarginV`). Style cho
  ngang: cỡ nhỏ hơn, đặt dưới.
- Burn bằng filter `subtitles=`/`ass=` của FFmpeg. **Cảnh báo Windows**: đường dẫn trong
  filter phải escape dấu `:` và `\` (`C\:/path/file.ass`). Cách an toàn nhất: chạy FFmpeg
  với `cwd` là thư mục chứa file `.ass` và dùng tên file tương đối.
- Tùy chọn (bật bằng cờ): gửi các dòng phụ đề cho Claude Haiku sửa lỗi chính tả ASR, **giữ
  nguyên số từ** để không lệch timestamp; `validate` số từ, lệch thì dùng bản gốc.
  Prompt đặt ở `prompts/fix_subtitles.md`.

### 5.3 CLI

`python run.py render --job X --format ngang|doc|ca-hai [--preview]`. Output:
`final/c01_ngang.mp4`, `final/c01_doc.mp4`.

**Tiêu chí xong:** clip dọc 30 giây có facecam trên/gameplay dưới đúng vị trí, phụ đề
tiếng Việt đủ dấu, chữ tô theo lời nói lệch không quá ~0.2s.

---

## 6. Tuần 3 — Thư viện meme & chèn meme tự động

### 6.1 Thư viện

`meme_library/library.jsonl` (đã có mẫu). Bổ sung trường `tags` (dùng để lọc theo
`meme_cam` của preset) và `am_luong` (hệ số âm lượng, mặc định 1.0).

Script `python run.py meme-tag`:
- Ảnh: gửi ảnh cho Claude Haiku (vision) → gợi ý `dung_khi` + `tags`.
- Video phông xanh: trích frame giữa bằng FFmpeg → gửi như ảnh.
- SFX: Claude không nghe được âm thanh → chỉ liệt kê các file còn thiếu mô tả để người điền.
- **Không ghi đè** trường người đã điền tay. Chỉ điền trường còn trống.
- Chuẩn hóa âm lượng mọi SFX một lần về ~ −16 LUFS (`loudnorm`), lưu bản chuẩn hóa cạnh bản gốc.

### 6.2 Chọn meme — `pipeline/s5_memes.py`

- Chạy cho từng clip đã duyệt. Prompt `prompts/insert_memes.md`.
- Input cho Claude: transcript theo từ của clip (thời gian tương đối), chat trong clip,
  thư viện đã lọc bỏ meme có tag cấm, `mat_do_meme_sec`, phong cách kênh, ví dụ phản hồi
  `kind: "meme"`.
- Tool `submit_memes`, mỗi phần tử:
  `{id, t, vi_tri: giua|tren_trai|tren_phai|duoi_trai|duoi_phai|facecam, kich_thuoc: 0.2–0.6, ly_do}`.
- `validate_memes` (hàm thuần, có test):
  - `id` có trong thư viện và không bị cấm;
  - `t` trong `[0.3, thời lượng clip − dai]`;
  - khoảng cách giữa hai meme ≥ `mat_do_meme_sec`;
  - ảnh/video meme không đè vùng phụ đề;
  - SFX: dời `t` về cuối từ gần nhất nếu trong vòng 0.5s (meme hài nhất khi rơi ngay sau câu nói).
- Output: `jobs/<job>/memes/c01.json`.

### 6.3 Dựng meme — `pipeline/meme_render.py`

Dựng filtergraph bằng code (hàm thuần `build_meme_filter(events, layout) -> (filter, inputs)`),
**không** viết tay. Thứ tự lớp cho mỗi clip:

1. Cắt clip → 2. hiệu ứng lên nguồn (`zoom_mat`: phóng vào vùng facecam; `rung_man_hinh`:
   crop với offset dao động theo `t`) → 3. layout (ngang/dọc) → 4. overlay ảnh/GIF/phông xanh
   theo tọa độ khung đầu ra (`overlay=...:enable='between(t,a,b)'`; phông xanh dùng
   `colorkey` + `setpts=PTS+t/TB`) → 5. phụ đề (luôn nằm trên meme) → 6. trộn âm SFX
   (`adelay` + `amix=normalize=0`, áp `am_luong`).

Nếu filtergraph FFmpeg trở nên quá phức tạp cho hiệu ứng động (bật nảy, easing), cân nhắc
Remotion — nhưng **hỏi người dùng trước**, vì thêm Node.js vào dự án.

### 6.4 Duyệt

Bản preview có meme; ở bước duyệt cho phép bỏ từng meme. Ghi phản hồi `kind: "meme"`.

**Tiêu chí xong:** clip có 2–5 meme, đúng thời điểm, không đè phụ đề, âm lượng SFX đồng đều.

---

## 7. Tuần 4 — Trang duyệt web, metadata, hoàn thiện

### 7.1 Trang duyệt web — `python run.py review-web --job X`

- Server cục bộ (ưu tiên stdlib `http.server`; nếu cần, Flask — hỏi trước), mở trình duyệt.
- Mỗi clip: video preview, tiêu đề, lý do, điểm; nút Giữ/Loại; ô ghi chú; danh sách meme
  có thể bỏ từng cái; ô "sửa bằng lời" (ví dụ "cắt sớm 3 giây, bỏ meme thứ 2") → gửi
  Claude sửa JSON → validate → render lại preview clip đó.
- Lưu ngay vào `clips.json`, `memes/*.json`, `feedback/examples.jsonl`.

### 7.2 Metadata — `pipeline/s8_metadata.py`

- Tiêu đề (3 phương án), mô tả, tags, chapter cho `highlight.mp4` (tính từ thứ tự và thời
  lượng các clip). Prompt `prompts/metadata.md`. Dùng Haiku.
- Thumbnail: trích ~12 frame tại các đỉnh âm lượng trong clip điểm cao nhất; Claude (vision)
  chọn 3 frame có biểu cảm streamer rõ nhất. Lưu `final/thumbs/`.
- Output `final/metadata.json`.

### 7.3 Hoàn thiện

- `jobs/<job>/usage.json`: token vào/ra theo từng bước + ước tính chi phí.
- Lệnh `python run.py status --job X`: bước nào đã xong, bao nhiêu clip duyệt, chi phí.
- Chạy song song render nhiều clip (`concurrent.futures`, giới hạn theo số nhân CPU).
- Cập nhật README cho người dùng cuối.

---

## 8. Checklist tổng

- [x] Tuần 1: tải, tiền xử lý, ứng viên, Claude chọn clip, duyệt terminal, render ngang
- [~] Tuần 1.5: phần code đã gia cố xong (doctor, inspect, log file, usage.json, retry API,
      cửa sổ cuối, align_model). **Còn lại: chạy thật trên VOD của bạn** — xem mục 4.
- [x] Tuần 2: layout dọc (5.1)
- [x] Tuần 2: phụ đề karaoke (5.2) — trừ phần Haiku sửa chính tả
- [x] Tuần 2: CLI định dạng (5.3)
- [ ] Tuần 3: gắn nhãn thư viện meme (6.1)
- [ ] Tuần 3: chọn meme + validate (6.2)
- [ ] Tuần 3: dựng meme (6.3)
- [ ] Tuần 3: duyệt meme (6.4)
- [ ] Tuần 4: trang duyệt web (7.1)
- [ ] Tuần 4: metadata + thumbnail (7.2)
- [ ] Tuần 4: hoàn thiện (7.3)

---

## 9. Nhật ký tiến độ

> Claude Code: thêm một mục sau mỗi phiên làm việc — đã làm gì, quyết định gì, vấn đề còn tồn tại.
> Mới nhất ở trên cùng.

### 2026-09-10 (phiên 2) — Gia cố tuần 1.5 (phần code) + trọn tuần 2 (Claude Code)

**Môi trường.** Python trên PATH là bản *embeddable* 3.13 (không có `venv`, không cài được thư
viện) → dựng `.venv` bằng Python 3.11 có sẵn ở
`C:\Users\ADMIN\AppData\Local\Programs\Python\Python311`. Cài `requirements-dev.txt`.
Cài FFmpeg 9.0.1 bằng `winget install Gyan.FFmpeg`.
**Chạy mọi lệnh qua `.venv\Scripts\python.exe`** (venv chưa được activate sẵn).
Chưa cài torch/whisperx (nặng, cần GPU) — cài khi bắt đầu chạy VOD thật.

**Đã làm — gia cố (mục 4).**
- `run.py doctor` — bảng kiểm tra môi trường 3 mức (HỎNG / THIẾU / OK), tìm cả binary trong
  `Scripts/` của venv.
- `run.py inspect --job X` — bảng điểm từng tín hiệu tại mỗi đỉnh; `combine` được tách thành
  `combine_parts` để lấy được đóng góp của từng tín hiệu.
- `pipeline/claude_api.py` — lớp bao SDK: `max_retries=3`, `call_tool`, dịch lỗi sang tiếng Việt.
- `usage.json` (token + ước tính USD) và `pipeline.log` (mức DEBUG, kèm nguyên lệnh FFmpeg).
- Bỏ cửa sổ cuối VOD khi ngắn hơn nửa `window_sec`; `asr.align_model` cấu hình được.

**Đã làm — tuần 2.** `pipeline/layout.py`, `pipeline/subtitles.py`, `s7_render.py` viết lại,
`--format ngang|doc|ca-hai`, khối `phu_de` trong `settings.yaml`, khối `doc` trong preset
streamer, `assets/fonts/` + tự truyền `fontsdir`. 13 → **58 test**, đều xanh.

**Quyết định đáng nhớ.**
- *Không* tự viết vòng retry: SDK Anthropic đã tự backoff lũy thừa cho 429/5xx, chỉ cần
  `max_retries=3` khi tạo client.
- Toạ độ và kích thước làm tròn **xuống** số chẵn, không phải tròn gần nhất. Tròn gần nhất
  từng đẩy vùng cắt gameplay ra ngoài khung (cho ra `y=2, h=1080` trên nguồn cao 1080) — test
  `test_vung_cat_luon_nam_trong_khung` bắt được.
- Đường dẫn trong filter FFmpeg: chạy FFmpeg với `cwd` = thư mục `subs/`, truyền tên file .ass
  tương đối và `fontsdir` tương đối dùng dấu `/`. Nhờ vậy chuỗi filter không bao giờ chứa `:`
  hay `\` — né hẳn lỗi escape trên Windows thay vì đi tìm cách escape cho đúng.
- Sửa `models.cheap` thành `claude-haiku-4-5` (bỏ hậu tố ngày). Bảng giá đặt ở `common.PRICING`,
  khớp theo tiền tố nên id có hậu tố ngày vẫn tính đúng chi phí.

**Đã chạy thật (dựng lại được).** Video tự sinh, không cần VOD:

```bash
mkdir -p jobs/smoketest/raw
ffmpeg -y -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=20 \
       -f lavfi -i "sine=frequency=440:duration=20" \
       -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest \
       jobs/smoketest/raw/vod.mp4
# rồi tạo tay: job.json, transcript/words.json, clips.json (1 clip approved: true)
python run.py render --job smoketest --format ca-hai
```

Kết quả: `c01_ngang.mp4` 1920×1080, `c01_doc.mp4` 1080×1920, preview 270×480; facecam trên /
gameplay dưới đúng vị trí; phụ đề đủ dấu tiếng Việt. Tại giây thứ 2 các từ đã nói hiện màu
vàng, từ chưa tới màu trắng — tag `\k` hoạt động đúng.

**Còn tồn tại.**
- Chưa chạy trên VOD thật: WhisperX tiếng Việt, Claude API thật, yt-dlp live chat.
- `facecam` trong `streamer_example.yaml` vẫn là số ví dụ — phải đo lại trên một khung hình
  thật trước khi tin kết quả bản dọc.
- Chưa làm: dùng Haiku sửa lỗi chính tả phụ đề (đoạn cuối mục 5.2).

**Việc tiếp theo:** hoặc chạy thật tuần 1.5 trên một VOD 30–60 phút, hoặc sang tuần 3 (meme).

### 2026-09-10 — Khởi tạo (Claude trên claude.ai)
- Dựng khung repo và pipeline tuần 1; 13 test xanh; chạy thử đầu-cuối với video giả lập.
- Quyết định: chuẩn hóa tín hiệu theo mức tham chiếu cố định thay vì phân vị (phân vị đẩy
  nhiễu chat lên ngang đỉnh thật); gộp tin chat trùng nội dung khi dựng prompt để tiết kiệm token.
- Chưa rõ: nền tảng stream (hỗ trợ cả hai), layout facecam, cấu hình máy người dùng.
