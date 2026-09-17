# Hướng dẫn sử dụng automeme

> Cài đặt nhanh xem [`README.md`](../README.md). File này giải thích từng bước: cài đặt, kiểm
> tra môi trường, cấu hình, quy trình làm video, xử lý sự cố, và cách làm việc cùng Claude Code.
>
> **Cập nhật: 2026-09-12 — MVP đã có đủ `transcribe`, `analyze`, tìm meme, timeline và
> `run`.** Lộ trình đầy đủ: [`HANDOFF.md`](HANDOFF.md) mục 5.

## Mục lục

1. [automeme làm gì, hiện làm được đến đâu](#1-automeme-làm-gì-hiện-làm-được-đến-đâu)
2. [Cài đặt từ đầu trên Windows](#2-cài-đặt-từ-đầu-trên-windows)
3. [Kiểm tra môi trường: `automeme doctor`](#3-kiểm-tra-môi-trường-automeme-doctor)
4. [Cấu hình](#4-cấu-hình)
5. [Quy trình làm một video](#5-quy-trình-làm-một-video)
6. [Log và cách báo lỗi](#6-log-và-cách-báo-lỗi)
7. [Xử lý sự cố thường gặp](#7-xử-lý-sự-cố-thường-gặp)
8. [Làm việc cùng Claude Code](#8-làm-việc-cùng-claude-code)
9. [Dành cho người phát triển](#9-dành-cho-người-phát-triển)
10. [Code cũ trong `legacy/`](#10-code-cũ-trong-legacy)

---

## 1. automeme làm gì, hiện làm được đến đâu

```
video.mp4
  → audio.wav          FFmpeg tách tiếng
  → transcript.json    faster-whisper: lời thoại + thời điểm từng từ
  → analysis.json      Ollama: câu nào đáng chèn meme, cần phản ứng kiểu gì
  → ứng viên meme      tìm theo ý nghĩa trong thư viện meme của bạn
  → timeline.json      meme nào, lúc nào, ở góc nào — bạn sửa được
  → output.mp4         FFmpeg dựng
```

Ba nguyên tắc: AI chỉ **đề xuất**; code chặn các lỗi của AI (meme quá dày, quá dài, trùng
lặp, sai thời điểm); bạn **duyệt `timeline.json`** trước khi render.

| Lệnh | Việc | Trạng thái |
|---|---|---|
| `automeme doctor` | Kiểm tra môi trường | ✅ dùng được |
| `automeme download` | Tải video (hoặc một đoạn) từ YouTube vào `data/input/` | ✅ dùng được |
| `automeme transcribe` | Video → transcript (lời thoại + thời điểm từng từ) | ✅ dùng được |
| `automeme inspect` | Xem lại và kiểm tra timeline | ✅ dùng được |
| `automeme render` | Timeline → video đã chèn meme | ✅ dùng được |
| `automeme analyze` | Transcript → khoảnh khắc nên chèn meme | ✅ dùng được |
| `automeme run` | Trọn quy trình bằng một lệnh | ✅ dùng được |
| `automeme review` | Duyệt timeline bằng giao diện web local | ✅ dùng được |
| `automeme studio` | Giao diện đầy đủ: nhập video → chạy AI → biên tập → tải output | ✅ dùng được |

---

## 2. Cài đặt từ đầu trên Windows

Mọi lệnh chạy trong **PowerShell**, tại thư mục gốc dự án. Sau mỗi bước có lệnh kiểm tra.

### 2.1 Python 3.11

```powershell
winget install Python.Python.3.11
py -0p        # liệt kê các bản Python đã cài — phải thấy dòng -V:3.11
```

> **Máy có nhiều bản Python:** lệnh `python` có thể trỏ tới một bản khác, ví dụ bản
> *embeddable* không tạo được môi trường ảo. Luôn tạo venv bằng `py -3.11`, không dùng `python`.

### 2.2 FFmpeg

```powershell
winget install Gyan.FFmpeg
```

**Đóng và mở lại terminal** (để nhận PATH mới), rồi kiểm tra: `ffmpeg -version`.

### 2.3 Môi trường ảo và cài automeme

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

- Kích hoạt thành công thì đầu dòng lệnh có `(.venv)`. **Mỗi terminal mới phải kích hoạt lại.**
- PowerShell báo *running scripts is disabled*: chạy một lần
  `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` rồi kích hoạt lại.
- Không muốn kích hoạt: gọi thẳng `.\.venv\Scripts\automeme.exe <lệnh>`.
- `-e` là cài kiểu *editable*: sửa code trong `src/` có hiệu lực ngay. Chỉ cần cài lại khi
  sửa `pyproject.toml`.
- Luôn dùng `python -m pip` thay vì `pip` để chắc chắn cài vào đúng Python của venv.

### 2.4 Tiếng Việt trên console

```powershell
setx PYTHONUTF8 1
```

Mở terminal mới là có hiệu lực. automeme tự ép UTF-8 cho log của nó, nhưng biến này giúp mọi
script Python khác hiển thị đúng dấu.

### 2.5 File `.env`

```powershell
Copy-Item .env.example .env
```

Mở `.env` và sửa theo máy của bạn (xem [4.2](#42-env--cấu-hình-của-máy)). **Không bao giờ
commit `.env`** (đã có trong `.gitignore`).

### 2.6 Cài thêm theo từng giai đoạn

| Khi nào | Cần gì | Cách cài |
|---|---|---|
| Lệnh `transcribe` | faster-whisper | **Có GPU NVIDIA:** `python -m pip install -e ".[asr-cuda]"` — kèm sẵn cuBLAS + cuDNN (~1 GB), không cần cài CUDA Toolkit riêng. **Không có GPU:** `python -m pip install -e ".[asr]"` rồi đặt `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8` trong `.env` |
| Lệnh `analyze` | SDK + Ollama + model | `python -m pip install -e ".[llm]"`; `winget install Ollama.Ollama`; rồi `ollama pull qwen3:8b` |
| Lệnh `run` | Thư viện meme của bạn | chép file vào `assets/` — xem [5.3](#53-thư-viện-meme) |
| Tùy chọn | Docker Desktop (cho Meme Search) | `winget install Docker.DockerDesktop` |
| Tùy chọn | Claude thay cho Ollama | `python -m pip install -e ".[claude]"`, đặt `LLM_BACKEND=claude` và `ANTHROPIC_API_KEY` trong `.env` |

Kiểm tra Ollama sau khi cài:

```powershell
ollama list            # phải thấy qwen3:8b
ollama run qwen3:8b    # gõ thử một câu tiếng Việt, gõ /bye để thoát
```

---

## 3. Kiểm tra môi trường: `automeme doctor`

```powershell
automeme doctor                    # cấu hình mặc định
automeme doctor --profile subtle   # kiểm tra kèm một profile
```

Ví dụ kết quả trên máy RTX 4060 (rút gọn):

```
KIỂM TRA MÔI TRƯỜNG
  [  OK  ]  Python >= 3.10  3.11.9 — ...\.venv\Scripts\python.exe
  [  OK  ]  Cấu hình        profile: default
  [THIẾU ]  .env            chưa có — đang dùng giá trị mặc định; tạo: Copy-Item .env.example .env
  [  OK  ]  ffmpeg            9.0.1-full_build-www.gyan.dev — ...
  [  OK  ]  faster-whisper    đã cài
  [  OK  ]  GPU NVIDIA        NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB)
  [  OK  ]  CTranslate2 CUDA  thấy 1 GPU
  [THIẾU ]  Ollama            không kết nối được http://localhost:11434 (...); cần cho `analyze`
  ...
Bắt buộc: tất cả đạt.
Thiếu nhưng chưa chặn: .env, Ollama
```

Ba mức: `[  OK  ]` đạt · `[THIẾU ]` chưa cần cho bước hiện tại · `[ HỎNG ]` phải sửa (lệnh
thoát với mã 1, dùng được trong script).

| Dòng | Kiểm tra gì | Không đạt thì |
|---|---|---|
| Python >= 3.10 | Phiên bản Python đang chạy automeme | Tạo lại venv bằng `py -3.11` |
| Cấu hình | `configs/`, profile và `.env` hợp lệ | Đọc thông báo, sửa đúng khóa bị nêu tên — xem [4.5](#45-khi-cấu-hình-sai) |
| .env | Đã có file `.env` chưa | `Copy-Item .env.example .env` |
| ffmpeg, ffprobe | Có trong PATH, phiên bản bao nhiêu | `winget install Gyan.FFmpeg`, mở lại terminal |
| faster-whisper | Đã cài chưa (cần cho `transcribe`) | `python -m pip install -e ".[asr-cuda]"`, hoặc `".[asr]"` nếu chạy CPU |
| GPU NVIDIA | `nvidia-smi` có thấy GPU không | Cài driver NVIDIA. Không có GPU: `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8` |
| CTranslate2 CUDA | Lõi của faster-whisper có dùng được GPU không (chỉ hiện khi `WHISPER_DEVICE` khác `cpu`) | Cài `".[asr-cuda]"`. Thiếu cuDNN thì tới lúc nạp model mới lộ, thông báo lỗi sẽ nói rõ cách sửa |
| Ollama | Server ở `OLLAMA_HOST` có chạy, đã tải model chưa | Mở ứng dụng Ollama; `ollama pull <model>` |
| Claude API | Chỉ hiện khi `LLM_BACKEND=claude`: đã cài thư viện, có key chưa | Xem [2.6](#26-cài-thêm-theo-từng-giai-đoạn) |
| yt-dlp | Đã cài chưa, có quá 90 ngày tuổi không | `python -m pip install -U yt-dlp` — YouTube đổi liên tục nên bản cũ hay hỏng |
| JS runtime | Có Deno/Node/Bun, có gói `yt-dlp-ejs` và gói này **khớp đúng** bản yt-dlp yêu cầu | Thiếu runtime: `winget install DenoLand.Deno`. Thiếu hoặc lệch `yt-dlp-ejs`: chạy lệnh `pip install "yt-dlp-ejs==…"` mà dòng này in ra |
| docker, git | Có trong PATH | Docker chỉ cần cho Meme Search |
| Console UTF-8 | Console hiển thị được tiếng Việt | `setx PYTHONUTF8 1`, mở terminal mới |

---

## 4. Cấu hình

### 4.1 Bốn lớp, lớp sau đè lớp trước

```
configs/default.yaml  →  configs/<profile>.yaml  →  .env / biến môi trường  →  cờ CLI
```

Cách chia: tham số của **máy** (model, GPU hay CPU, địa chỉ Ollama) để trong `.env`; tham số
**dựng video** (mật độ meme, ngưỡng…) để trong profile. Mọi khóa có thể đặt, kèm chú thích,
nằm trong `configs/default.yaml`.

### 4.2 `.env` — cấu hình của máy

| Biến | Mặc định | Khi nào đổi |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | Máy yếu hoặc chạy CPU: `medium` / `small` — nhanh hơn nhưng nghe tiếng Việt kém hơn |
| `WHISPER_DEVICE` | `cuda` | Không có GPU NVIDIA: `cpu` |
| `WHISPER_COMPUTE_TYPE` | `float16` | CPU: `int8`; GPU ít VRAM: `int8_float16` |
| `WHISPER_BEAM_SIZE` | `5` | Giảm để nhanh hơn |
| `WHISPER_VAD_FILTER` | `true` | Đặt `false` khi giọng nói nhỏ và bị cắt mất câu |
| `WHISPER_CONDITION_ON_PREVIOUS_TEXT` | `false` | Đặt `true` nếu muốn Whisper dùng câu trước làm ngữ cảnh (chính xác hơn một chút nhưng dễ lặp chữ) |
| `LLM_BACKEND` | `ollama` | `claude` để dùng Claude API |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama chạy ở máy khác |
| `OLLAMA_MODEL` | `qwen3:8b` | GPU dưới 8 GB VRAM: `qwen3:4b` |
| `MEME_TIMING_DELAY` | `0.15` | Độ trễ từ cuối câu đến lúc meme bắt đầu; thường giữ 0.10–0.30 giây |
| `MEME_LIBRARY_FILE` | `assets/memes/library.jsonl` | Metadata cho thư viện local |
| `SFX_ENABLED`, `SFX_VOLUME` | `true`, `0.35` | Bật/tắt SFX tự động và chỉnh master volume |
| `SFX_LIBRARY_FILE` | `assets/sfx/library.jsonl` | Metadata thư viện sound effect local |
| `MEME_SEARCH_BASE_URL`, `_TOKEN`, `_TOP_K` | — | Khi dùng Meme Search API v1 |
| `MEME_SEARCH_MAX_DOWNLOAD_MB` | `25` | Giới hạn kích thước mỗi media tải từ API |
| `OUTPUT_CRF` | `18` | Nhỏ hơn = đẹp hơn, file to hơn |
| `OUTPUT_PRESET` | `medium` | `fast` / `veryfast` để render nhanh hơn |
| `LOG_LEVEL` | `INFO` | `DEBUG` để xem chi tiết trên console |

Để trống một biến = dùng giá trị trong `configs/`.

> **VRAM 8 GB:** Whisper `large-v3` và `qwen3:8b` không nạp cùng lúc được, nên pipeline chạy
> lần lượt. Nếu vẫn thiếu VRAM: `OLLAMA_MODEL=qwen3:4b` hoặc `WHISPER_COMPUTE_TYPE=int8_float16`.

Các biến dựng video (`MEME_COOLDOWN`, `MAX_MEMES_PER_MINUTE`…) trong `.env.example` được để
dạng comment. Bỏ comment một dòng là ghi đè giá trị đó cho **mọi** profile — `--profile` sẽ
không đổi được nó nữa.

### 4.3 Profile — phong cách dựng

| Profile | Meme/phút tối đa | Cooldown | Ngưỡng confidence | Meme hiện trong |
|---|---|---|---|---|
| *(mặc định)* | 5 | 7 giây | 0.65 | 0.8–2.5 giây |
| `subtle` | 2 | 12 giây | 0.8 | 0.8–1.5 giây |
| `funny` | 5 | 6 giây | 0.65 | 0.8–2.5 giây |
| `chaotic` | 9 | 3 giây | 0.5 | 0.8–2.5 giây |

- **`max_memes_per_minute`** — trần mật độ. Số meme tối đa của cả video là
  `max(1, làm tròn xuống(thời lượng tính bằng phút × giá trị này))`, nên video ngắn vẫn được
  ít nhất 1 meme (video 12 giây với giá trị 5 → tối đa 1 meme).
- **`cooldown`** — khoảng cách tối thiểu giữa hai meme. Với 7 giây: có meme ở 00:05 thì ứng
  viên ở 00:08 bị loại, ứng viên ở 00:13 được giữ.
- **`threshold`** — LLM tự chấm độ chắc chắn 0–1 cho mỗi khoảnh khắc; thấp hơn ngưỡng thì bỏ.
- **`duration_min` / `duration_max`** — meme hiện trên màn hình bao lâu.

> Ngưỡng, cooldown và mật độ đã được áp dụng khi `analyze`; duration và timing được code kẹp
> lại trước khi ghi `analysis.json`.

**Tạo profile riêng:**

```powershell
Copy-Item configs\funny.yaml configs\kenh_cua_toi.yaml
# mở file, sửa giá trị — chỉ cần giữ những khóa muốn khác mặc định
automeme doctor --profile kenh_cua_toi
```

Tên profile chỉ gồm chữ, số, `_`, `-` — nên dùng không dấu.

### 4.4 Cờ CLI

Đè tất cả, chỉ cho một lần chạy:

```powershell
automeme run data\input\video.mp4 --profile funny --force
```

### 4.5 Khi cấu hình sai

automeme dừng và nói rõ khóa nào sai, giá trị đang là gì — không lặng lẽ bỏ qua. Ví dụ đặt
`MEME_SCORE_THRESHOLD=1.5` trong `.env`:

```
[ HỎNG ]  Cấu hình  Cấu hình không hợp lệ (giá trị có thể đến từ configs/, .env hoặc cờ CLI):
                    - editing.threshold: Input should be less than or equal to 1 (đang là '1.5')
```

Profile không tồn tại:

```
[ HỎNG ]  Cấu hình  Không có profile 'khong_co'. Có sẵn: chaotic, funny, subtle
```

Thông báo dùng tên khóa trong `configs/` (`editing.threshold`). Muốn biết biến `.env` nào ứng
với khóa đó, xem bảng `ENV_MAP` trong `src/automeme/config.py` — ví dụ `editing.threshold` ↔
`MEME_SCORE_THRESHOLD`. Gõ nhầm tên khóa trong YAML (như `cooldwon`) cũng bị báo lỗi
*Extra inputs are not permitted*.

---

## 5. Quy trình làm một video

### 5.1 Chọn video

MVP nhắm tới video tiếng Việt **30–90 giây**, có hội thoại rõ, định dạng `.mp4`, `.mov` hoặc
`.mkv`. Chép vào `data/input/`, hoặc tải thẳng từ YouTube như dưới đây.

**Tải từ YouTube** (dùng [yt-dlp](https://github.com/yt-dlp/yt-dlp), mã nguồn mở, đã cài sẵn):

```powershell
automeme download "https://www.youtube.com/watch?v=..." --from 1:20 --to 2:40
automeme download "https://youtu.be/..."                    # cả video (nếu ngắn hơn 10 phút)
automeme run "https://youtu.be/..." --from 1:20 --to 2:40 --profile funny   # tải xong chạy luôn
```

- Nhận link `watch?v=`, `youtu.be/`, `shorts/`, `live/`, kể cả khi dán thiếu `https://`. Link
  playlist phải mở một video cụ thể rồi copy link của video đó. **Chỉ nhận YouTube**: Studio chạy
  trên máy bạn, nếu nhận URL bất kỳ thì có thể bị lợi dụng để tải từ địa chỉ tùy ý.
- `--from`/`--to` nhận `90`, `1:30`, `1:02:03.5`; bỏ trống một đầu thì lấy từ đầu hoặc tới hết.
  Chỉ tải đúng đoạn đó, cắt đúng khung hình — tiết kiệm mạng và ổ đĩa.
- File ra: `data/input/<tieu-de>-<mã video>[-<từ>s-<đến>s].mp4`, H.264 + AAC tối đa 1080p.
  Kèm `<tên>.source.json` ghi link, kênh, **giấy phép**, đoạn đã cắt và thời điểm tải. Tải lại
  cùng link và cùng đoạn thì bỏ qua; thêm `--force` để tải lại.
- Giới hạn trong `configs/default.yaml`, mục `download`: `max_height` (1080),
  `max_duration` (600 giây — video hoặc đoạn dài hơn thì bị chặn trước khi tải),
  `max_filesize_mb` (1024), `js_runtime` (`auto`).

> **Bản quyền:** điều khoản của YouTube hạn chế việc tải video. Chỉ tải video bạn sở hữu hoặc có
> quyền dùng. Nếu video không ghi giấy phép Creative Commons, automeme vẫn tải nhưng cảnh báo;
> giấy phép được lưu trong `.source.json` để bạn kiểm tra lại trước khi đăng.

> **JS runtime:** YouTube bắt trình tải giải thử thách bằng JavaScript. Cần hai thứ: một runtime
> (automeme tự dùng Deno, Node hoặc Bun nếu máy có — `download.js_runtime: auto`) và gói script
> `yt-dlp-ejs` (cài sẵn cùng automeme). Thiếu một trong hai thì vẫn tải được nhưng YouTube có thể
> bóp tốc độ hoặc ẩn bớt định dạng; `automeme doctor` báo ở dòng **JS runtime**.

> **Cập nhật khi tải bắt đầu lỗi:** YouTube thay đổi thường xuyên. Chạy
> `python -m pip install -U yt-dlp`, rồi `automeme doctor`: nếu dòng **JS runtime** báo
> `yt-dlp-ejs … không khớp`, chạy đúng lệnh cài mà nó in ra (script phải khớp đúng bản yt-dlp).

**Tải lại livestream của bạn:**

- Bản ghi livestream thường dài hàng giờ, nên luôn tải **một đoạn**: mở VOD, tìm khoảnh khắc
  muốn dựng, ghi mốc thời gian rồi dùng `--from/--to` (ví dụ `--from 1:02:30 --to 1:04:00`).
  Chỉ đoạn đó được tải, không phải cả buổi stream.
- Ngay sau khi live kết thúc, YouTube còn **xử lý bản ghi** (vài chục phút tới vài giờ). Lúc đó
  automeme báo "Buổi live vừa kết thúc…" — đợi xử lý xong rồi tải lại.
- VOD để chế độ **Không công khai** tải được bằng link; để **Riêng tư** thì không (cần đăng nhập,
  chưa hỗ trợ).
- Video của chính bạn thường không ghi giấy phép Creative Commons nên sẽ có dòng cảnh báo bản
  quyền — với nội dung của bạn thì có thể bỏ qua.

### 5.2 Các bước

```powershell
automeme transcribe data\input\video.mp4    # lời thoại — đã dùng được
automeme analyze    data\input\video.mp4    # khoảnh khắc nên chèn meme — đã dùng được
automeme inspect    <file timeline>         # xem lại trước khi render — đã dùng được
automeme review     data\input\video.mp4    # duyệt bằng giao diện local
automeme render     data\input\video.mp4    # dựng video — đã dùng được
# hoặc một lệnh cho tất cả:
automeme run data\input\video.mp4 --profile funny
```

Mỗi bước lưu kết quả vào `data/` và **bỏ qua khi cache còn khớp**. Manifest nội bộ trong
`data/cache/manifests/` theo dõi video, transcript, prompt, cấu hình, timeline và asset: đổi một
đầu vào chỉ làm lại bước bị ảnh hưởng cùng các bước phía sau. Timeline chỉnh tay được giữ nguyên;
`--force` mới cho phép sinh lại và ghi đè nó.

**Lệnh `transcribe`:**

```powershell
automeme transcribe data\input\video.mp4
automeme -v transcribe data\input\video.mp4        # log chi tiết, có phần trăm tiến độ
automeme transcribe data\input\video.mp4 --force   # nhận dạng lại từ đầu
```

Chạy xong in ngay số đoạn, số từ và vài câu đầu để bạn kiểm tra. Ba file được tạo:

| File | Ý nghĩa |
|---|---|
| `data/cache/<tên-video>-<hash>/audio.wav` | Audio mono 16 kHz tách từ video |
| `data/cache/<tên-video>-<hash>/transcript-<mã>.json` | Cache theo tham số ASR — đổi model hoặc ngôn ngữ sẽ tạo file mới, không dùng nhầm bản cũ |
| `data/transcripts/<tên-video>.json` | Bản mới nhất, các bước sau đọc file này |

Nội dung transcript gồm `video`, `language`, `duration`, `model`, `segments` (mỗi câu có
`id`, `start`, `end`, `text`) và `words` (từng từ kèm `start`, `end` — dùng để canh meme rơi
đúng cuối câu).

Lần chạy đầu tải model về `C:\Users\<bạn>\.cache\huggingface`; bản `large-v3` khoảng 3 GB.
Muốn để ổ khác thì đặt biến môi trường `HF_HOME`. Nghe không ra chữ thì xem mục 4.2: đổi
`WHISPER_MODEL`, hoặc tắt VAD bằng `WHISPER_VAD_FILTER=false` khi giọng nói nhỏ.

**Lệnh `analyze`:**

```powershell
automeme analyze data\input\video.mp4
automeme -v analyze data\input\video.mp4        # xem tiến độ từng đoạn
automeme analyze data\input\video.mp4 --profile subtle
automeme analyze data\input\video.mp4 --force  # bỏ kết quả cũ, gọi LLM lại
```

Lệnh đọc `data/transcripts/<tên-video>.json`; chưa có thì thông báo chạy `transcribe` trước.
Mỗi câu được gửi cùng hai câu trước và một câu sau. LLM trả `insert_meme`, `insert_sfx`,
confidence, cảm xúc và các query tìm kiếm. Output sai schema được thử lại một lần; nếu vẫn sai chỉ bỏ
câu đó. Code tự đặt thời điểm ở cuối câu + 0,15 giây, kẹp duration, rồi áp confidence,
cooldown và số meme/phút theo profile. Kết quả:

```json
{
  "version": 1,
  "video": "video.mp4",
  "backend": "ollama",
  "model": "qwen3:8b",
  "opportunities": [
    {
      "segment_id": 2,
      "insert_meme": true,
      "confidence": 0.91,
      "trigger": "unexpected answer",
      "reason": "Câu trả lời đảo ngược kỳ vọng",
      "emotion": "bối rối",
      "reaction_type": "confused reaction",
      "search_query": "confused man reaction",
      "preferred_style": "reaction",
      "insert_sfx": true,
      "sfx_query": "awkward question",
      "timing": {"anchor": 8.73, "delay": 0.15, "duration": 1.5}
    }
  ]
}
```

`anchor` là cuối câu do code lấy từ transcript, không phải thời điểm tùy ý của LLM. `run`
dùng `search_query` để chọn asset và tạo timeline.

| Thư mục | Chứa |
|---|---|
| `data/input/` | Video gốc bạn chép vào |
| `data/temp/` | File tạm |
| `data/cache/` | Audio/transcript, media Meme Search và manifest invalidation từng bước |
| `data/transcripts/` | Transcript |
| `data/analysis/` | Cơ hội meme đã qua schema và bộ lọc cứng |
| `data/timelines/` | Timeline — file bạn duyệt và sửa |
| `data/output/` | Video hoàn chỉnh |
| `data/logs/` | `automeme.log` |

Toàn bộ `data/` không được commit.

### 5.3 Thư viện meme

Cách nhanh nhất là bấm **Kho meme → Cài bộ 100 meme** trong Studio, hoặc chạy:

```powershell
automeme install-memes             # tải đủ 100 template
automeme install-memes --limit 50  # chỉ lấy 50 template đầu
automeme install-gifs              # tải thêm 30 reaction GIF động
automeme install-gifs --limit 15   # chỉ lấy 15 GIF đầu
automeme install-sfx               # tải 30 sound effect Kenney CC0
automeme install-sfx --limit 15    # chỉ lấy 15 SFX đầu
```

Catalog cố định gồm 100 template phổ biến với taxonomy song ngữ về ngữ cảnh, cảm xúc và phong
cách. Lệnh tải từ HTTPS `i.imgflip.com`, kiểm tra MIME/kích thước, ghi file nguyên tử và có thể
chạy lại an toàn (file đã có được tái sử dụng). Ba template có nội dung nhạy cảm/bạo lực được
đặt `safe=false`, nên provider không bao giờ trả chúng cho pipeline tự động.

Bộ GIF dùng URL `raw.githubusercontent.com` được ghim vào SHA commit của hai kho nguồn. Trình
cài kiểm tra host/repository/revision allowlist, MIME `image/gif`, giới hạn 15 MB và phân tích
cấu trúc để chắc chắn file có ít nhất hai frame. Hai GIF có phụ đề thô tục hoặc nhân vật chính
trị được cài để người dùng có thể xem, nhưng đặt `safe=false`. Khi LLM trả
`preferred_style="animated"`, ranker cộng điểm phong cách cho các GIF này.

Ảnh/video riêng đặt trong `assets/memes/`, GIF có thể đặt trong `assets/gifs/`. Khi mở rộng,
nên có khoảng 200–500 meme chia theo cảm xúc: sốc, bối rối, ngượng, facepalm, hoảng, ăn mừng…
Media trong các thư mục này không được commit.

Bộ SFX gồm 30 âm OGG ngắn từ Kenney: impact, punch, metal, glass, fail, success, reveal,
whoosh, click, coin, door và sci-fi. Catalog gắn nhãn Việt–Anh, intensity, duration và âm lượng
khuyến nghị. Trình cài chỉ nhận HTTPS từ đúng repository/revision GitHub đã ghim, không theo
redirect, kiểm tra MIME, giới hạn 5 MB và header `OggS`. Asset là CC0 1.0; xem nguồn trong
`THIRD_PARTY_NOTICES.md`. File được lưu ở `assets/sfx/popular/`, metadata ở
`assets/sfx/library.jsonl`; cả hai đều không commit.

Không bắt buộc có metadata: local provider vẫn quét `.png`, `.jpg`, `.webp`, `.gif`, `.mp4`,
`.webm`, `.mov` và tìm theo tên file. Để kết quả tốt hơn, sao chép file mẫu rồi sửa:

```powershell
Copy-Item assets\memes\library.example.jsonl assets\memes\library.jsonl
```

Mỗi dòng là một JSON object gồm `id`, `filename`, `type`, `tags`, `emotion`, `style`,
`description`, `intensity`, `quality`, `safe`, `language`, `usage_count`, cùng `source_url` và
`license_note` nếu có. Đặt `safe=false` để meme không bao giờ được chọn. Một dòng hỏng chỉ bị
bỏ riêng và log chỉ rõ số dòng. Template Imgflip là nội dung do người dùng đăng; hãy đọc nguồn
và tự kiểm tra quyền sử dụng trước khi xuất bản, nhất là nội dung thương mại.

**Cách tìm kiếm local so khớp** (khi không dùng Meme Search):

- **Phân biệt dấu:** "bất ngờ" không khớp "nổi bật" hay "ngớ ngẩn". Gõ truy vấn **không dấu**
  ("bat ngo") thì mới so không phân biệt dấu.
- **Ưu tiên cả cụm:** "chờ đợi" khớp "chờ đợi quá lâu" tốt hơn "mong chờ"; một âm tiết khớp lẻ
  trong từ nhiều âm tiết chỉ được nửa điểm.
- **Không hiểu từ đồng nghĩa:** "tiết lộ" không tự khớp "bị nói trúng". Khi viết `description`
  và `tags`, dùng những từ AI hay dùng cho tình huống đó — xem taxonomy trong
  `prompts/meme_detector.txt` (ngượng, sốc, bối rối, giấu nỗi đau…). Muốn tìm theo ý nghĩa
  thật sự thì dùng Meme Search bên dưới.

Nếu muốn tìm semantic bằng Meme Search, chạy dịch vụ trên loopback rồi tạo token có hai scope
`search:read,media:read`:

```powershell
gh repo clone meme-search/meme-search
cd meme-search
docker compose up -d
docker compose exec meme_search bin/rails api_tokens:create `
  NAME="automeme" SCOPES="search:read,media:read"
```

Chép token vừa hiện ra vào `.env` dưới tên `MEME_SEARCH_TOKEN`. automeme gọi
`GET /api/v1/search?mode=vector`, xếp hạng metadata, rồi chỉ tải asset thắng vào
`data/cache/meme-search/`. API lỗi sẽ tự fallback về local. Không public Meme Search ra mạng:
API token không bảo vệ giao diện web/settings của dịch vụ.

### 5.4 Timeline: viết tay và duyệt

`timeline.json` là "bản dựng" dạng chữ: mỗi meme hoặc SFX có thời điểm, thời lượng và file.
Bạn xóa event, đổi thời điểm/asset/âm lượng rồi render lại mà không tốn lượt AI. `run` tự dựng
file này từ `analysis.json` và các thư viện local; bạn vẫn có thể tự viết hoàn toàn bằng tay.

Đặt ở `data/timelines/<tên-video>.timeline.json` (đúng tên này thì `render` tự tìm thấy):

```json
{
  "version": 1,
  "video": "video.mp4",
  "events": [
    {
      "id": "event_001",
      "type": "meme",
      "start": 3.0,
      "duration": 1.8,
      "asset": "assets/memes/soc.png",
      "position": "bottom-right",
      "scale": 0.35,
      "status": "pending",
      "reason": "ghi chú cho chính bạn, không bắt buộc"
    },
    {
      "id": "event_002",
      "type": "sfx",
      "start": 3.0,
      "duration": 0.53,
      "asset": "assets/sfx/popular/ui__error_003.ogg",
      "volume": 0.25,
      "status": "pending"
    }
  ]
}
```

| Khóa | Bắt buộc | Ý nghĩa |
|---|---|---|
| `id` | có | Mã riêng của sự kiện, không trùng nhau |
| `type` | không | `meme` (mặc định) hoặc `sfx` |
| `start` | có | Giây, tính từ đầu video |
| `duration` | có | Meme hiện bao lâu (giây) |
| `asset` | có | Đường dẫn ảnh/GIF, tính từ thư mục gốc dự án (hoặc từ `assets/`) |
| `position` | không | `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center`. Bỏ trống = `meme.position_default` |
| `scale` | không | Bề rộng meme so với bề rộng video, 0.05–1.0. Bỏ trống = `meme.scale_default` (0.30) |
| `volume` | không | Chỉ cho SFX, từ 0 đến 1; mặc định 0.25 |
| `mode` | không | Hiện chỉ có `overlay` (đè lên video) |
| `status` | không | `pending`, `accepted`, `rejected`; renderer bỏ qua sự kiện `rejected` |
| `confidence`, `query`, `reason` | không | Do bước phân tích ghi lại, để bạn hiểu vì sao có meme này |

Kiểm tra trước khi render:

```powershell
automeme inspect data\timelines\video.timeline.json --video data\input\video.mp4
```

```
TIMELINE  smoke-test.mp4  (2 sự kiện bật / 2 tổng, video 00:11.68)
  mã           trạng thái   bắt đầu    dài  vị trí           cỡ  asset
  event_001    accepted    00:03.00   1.80  bottom-right    35%  assets/memes/soc.png
  event_002    pending     00:08.30   1.50  top-left        25%  assets/memes/soc.png
  [cảnh báo] event_001 → event_002 chỉ cách 3.5s, dưới cooldown 7.0s
  → hợp lệ, render được.
```

**Lỗi** (chặn render): thiếu file meme, meme kết thúc sau khi video hết, trùng mã sự kiện, hai
meme cùng vị trí mà trùng thời gian. **Cảnh báo** (vẫn render): meme dày hơn cooldown, vượt số
meme mỗi phút, thời lượng ngoài khoảng trong cấu hình — timeline viết tay là quyền của bạn.

### 5.5 Làm toàn bộ bằng AutoMeme Studio

Cách dễ nhất là mở Studio từ thư mục dự án:

```powershell
automeme studio
automeme studio --profile funny --port 8765
automeme studio --no-browser --port 0   # tự mở URL được in trong log
```

Trong Studio:

1. **Tổng quan** hiển thị dự án gần đây và tình trạng Python/FFmpeg/GPU/Ollama.
2. **Tạo video** nhận file kéo-thả **hoặc link YouTube** (dán link, tùy chọn đoạn Từ/Đến, bấm
   **Tải về**; tải xong video tự được chọn), cho chọn profile và theo dõi bốn bước pipeline. Mỗi lần chỉ
   có một job GPU; lỗi ở giữa có thể chạy lại và các artifact còn mới được lấy từ cache.
3. **Biên tập** phát video, đồng bộ transcript và waveform; kéo vùng meme/SFX để đổi thời gian,
   Accept/Reject, thay asset/vị trí/tỉ lệ/âm lượng rồi render lại.
4. **Kho asset** nhận ảnh/GIF/video, nghe thử SFX và lọc theo loại. Nút cài riêng tải bộ
   100 meme, 30 GIF và 30 SFX.

Studio chỉ bind vào `127.0.0.1`, dùng token ngẫu nhiên cho request thay đổi dữ liệu và không
public ra LAN/Internet. Các thư viện giao diện đã được đóng gói trong ứng dụng nên chạy offline.

### 5.6 Duyệt nhanh một timeline

Khi chỉ muốn mở thẳng một video đã có timeline, dùng giao diện review gọn:

```powershell
automeme review data\input\video.mp4
automeme review data\input\video.mp4 --profile funny --port 8765
automeme review data\input\video.mp4 --no-browser   # tự mở URL được in trong log
```

Trang chỉ bind vào `127.0.0.1`, không public ra LAN/Internet và mỗi phiên có token riêng. Trong
trang bạn có thể tua video, xem meme xuất hiện đúng thời điểm, đọc transcript, Accept/Reject,
chọn asset khác từ `assets/memes` hoặc `assets/gifs`, sửa start/duration/vị trí/tỉ lệ rồi Render.
Mọi thay đổi được ghi ngay vào `timeline.json`. Reject không xóa event mà đặt
`status: rejected`, vì vậy có thể Accept lại để hoàn tác.

Render:

```powershell
automeme render data\input\video.mp4
automeme render data\input\video.mp4 --force     # dựng lại dù đã có file cũ
automeme render data\input\video.mp4 --timeline <file khác> --out <nơi lưu>
```

Video ra ở `data/output/<tên-video>_automeme.mp4`: cùng độ phân giải, cùng thời lượng; audio gốc
được giữ nguyên khi không có SFX, hoặc được mix với SFX khi timeline có event âm thanh. Ảnh PNG
có vùng trong suốt hiển thị đúng; GIF chạy lặp trong khoảng thời gian của sự kiện. Chất lượng
và tốc độ encode chỉnh bằng `OUTPUT_CRF` và `OUTPUT_PRESET`
(mục 4.2).

**Chạy trọn pipeline:**

```powershell
automeme run data\input\video.mp4 --profile funny
automeme run data\input\video.mp4 --profile funny --force
automeme run data\input\video.mp4 --out video-hoan-chinh.mp4
```

Lệnh lần lượt transcribe → analyze → tìm/rank meme → lưu timeline → render. Output do automeme
tạo được tái sử dụng khi mọi đầu vào còn khớp và tự render lại khi timeline, asset hoặc cấu hình
đổi. File bị sửa ngoài automeme không bị tự ghi đè; dùng `--force` khi thực sự muốn thay nó.
Công thức ranking mặc định: semantic 45%, emotion 20%, style 10%, quality 10%, novelty 15%;
cùng meme trong vòng 60 giây bị trừ thêm 0,30 điểm.

---

## 6. Log và cách báo lỗi

- **Console:** mức INFO. Thêm `-v` để xem DEBUG — đặt **trước** tên lệnh: `automeme -v doctor`.
- **File `data/logs/automeme.log`:** luôn ở mức DEBUG, ghi nguyên văn mọi lệnh FFmpeg (copy
  ra chạy lại được). Tự xoay vòng ở 5 MB, giữ 3 file cũ.
- **Khi báo lỗi**, gửi: lệnh đã chạy, thông báo trên màn hình, phần cuối
  `data/logs/automeme.log`, và kết quả `automeme doctor`. Với Claude Code: gõ `/sua-loi` rồi dán lỗi.

---

## 7. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `The term 'automeme' is not recognized` | Venv chưa kích hoạt | `.\.venv\Scripts\Activate.ps1`, hoặc gọi `.\.venv\Scripts\automeme.exe` |
| `running scripts is disabled on this system` | Chính sách PowerShell | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `python -m venv` báo lỗi | `python` trỏ tới bản Python embeddable | `py -3.11 -m venv .venv` |
| Tiếng Việt thành `Ã¡`, `?` | Console không phải UTF-8 | `setx PYTHONUTF8 1` rồi mở terminal mới; hoặc `chcp 65001` |
| `Không tìm thấy 'ffmpeg' trong PATH` ngay sau khi cài | Terminal cũ chưa nhận PATH mới | Đóng và mở lại terminal (hoặc VS Code) |
| `Chỉ hỗ trợ link YouTube` | Link không phải youtube.com/youtu.be, hoặc có user/port lạ | Mở video trên YouTube rồi copy link từ thanh địa chỉ hoặc nút Chia sẻ |
| `Đây là link playlist` | Link chỉ trỏ tới playlist | Mở một video trong playlist rồi copy link của video đó |
| `Video dài …, vượt giới hạn` | Video hoặc đoạn dài hơn `download.max_duration` | Chọn đoạn bằng `--from/--to` (Studio: ô Từ/Đến), hoặc tăng giới hạn trong `configs/` |
| `Video ở chế độ riêng tư` / `giới hạn độ tuổi` / `hội viên kênh` | Video cần đăng nhập | Chưa hỗ trợ đăng nhập/cookie — dùng video công khai |
| `YouTube vừa thay đổi cách phát video` / `HTTP Error 403` | yt-dlp đã cũ so với YouTube | `python -m pip install -U yt-dlp` rồi thử lại |
| Log yt-dlp báo `n challenge solving failed` | Thiếu JS runtime, thiếu gói `yt-dlp-ejs`, hoặc `yt-dlp-ejs` lệch bản với yt-dlp | Chạy `automeme doctor`, làm theo lệnh ở dòng JS runtime |
| `Buổi live vừa kết thúc, YouTube đang xử lý bản ghi` | VOD chưa xử lý xong | Đợi rồi tải lại; trong lúc đó YouTube thường chỉ cho tải vài giờ cuối |
| `Buổi live vẫn đang phát` | Link trỏ tới live đang diễn ra | Đợi kết thúc và xử lý xong bản ghi |
| `Cấu hình không hợp lệ` | Giá trị sai trong `configs/` hoặc `.env` | Đọc tên khóa trong thông báo — xem [4.5](#45-khi-cấu-hình-sai) |
| `Không có profile 'x'` | Sai tên hoặc chưa tạo file | Thông báo có liệt kê profile đang có |
| `No such option: -v` | Đặt `-v` sau tên lệnh | `automeme -v <lệnh>` |
| Doctor: Ollama *không kết nối được* | Chưa cài hoặc chưa chạy | Cài theo [2.6](#26-cài-thêm-theo-từng-giai-đoạn), hoặc mở ứng dụng Ollama; thử `ollama list` |
| Doctor: *chưa có qwen3:8b* | Chưa tải model | `ollama pull qwen3:8b` |
| `Chưa cài SDK Ollama` | Chưa cài extra Python của Iteration 3 | `python -m pip install -e ".[llm]"` |
| `LLM trả JSON sai ... hai lần` | Model không tuân theo schema ở một câu | Câu đó bị bỏ an toàn; thử model lớn hơn hoặc chạy `analyze --force` |
| `run` tạo timeline 0 meme | Thư viện không có file khớp query hoặc metadata quá ít | Đặt tên file bằng tag tiếng Anh, hoặc tạo `library.jsonl` theo mục 5.3 |
| Meme Search báo 401/403 | Token sai hoặc thiếu scope | Tạo token mới có `search:read,media:read`; không ghi token vào lệnh hay log |
| Meme Search không kết nối được | Container chưa chạy | `docker compose up -d`; pipeline vẫn tự dùng thư viện local |
| `Chưa cài faster-whisper` | Chưa cài nhóm `asr` | `python -m pip install -e ".[asr-cuda]"`, hoặc `".[asr]"` nếu chạy CPU |
| `Thiếu thư viện CUDA (cuDNN/cuBLAS)` | Cài `[asr]` nhưng lại chạy GPU | Cài `".[asr-cuda]"`, hoặc đặt `WHISPER_DEVICE=cpu` và `WHISPER_COMPUTE_TYPE=int8` |
| `GPU hết VRAM` khi nạp model | Model lớn hơn VRAM còn trống | `WHISPER_COMPUTE_TYPE=int8_float16`, hoặc `WHISPER_MODEL=large-v3-turbo`; đóng ứng dụng khác đang dùng GPU |
| Transcript trống, log báo *không nhận được câu nào* | Video không có tiếng nói, hoặc VAD cắt nhầm vì giọng quá nhỏ | Nghe thử `data/cache/.../audio.wav`; thử `WHISPER_VAD_FILTER=false` |
| Log báo *câu ... lặp liên tiếp nhiều lần* | Whisper bị kẹt, hay gặp ở đoạn nhạc hoặc im lặng | Bật lại VAD, hoặc đổi model |
| `Timeline sai định dạng: sự kiện #0 → ...` | Gõ sai tên khóa hoặc giá trị ngoài khoảng | Thông báo chỉ rõ sự kiện thứ mấy và khóa nào — xem bảng khóa ở [5.4](#54-timeline-viết-tay-và-duyệt) |
| `Timeline không hợp lệ: không thấy file meme` | Sai đường dẫn `asset` | Đường dẫn tính từ thư mục gốc dự án (`assets/memes/x.png`) hoặc từ `assets/` (`memes/x.png`) |
| `Chưa có timeline ...` khi dùng `render` | Chưa viết hoặc chưa sinh file timeline | Chạy `automeme run <video>` để sinh tự động, hoặc viết theo mẫu ở [5.4](#54-timeline-viết-tay-và-duyệt) |
| Output *đã bị sửa ngoài automeme* | File đích khác bản automeme đã ghi | Chọn `--out` khác để giữ cả hai, hoặc thêm `--force` nếu muốn ghi đè |
| Port 8765 đang được dùng | Một ứng dụng khác đang nghe trên port đó | Chạy `automeme studio --port 0` hoặc `automeme review <video> --port 0` để tự chọn port trống |
| Render xong nhưng không thấy meme đâu | Thời điểm nằm ngoài đoạn đang xem, hoặc meme trùng màu nền | Trích thử khung hình: `ffmpeg -ss <giây> -i <video ra> -frames:v 1 thu.png` |
| Log báo *Không copy được audio gốc* | Định dạng tiếng gốc không nhét được vào MP4 | Không sao — automeme tự encode lại bằng `AUDIO_CODEC` |

---

## 8. Làm việc cùng Claude Code

Dự án được phát triển cùng Claude Code. Quy tắc nằm trong `CLAUDE.md`; hiện trạng, quyết định
và lộ trình trong `docs/HANDOFF.md`.

| Lệnh | Dùng khi |
|---|---|
| `/tiep-tuc` | Làm hạng mục tiếp theo trong lộ trình |
| `/chay-that` | Chạy thử trên một video thật, kiểm tra từng bước |
| `/sua-loi` | Dán lỗi hoặc tả triệu chứng để chẩn đoán và sửa |

Nhịp làm việc:

1. Claude đọc HANDOFF, trình kế hoạch (file sẽ sửa, thư viện cần cài, rủi ro, chỗ làm khác
   SPEC) rồi **dừng chờ bạn duyệt**. Các quyết định được đánh số, có phương án khuyên — trả
   lời "đồng ý hết" hoặc chọn từng điểm.
2. Claude viết code và test; `pytest -q` và `ruff` phải xanh.
3. Claude cập nhật HANDOFF (checklist, nhật ký) và hướng dẫn này, rồi đề xuất commit — chỉ
   commit khi bạn đồng ý. Cài thư viện mới luôn phải hỏi trước.

Muốn đổi hướng thiết kế: nói với Claude để ghi vào mục "Quyết định đã chốt" của HANDOFF —
khi HANDOFF và SPEC mâu thuẫn, HANDOFF thắng.

---

## 9. Dành cho người phát triển

```powershell
pytest -q                     # 237 test, không cần GPU/Ollama; test FFmpeg tự bỏ qua nếu máy thiếu
pytest --cov=automeme         # kèm độ phủ code
ruff check src tests          # lint
ruff check --fix src tests    # tự sửa lỗi dễ (sắp xếp import…)
```

```
src/automeme/
├── cli.py        lệnh automeme (Typer)
├── config.py     nạp + kiểm tra cấu hình
├── doctor.py     automeme doctor
├── cache.py      manifest, cache key và nhận biết file người dùng đã sửa
├── pipeline.py   nối các bước lại (transcribe_video…)
├── workspace.py  đường dẫn output + khóa cache của từng video
├── media/        mọi lời gọi FFmpeg/ffprobe: ffmpeg.py, probe.py, audio.py
├── transcription/  interface + backend faster-whisper + chuẩn hóa transcript
├── analyzer/     context window + schema + adapter Ollama/Claude + bộ lọc cứng
├── memes/        provider local/API, metadata, tải cache và xếp hạng
├── timeline/     schema + builder + validator
├── rendering/    filters.py (dựng filtergraph, hàm thuần) + renderer.py (gọi FFmpeg)
├── review/       web UI loopback + API chỉnh timeline có token phiên
├── studio/       dashboard + upload/job + editor waveform + kho meme
└── utils/        đường dẫn, JSON, thời gian, log
```

Frontend Studio dùng dependency npm **chỉ lúc build**. Bản phân phối đã chứa vendor offline;
muốn cập nhật/dựng lại thì chạy `npm install` và `npm run build:studio`, sau đó kiểm tra
`THIRD_PARTY_NOTICES.md` cùng các license trong `studio/static/vendor/licenses/`.

**Quy tắc chính** (đầy đủ trong `CLAUDE.md`): logic là hàm thuần có test; FFmpeg chỉ gọi qua
`automeme.media`, lệnh dạng list; import thư viện nặng bên trong hàm; output của LLM luôn qua
pydantic + `validate_*`; mỗi bước bỏ qua nếu output đã có và ghi file tạm rồi đổi tên; log và
comment tiếng Việt; không commit `.env`, media, `data/`.

**Thêm một tham số cấu hình:**
1. Thêm khóa (kèm chú thích) vào `configs/default.yaml`.
2. Thêm field vào model tương ứng trong `src/automeme/config.py`.
3. Nếu cần đặt qua `.env`: thêm vào `ENV_MAP` và `.env.example` — test sẽ báo nếu hai chỗ lệch nhau.

**Git:** nhánh `main`. Commit nhỏ, mỗi commit một ý, message dạng `feat: …`, `fix: …`,
`docs: …`. CI (`.github/workflows/ci.yml`) chạy ruff + pytest mỗi lần push lên GitHub.

---

## 10. Code cũ trong `legacy/`

`legacy/stream_editor/` là phiên bản trước: cắt highlight từ VOD stream game, khung dọc 9:16,
phụ đề karaoke, Claude chọn clip. Không bảo trì nhưng vẫn chạy được:

```powershell
cd legacy\stream_editor
..\..\.venv\Scripts\python.exe -m pytest -q
..\..\.venv\Scripts\python.exe run.py doctor
```

Tài liệu cũ: `legacy/stream_editor/README.md`, `legacy/stream_editor/HANDOFF.md`. Một số phần
sẽ được dùng lại: phụ đề karaoke (thành `CaptionEvent`), khung dọc 9:16, lớp gọi Claude API.
