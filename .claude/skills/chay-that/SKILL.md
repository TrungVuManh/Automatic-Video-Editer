---
name: chay-that
description: Hướng dẫn chạy pipeline automeme trên một video thật lần đầu (hoặc sau thay đổi lớn) — kiểm tra môi trường, chạy từng bước, kiểm tra output mỗi bước, chẩn đoán lỗi. Dùng khi người dùng gõ /chay-that hoặc muốn "chạy thử thật", "test với video thật".
---

# Chạy pipeline trên video thật

Mục tiêu: chạy hết các bước **đã làm** (xem mục 2 và 6 của `docs/HANDOFF.md`), kiểm tra
output từng bước, ghi lại mọi vấn đề. Chạy **từng lệnh một**, không dùng `run`, để khoanh vùng
lỗi. Lệnh nào còn báo "chưa làm" thì dừng ở đó và nói rõ cho người dùng.

1. **Môi trường:** chạy `.venv\Scripts\automeme doctor`, báo lại bảng. Mục `[ HỎNG ]` phải xử
   lý trước; `[THIẾU ]` chỉ cần xử lý nếu bước sắp chạy dùng tới (faster-whisper cho
   `transcribe`, Ollama + model cho `analyze`). Không bao giờ in giá trị key trong `.env`.
   Trên Windows gợi ý `PYTHONUTF8=1`.
2. **Hỏi người dùng:** đường dẫn một video tiếng Việt 30–90 giây có hội thoại (SPEC §61), profile
   muốn dùng. Chép video vào `data/input/`.
3. **transcribe** → báo số đoạn, số từ, thời gian chạy, VRAM nếu dùng GPU; in 10 câu mẫu để
   người dùng đánh giá chất lượng tiếng Việt; kiểm tra timestamp tăng dần và `words` không rỗng.
4. **analyze** → báo số khoảnh khắc, bao nhiêu qua ngưỡng confidence; in từng cái (thời điểm,
   câu trigger, emotion, `search_query`). Kiểm tra query tả **phản ứng hình ảnh** chứ không
   phải từ khóa (SPEC §22). Hỏi người dùng thấy đúng chỗ buồn cười không.
5. **Tìm meme / timeline** → `automeme inspect <timeline>`; kiểm tra khoảng cách giữa các meme
   ≥ cooldown, số meme/phút, file meme tồn tại.
6. **render --preview** rồi **render** → dùng `ffprobe` so thời lượng với video gốc, kiểm tra
   còn audio; đưa lệnh `ffplay` để người dùng tự xem meme có đúng lúc, đúng chỗ, không che mặt.
7. Ghi số liệu (thời gian từng bước, VRAM, số meme được giữ, cảm nhận của người dùng) và mọi
   thay đổi config vào **Nhật ký tiến độ** trong `docs/HANDOFF.md`. Có lỗi thì sửa theo
   quy trình `/sua-loi`.
