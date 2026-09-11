---
name: chay-that
description: Hướng dẫn chạy pipeline trên một VOD thật lần đầu (hoặc sau thay đổi lớn) — kiểm tra môi trường, chạy từng bước, kiểm tra output mỗi bước, chẩn đoán lỗi. Dùng khi người dùng gõ /chay-that hoặc muốn "chạy thử thật", "test với VOD".
---

# Chạy pipeline trên VOD thật

Mục tiêu: chạy xong bước 1 → 4, duyệt, render, và ghi lại mọi vấn đề phát hiện được.
Chạy **từng bước một**, không dùng `all`, để khoanh vùng lỗi.

1. **Kiểm tra môi trường** (chạy lệnh, báo kết quả dạng bảng):
   `python --version`, `ffmpeg -version`, `yt-dlp --version`, có `.env` với
   `ANTHROPIC_API_KEY` (chỉ kiểm tra có tồn tại, KHÔNG in giá trị key),
   `python -c "import torch; print(torch.cuda.is_available())"`, backend ASR đã cài chưa,
   nếu Twitch thì `TwitchDownloaderCLI`. Trên Windows gợi ý `PYTHONUTF8=1`.
   Thiếu gì thì hướng dẫn cài, dừng lại chờ người dùng.
2. **Hỏi người dùng**: link VOD (khuyên dùng VOD 30–60 phút cho lần đầu) hoặc đường dẫn
   video có sẵn; nền tảng; preset streamer nào (nếu chưa có, giúp tạo từ `streamer_example.yaml`).
3. **fetch** → xác nhận `vod.mp4`, `audio.wav` tồn tại; thời lượng (ffprobe); chat có tải được
   không, bao nhiêu tin nhắn.
4. **preprocess** → báo: số từ, số câu, thời gian chạy; in 10 câu transcript mẫu để người dùng
   đánh giá chất lượng tiếng Việt; kiểm tra `words.json` KHÔNG rỗng (nếu rỗng: căn chỉnh theo từ
   thất bại — xem mục 4 HANDOFF).
5. **candidates** → in bảng các ứng viên (id, thời gian, điểm, tín hiệu chính). Đưa lệnh ffplay
   để người dùng xem nhanh 3–5 ứng viên điểm cao nhất; hỏi cảm nhận; đề xuất chỉnh
   `refs`/`weights` nếu cần.
6. **select** → báo token vào/ra và ước tính chi phí; in danh sách clip; lưu ý các cảnh báo
   từ `validate_clips`.
7. Nhắc người dùng chạy `python run.py review --job X` (tương tác, người dùng tự làm), rồi
   `render --preview` và `render`.
8. Ghi mọi vấn đề, số liệu (thời gian mỗi bước, token, tỉ lệ clip được giữ) và thay đổi
   config vào **Nhật ký tiến độ** trong `docs/HANDOFF.md`. Đề xuất sửa lỗi nếu có — sửa theo
   quy trình `/sua-loi`.
