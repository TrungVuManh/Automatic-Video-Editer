---
name: sua-loi
description: Chẩn đoán và sửa lỗi của pipeline automeme từ log, traceback hoặc mô tả triệu chứng (transcript sai, meme lệch thời điểm, meme không liên quan, render lỗi...). Dùng khi người dùng gõ /sua-loi, dán lỗi, hoặc báo kết quả không như mong đợi.
---

# Sửa lỗi

1. Thu thập bằng chứng: traceback/log người dùng dán, `data/logs/automeme.log` (mức DEBUG, có
   nguyên lệnh FFmpeg), file output của bước lỗi trong `data/` (transcript, analysis, timeline),
   và output `automeme doctor` nếu nghi do môi trường. Nếu thiếu thông tin quyết định, hỏi đúng
   thứ cần (một lượt).
2. Xác định bước và module gây lỗi. Tái hiện bằng lệnh nhỏ nhất có thể (lệnh FFmpeg trong log
   chạy lại được nguyên văn).
3. Tìm **nguyên nhân gốc**, không vá triệu chứng. Với lỗi logic: viết test tái hiện lỗi
   (test phải đỏ) trước khi sửa.
4. Sửa, chạy lại test tái hiện, toàn bộ `pytest -q` và `ruff check src tests`.
5. Nếu lỗi do môi trường (thiếu công cụ, phiên bản, đường dẫn Windows, CUDA/cuDNN, Ollama chưa
   chạy, thiếu VRAM), hướng dẫn người dùng xử lý thay vì sửa code — trừ khi code có thể phát
   hiện và báo lỗi rõ hơn; khi đó thêm thông báo tiếng Việt dễ hiểu (và một dòng trong `doctor`
   nếu hợp).
6. Nếu LLM trả kết quả kém (khoảnh khắc sai, query là từ khóa): xem prompt trong `prompts/` và
   input thực tế đã gửi; ưu tiên sửa prompt/cửa sổ ngữ cảnh trước khi đổi model.
7. Giải thích ngắn gọn cho người dùng: nguyên nhân, đã sửa gì, cách tránh. Ghi một dòng vào
   **Nhật ký tiến độ** trong `docs/HANDOFF.md` nếu lỗi đáng chú ý.
