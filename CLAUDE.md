# Hướng dẫn cho Claude Code

Dự án: pipeline Python tự động cắt highlight, làm video dọc có phụ đề và chèn meme cho
video stream game tiếng Việt. Claude (API) ra quyết định dạng JSON; FFmpeg dựng video.

**Đọc `docs/HANDOFF.md` ở đầu mỗi phiên** — trong đó có hiện trạng, đặc tả chi tiết từng
tuần, checklist và nhật ký tiến độ. Cập nhật checklist + nhật ký sau mỗi việc hoàn thành.

## Quy tắc bắt buộc
- Lập kế hoạch và chờ người dùng đồng ý trước khi code một hạng mục mới.
- Mọi output của model qua hàm `validate_*` trước khi dùng.
- Logic là hàm thuần có test; phần gọi FFmpeg/API mỏng nhất có thể.
- Import thư viện nặng (whisperx, faster_whisper, anthropic, torch) bên trong hàm.
- Tham số đặt trong `config/`, prompt đặt trong `prompts/`, không hard-code.
- Mỗi bước bỏ qua nếu output đã tồn tại.
- Log và comment tiếng Việt; trả lời người dùng bằng tiếng Việt.
- `pytest -q` phải xanh trước khi đề xuất commit; chỉ commit khi người dùng đồng ý.
- Không commit `.env`, file media, `jobs/`. Hỏi trước khi cài thư viện mới.

## Lệnh
- Test: `pytest -q`
- Chạy thử với video có sẵn: `python run.py all --job test --streamer streamer_example --platform twitch --video <file.mp4>`
- Duyệt / render: `python run.py review --job X`, `python run.py render --job X [--preview]`

## Lệnh tắt (skill) trong dự án
- `/tiep-tuc` — làm hạng mục tiếp theo trong lộ trình
- `/chay-that` — hướng dẫn chạy pipeline trên VOD thật và kiểm tra từng bước
- `/sua-loi` — chẩn đoán và sửa lỗi từ log/triệu chứng

## Môi trường
Người dùng có thể dùng Windows: chú ý đường dẫn trong filter FFmpeg (escape `:` và `\`),
luôn `encoding="utf-8"` khi mở file, gợi ý `PYTHONUTF8=1`.
