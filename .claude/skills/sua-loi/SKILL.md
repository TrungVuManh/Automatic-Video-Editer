---
name: sua-loi
description: Chẩn đoán và sửa lỗi của pipeline từ log, traceback hoặc mô tả triệu chứng (clip cắt sai, phụ đề lệch, ứng viên toàn nhiễu...). Dùng khi người dùng gõ /sua-loi, dán lỗi, hoặc báo kết quả không như mong đợi.
---

# Sửa lỗi

1. Thu thập bằng chứng: traceback/log người dùng dán, `jobs/<job>/pipeline.log` nếu có,
   file output của bước lỗi, `candidates/prompt_last.md` nếu lỗi liên quan đến Claude.
   Nếu thiếu thông tin quyết định, hỏi đúng thứ cần (một lượt).
2. Xác định bước và module gây lỗi. Tái hiện lỗi bằng lệnh nhỏ nhất có thể.
3. Tìm **nguyên nhân gốc**, không vá triệu chứng. Với lỗi logic: viết test tái hiện lỗi
   (test phải đỏ) trước khi sửa.
4. Sửa, chạy lại test tái hiện và toàn bộ `pytest -q`.
5. Nếu lỗi do môi trường (thiếu công cụ, phiên bản, đường dẫn Windows, GPU), hướng dẫn
   người dùng xử lý thay vì sửa code, trừ khi code có thể phát hiện và báo lỗi rõ ràng hơn —
   khi đó thêm thông báo lỗi tiếng Việt dễ hiểu.
6. Giải thích ngắn gọn cho người dùng: nguyên nhân, đã sửa gì, cách tránh. Ghi một dòng vào
   **Nhật ký tiến độ** trong `docs/HANDOFF.md` nếu lỗi đáng chú ý.
