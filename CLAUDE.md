# Hướng dẫn cho Claude Code

Dự án **automeme**: công cụ Python tìm khoảnh khắc trong video tiếng Việt để chèn meme/reaction.
faster-whisper (lời thoại) → LLM local qua Ollama (quyết định dạng JSON) → tìm và xếp hạng
meme → `timeline.json` (người duyệt được) → FFmpeg render.

**Đọc `docs/HANDOFF.md` ở đầu mỗi phiên** — hiện trạng, quyết định đã chốt, lộ trình,
checklist, nhật ký. Đặc tả gốc là `docs/SPEC.md`; khi mâu thuẫn thì HANDOFF đúng.
Cập nhật checklist + nhật ký sau mỗi việc hoàn thành.

## Quy tắc bắt buộc
- Lập kế hoạch và chờ người dùng đồng ý trước khi code một hạng mục mới.
- Mọi output của LLM qua model pydantic + hàm `validate_*` trước khi dùng. Ràng buộc cứng
  (cooldown, số meme/phút, thời lượng, chồng lấn, file tồn tại) do code quyết định, không phải LLM.
- Logic là hàm thuần có test; phần gọi FFmpeg/Ollama/API mỏng nhất có thể. FFmpeg chỉ gọi qua
  `automeme.media`, lệnh dạng list.
- Import thư viện nặng (faster_whisper, ctranslate2, ollama, anthropic, torch) bên trong hàm.
- Tham số dựng video đặt trong `configs/` (profile), tham số máy trong `.env`, prompt trong
  `prompts/` — không hard-code.
- Mỗi bước bỏ qua nếu output đã tồn tại; ghi ra file tạm rồi đổi tên.
- Log và comment tiếng Việt; trả lời người dùng bằng tiếng Việt.
- `pytest -q` và `ruff check src tests` phải xanh trước khi đề xuất commit; chỉ commit khi
  người dùng đồng ý.
- Không commit `.env`, file media, `data/`. Hỏi trước khi cài thư viện mới.
- Thêm/đổi lệnh, cấu hình hoặc bước cài đặt thì cập nhật `docs/GUIDE.md` (hướng dẫn người dùng).
- `legacy/` là code cũ (cắt highlight stream) — không sửa trừ khi người dùng yêu cầu.

## Lệnh
Venv không được kích hoạt sẵn — gọi qua `.venv\Scripts\`:
- Test: `.venv\Scripts\python -m pytest -q` · Lint: `.venv\Scripts\ruff check src tests`
- Kiểm tra môi trường: `.venv\Scripts\automeme doctor`
- Duyệt timeline: `.venv\Scripts\automeme review <video>`
- Cài lại sau khi sửa `pyproject.toml`: `.venv\Scripts\python -m pip install -e ".[dev]"`
- Chạy trọn pipeline MVP: `automeme run input.mp4 --profile funny`

## Lệnh tắt (skill) trong dự án
- `/tiep-tuc` — làm hạng mục tiếp theo trong lộ trình
- `/chay-that` — chạy pipeline trên một video thật và kiểm tra từng bước
- `/sua-loi` — chẩn đoán và sửa lỗi từ log/triệu chứng

## Môi trường
Windows: đường dẫn trong filter FFmpeg phải escape `:` và `\` — né bằng cách đưa file vào qua
`-i`, hoặc chạy FFmpeg với `cwd` là thư mục chứa file và dùng tên tương đối. Luôn
`encoding="utf-8"` khi mở file, gợi ý `PYTHONUTF8=1`.
