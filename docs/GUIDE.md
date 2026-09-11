# Hướng dẫn sử dụng automeme

> Cài đặt nhanh xem [`README.md`](../README.md). File này giải thích từng bước: cài đặt, kiểm
> tra môi trường, cấu hình, quy trình làm video, xử lý sự cố, và cách làm việc cùng Claude Code.
>
> **Cập nhật: 2026-09-11 — Stage A.** Mục nào ghi *(đang xây)* sẽ được viết chi tiết khi
> iteration tương ứng xong. Lộ trình đầy đủ: [`HANDOFF.md`](HANDOFF.md) mục 5.

## Mục lục

1. [automeme làm gì, hiện làm được đến đâu](#1-automeme-làm-gì-hiện-làm-được-đến-đâu)
2. [Cài đặt từ đầu trên Windows](#2-cài-đặt-từ-đầu-trên-windows)
3. [Kiểm tra môi trường: `automeme doctor`](#3-kiểm-tra-môi-trường-automeme-doctor)
4. [Cấu hình](#4-cấu-hình)
5. [Quy trình làm một video](#5-quy-trình-làm-một-video-đang-xây)
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
| `automeme transcribe` | Video → transcript | Iteration 1 |
| `automeme render`, `automeme inspect` | Timeline → video; xem lại timeline | Iteration 2 |
| `automeme analyze` | Transcript → khoảnh khắc nên chèn meme | Iteration 3 |
| `automeme run` | Trọn quy trình bằng một lệnh | Iteration 4 |

Lệnh chưa làm chỉ in cảnh báo "chưa làm — thuộc Iteration N" rồi thoát, không đụng vào file nào.

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
| Iteration 1 — `transcribe` | faster-whisper | `python -m pip install -e ".[asr]"`. Chạy GPU trên Windows còn cần thư viện CUDA — hướng dẫn cụ thể sẽ có khi làm Iteration 1 |
| Iteration 3 — `analyze` | Ollama + model | `winget install Ollama.Ollama`, rồi `ollama pull qwen3:8b` |
| Iteration 4 | Thư viện meme của bạn | chép file vào `assets/` — xem [5.3](#53-thư-viện-meme-iteration-4) |
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
  [  OK  ]  ffmpeg          9.0.1-full_build-www.gyan.dev — ...
  [THIẾU ]  faster-whisper  chưa cài — cần từ Iteration 1: python -m pip install -e .[asr]
  [  OK  ]  GPU NVIDIA      NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB)
  [THIẾU ]  Ollama          không kết nối được http://localhost:11434 (...); cần từ Iteration 3
  ...
Bắt buộc: tất cả đạt.
Thiếu nhưng chưa chặn: .env, faster-whisper, Ollama
```

Ba mức: `[  OK  ]` đạt · `[THIẾU ]` chưa cần cho bước hiện tại · `[ HỎNG ]` phải sửa (lệnh
thoát với mã 1, dùng được trong script).

| Dòng | Kiểm tra gì | Không đạt thì |
|---|---|---|
| Python >= 3.10 | Phiên bản Python đang chạy automeme | Tạo lại venv bằng `py -3.11` |
| Cấu hình | `configs/`, profile và `.env` hợp lệ | Đọc thông báo, sửa đúng khóa bị nêu tên — xem [4.5](#45-khi-cấu-hình-sai) |
| .env | Đã có file `.env` chưa | `Copy-Item .env.example .env` |
| ffmpeg, ffprobe | Có trong PATH, phiên bản bao nhiêu | `winget install Gyan.FFmpeg`, mở lại terminal |
| faster-whisper | Đã cài chưa | `python -m pip install -e ".[asr]"` (từ Iteration 1) |
| GPU NVIDIA | `nvidia-smi` có thấy GPU không | Cài driver NVIDIA. Không có GPU: `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8` |
| Ollama | Server ở `OLLAMA_HOST` có chạy, đã tải model chưa | Mở ứng dụng Ollama; `ollama pull <model>` |
| Claude API | Chỉ hiện khi `LLM_BACKEND=claude`: đã cài thư viện, có key chưa | Xem [2.6](#26-cài-thêm-theo-từng-giai-đoạn) |
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
| `LLM_BACKEND` | `ollama` | `claude` để dùng Claude API |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama chạy ở máy khác |
| `OLLAMA_MODEL` | `qwen3:8b` | GPU dưới 8 GB VRAM: `qwen3:4b` |
| `MEME_SEARCH_BASE_URL`, `_TOKEN`, `_TOP_K` | — | Khi dùng Meme Search |
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

- **`max_memes_per_minute`** — trần mật độ.
- **`cooldown`** — khoảng cách tối thiểu giữa hai meme. Với 7 giây: có meme ở 00:05 thì ứng
  viên ở 00:08 bị loại, ứng viên ở 00:13 được giữ.
- **`threshold`** — LLM tự chấm độ chắc chắn 0–1 cho mỗi khoảnh khắc; thấp hơn ngưỡng thì bỏ.
- **`duration_min` / `duration_max`** — meme hiện trên màn hình bao lâu.

> Các tham số này có tác dụng từ Iteration 3–4 (khi có bước phân tích và dựng timeline). Hiện
> tại `doctor` chỉ kiểm tra chúng hợp lệ.

**Tạo profile riêng:**

```powershell
Copy-Item configs\funny.yaml configs\kenh_cua_toi.yaml
# mở file, sửa giá trị — chỉ cần giữ những khóa muốn khác mặc định
automeme doctor --profile kenh_cua_toi
```

Tên profile chỉ gồm chữ, số, `_`, `-` — nên dùng không dấu.

### 4.4 Cờ CLI

Đè tất cả, chỉ cho một lần chạy. Ví dụ theo mục tiêu MVP *(đang xây)*:

```powershell
automeme run input.mp4 --profile funny --max-memes 5
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

## 5. Quy trình làm một video *(đang xây)*

### 5.1 Chọn video

MVP nhắm tới video tiếng Việt **30–90 giây**, có hội thoại rõ, định dạng `.mp4`, `.mov` hoặc
`.mkv`. Chép vào `data/input/`.

### 5.2 Các bước

```powershell
automeme transcribe data\input\video.mp4    # Iteration 1: lời thoại
automeme analyze    data\input\video.mp4    # Iteration 3: khoảnh khắc nên chèn meme
automeme inspect    <file timeline>         # Iteration 2: xem lại trước khi render
automeme render     data\input\video.mp4    # Iteration 2: dựng video
# hoặc một lệnh cho tất cả (Iteration 4):
automeme run data\input\video.mp4 --profile funny
```

Mỗi bước lưu kết quả vào `data/` và **bỏ qua nếu kết quả đã có** — sửa timeline rồi render lại
không phải chạy lại Whisper hay LLM. Muốn làm lại một bước thì xóa file kết quả của bước đó.
Tên file cụ thể sẽ chốt ở Iteration 1.

| Thư mục | Chứa |
|---|---|
| `data/input/` | Video gốc bạn chép vào |
| `data/temp/` | File tạm |
| `data/cache/` | Kết quả trung gian của từng video (audio, phân tích, kết quả tìm meme) |
| `data/transcripts/` | Transcript |
| `data/timelines/` | Timeline — file bạn duyệt và sửa |
| `data/output/` | Video hoàn chỉnh |
| `data/logs/` | `automeme.log` |

Toàn bộ `data/` không được commit.

### 5.3 Thư viện meme *(Iteration 4)*

Ảnh đặt trong `assets/memes/`, GIF trong `assets/gifs/`, âm thanh trong `assets/sfx/`. Nên có
khoảng 200–500 meme chia theo cảm xúc: sốc, bối rối, ngượng, facepalm, hoảng, ăn mừng… (SPEC
§25). Chỉ dùng meme bạn có quyền dùng — repo không commit các thư mục này (SPEC §56). Cách mô
tả từng meme (tag, cảm xúc, an toàn) sẽ chốt ở Iteration 4.

### 5.4 Duyệt timeline

`timeline.json` là "bản dựng" dạng chữ: mỗi meme có thời điểm, thời lượng, file, vị trí, cỡ.
Bạn xóa meme, đổi thời điểm, đổi file rồi render lại mà không tốn lượt chạy AI. Định dạng chốt
ở Iteration 2 (ví dụ tham khảo: SPEC §34).

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
| `Cấu hình không hợp lệ` | Giá trị sai trong `configs/` hoặc `.env` | Đọc tên khóa trong thông báo — xem [4.5](#45-khi-cấu-hình-sai) |
| `Không có profile 'x'` | Sai tên hoặc chưa tạo file | Thông báo có liệt kê profile đang có |
| `No such option: -v` | Đặt `-v` sau tên lệnh | `automeme -v <lệnh>` |
| Doctor: Ollama *không kết nối được* | Chưa cài hoặc chưa chạy | Cài theo [2.6](#26-cài-thêm-theo-từng-giai-đoạn), hoặc mở ứng dụng Ollama; thử `ollama list` |
| Doctor: *chưa có qwen3:8b* | Chưa tải model | `ollama pull qwen3:8b` |
| Lệnh báo *chưa làm — thuộc Iteration N* | Tính năng chưa xây | Xem lộ trình trong `docs/HANDOFF.md` |

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
pytest -q                     # 73 test, không cần GPU/Ollama; test FFmpeg tự bỏ qua nếu máy thiếu
pytest --cov=automeme         # kèm độ phủ code
ruff check src tests          # lint
ruff check --fix src tests    # tự sửa lỗi dễ (sắp xếp import…)
```

```
src/automeme/
├── cli.py        lệnh automeme (Typer)
├── config.py     nạp + kiểm tra cấu hình
├── doctor.py     automeme doctor
├── media/        mọi lời gọi FFmpeg/ffprobe: ffmpeg.py, probe.py, audio.py
└── utils/        đường dẫn, JSON, thời gian, log
```

Sắp thêm theo SPEC §12: `transcription/`, `analyzer/`, `memes/`, `timeline/`, `rendering/`,
`pipeline.py`.

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
