---
name: tiep-tuc
description: Tiếp tục phát triển dự án theo lộ trình trong docs/HANDOFF.md — xác định hạng mục tiếp theo, lập kế hoạch, triển khai, viết test, cập nhật nhật ký. Dùng khi người dùng gõ /tiep-tuc, hoặc nói "làm tiếp", "sang tuần sau", "làm phần tiếp theo".
---

# Tiếp tục dự án

1. Đọc `docs/HANDOFF.md`: mục **Checklist tổng** và **Nhật ký tiến độ**, rồi đọc mục đặc tả
   của hạng mục liên quan. Nếu người dùng chỉ định hạng mục cụ thể thì làm hạng mục đó;
   nếu không, chọn ô chưa tick đầu tiên trong checklist.
2. Đọc code hiện có liên quan (module, test, config) trước khi đề xuất gì.
3. Nếu đặc tả cần thông tin chỉ người dùng biết (nền tảng, layout facecam, GPU, phong cách
   kênh...), hỏi trước — gộp thành một lượt hỏi ngắn.
4. **Trình bày kế hoạch và dừng lại chờ đồng ý.** Kế hoạch gồm: file tạo/sửa, hàm chính và
   chữ ký, định dạng JSON/config mới, test sẽ viết, cách kiểm tra thủ công, rủi ro.
5. Triển khai theo từng bước nhỏ. Logic là hàm thuần; viết test cho hàm thuần trước hoặc
   song song. Tuân thủ mọi quy tắc trong `CLAUDE.md`.
6. Chạy `pytest -q` đến khi xanh. Nếu có sẵn video trong `jobs/` hoặc người dùng cung cấp,
   chạy thử thủ công và báo kết quả (kèm lệnh để người dùng tự xem file output).
7. Cập nhật `docs/HANDOFF.md`: tick checklist, cập nhật mục 2 nếu định dạng/module thay đổi,
   thêm một mục vào **Nhật ký tiến độ** (đã làm, quyết định, vấn đề tồn tại).
8. Tóm tắt ngắn cho người dùng bằng tiếng Việt và đề xuất commit message. Chỉ commit khi
   người dùng đồng ý.
