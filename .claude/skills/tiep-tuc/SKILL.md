---
name: tiep-tuc
description: Tiếp tục phát triển dự án theo lộ trình trong docs/HANDOFF.md — xác định hạng mục tiếp theo, lập kế hoạch, triển khai, viết test, cập nhật nhật ký. Dùng khi người dùng gõ /tiep-tuc, hoặc nói "làm tiếp", "sang bước sau", "làm phần tiếp theo".
---

# Tiếp tục dự án

1. Đọc `docs/HANDOFF.md`: **Quyết định đã chốt** (mục 4), **Lộ trình** (mục 5), **Checklist**
   (mục 6) và **Nhật ký** (mục 8). Nếu người dùng chỉ định hạng mục thì làm hạng mục đó; nếu
   không, làm iteration đánh dấu "TIẾP THEO". Đọc các mục SPEC mà lộ trình trỏ tới
   (`docs/SPEC.md §…`).
2. Đọc code hiện có liên quan (module, test, config) trước khi đề xuất gì.
3. Nếu cần thông tin chỉ người dùng biết (video mẫu, GPU, cài thư viện, gu meme...), hỏi
   trước — gộp thành một lượt hỏi ngắn.
4. **Trình bày kế hoạch và dừng lại chờ đồng ý.** Kế hoạch gồm: file tạo/sửa, hàm chính và
   chữ ký, định dạng JSON/config mới, thư viện cần cài, test sẽ viết, cách kiểm tra thủ công,
   rủi ro, và chỗ nào định làm khác SPEC (kèm lý do).
5. Triển khai theo từng bước nhỏ. Logic là hàm thuần; viết test cho hàm thuần trước hoặc
   song song. Tuân thủ mọi quy tắc trong `CLAUDE.md`.
6. Chạy `.venv\Scripts\python -m pytest -q` và `.venv\Scripts\ruff check src tests` đến khi
   xanh. Nếu có video trong `data/input/` hoặc người dùng cung cấp, chạy thử thủ công và báo
   kết quả (kèm lệnh để người dùng tự xem file output).
7. Cập nhật `docs/HANDOFF.md`: tick checklist, cập nhật mục 2 nếu module/định dạng thay đổi,
   ghi quyết định mới vào mục 4, chuyển nhãn "TIẾP THEO" ở mục 5, thêm một mục vào Nhật ký.
   Cập nhật bảng trạng thái trong `README.md`.
8. Tóm tắt ngắn cho người dùng bằng tiếng Việt và đề xuất commit message. Chỉ commit khi
   người dùng đồng ý.
