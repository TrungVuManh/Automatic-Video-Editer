# Auto Meme Video Editor (`automeme`)

AI phân tích lời thoại trong video tiếng Việt, tìm khoảnh khắc nên chèn meme/reaction, tìm
meme phù hợp theo ngữ nghĩa và render vào đúng lúc. Chạy local: **faster-whisper** nghe,
**Ollama** quyết định, **FFmpeg** dựng.

```
video → audio → transcript → LLM tìm khoảnh khắc → tìm & xếp hạng meme → timeline.json → duyệt → render
```

Mọi quyết định của AI nằm trong `timeline.json` để người sửa được trước khi render — AI không
render trực tiếp.

## Trạng thái

| Bước | Nội dung | Trạng thái |
|---|---|---|
| Stage A | Khung dự án, cấu hình + profile, log, `automeme doctor` | ✅ |
| Iteration 1 | `automeme transcribe` → `transcript.json` | ⏳ |
| Iteration 2 | `timeline.json` + render meme PNG/JPG/GIF | ⏳ |
| Iteration 3 | Ollama tìm khoảnh khắc → `analysis.json` | ⏳ |
| Iteration 4 | Tìm + xếp hạng meme → `automeme run` | ⏳ |

**Hướng dẫn chi tiết** (cài đặt từng bước, cấu hình, xử lý sự cố):
[`docs/GUIDE.md`](docs/GUIDE.md). Đặc tả đầy đủ: [`docs/SPEC.md`](docs/SPEC.md). Tiến độ và các
quyết định đã chốt: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Cài đặt (Windows, PowerShell)

**1. Công cụ hệ thống**

- Python 3.10+ (khuyên 3.11)
- FFmpeg: `winget install Gyan.FFmpeg`
- Ollama (cần từ Iteration 3): `winget install Ollama.Ollama`, rồi `ollama pull qwen3:8b`
- Docker Desktop — chỉ cần nếu dùng Meme Search

**2. Môi trường Python**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

PowerShell chặn script thì chạy một lần:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
Không muốn kích hoạt venv: gọi thẳng `.\.venv\Scripts\automeme.exe` hoặc
`.\.venv\Scripts\python.exe -m automeme`.

Nhận dạng giọng nói (cần từ Iteration 1): `python -m pip install -e ".[asr]"`.

**3. Kiểm tra**

```powershell
automeme doctor
```

Mục `[ HỎNG ]` phải xử lý hết; `[THIẾU ]` là thứ chưa cần cho bước hiện tại.

## Sử dụng

```powershell
automeme --help
automeme doctor                    # kiểm tra môi trường
automeme doctor --profile subtle   # kiểm tra kèm một profile
```

`transcribe`, `analyze`, `inspect`, `render`, `run` đã có tên nhưng chưa làm — chạy sẽ báo lệnh
đó thuộc iteration nào. Mục tiêu cuối MVP (SPEC §78):

```powershell
automeme run input.mp4 --profile funny
```

## Cấu hình

Thứ tự ưu tiên, cao đè thấp:

```
cờ CLI  >  biến môi trường / .env  >  profile (--profile)  >  configs/default.yaml
```

- `configs/default.yaml` — đủ mọi khóa, có chú thích.
- `configs/subtle.yaml`, `funny.yaml`, `chaotic.yaml` — profile, chỉ ghi khóa muốn đổi.
- `.env` — cấu hình của máy (model Whisper, `cuda`/`cpu`, địa chỉ Ollama…). Tên biến xem
  `.env.example`. Tham số dựng video (`MEME_COOLDOWN`…) để dạng comment: bỏ comment sẽ đè
  **mọi** profile.

Gõ sai tên khóa hoặc giá trị ngoài khoảng cho phép sẽ bị báo lỗi, không bị lặng lẽ bỏ qua.

Log hiện trên console và ghi đầy đủ (kèm nguyên lệnh FFmpeg) vào `data/logs/automeme.log` —
gửi file này khi báo lỗi.

## Cấu trúc

```
configs/         default.yaml + profile
prompts/         prompt gửi LLM (từ Iteration 3)
src/automeme/    cli, config, doctor, media/ (FFmpeg), utils/
tests/           pytest — không cần GPU hay Ollama; test FFmpeg tự bỏ qua nếu máy không có
data/            input, temp, cache, transcripts, timelines, output, logs — không commit
assets/          memes, gifs, sfx, fonts — người dùng tự thêm, không commit
docs/            GUIDE.md (hướng dẫn), SPEC.md (đặc tả gốc), HANDOFF.md (tiến độ, quyết định)
legacy/          code cũ stream-auto-editor (cắt highlight stream game) — không bảo trì
```

## Phát triển

```powershell
pytest -q
ruff check src tests
```

## Bản quyền

License cho code chưa chọn (SPEC §83 gợi ý MIT hoặc Apache-2.0). Meme **không** tự động là
mã nguồn mở: repo không kèm meme, người dùng tự thêm vào `assets/memes/` (SPEC §56).
