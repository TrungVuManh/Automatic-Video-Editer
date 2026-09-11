# Thư viện meme

Mỗi dòng trong `library.jsonl` mô tả một meme. Claude chọn meme **chỉ dựa trên mô tả**,
nên cột `dung_khi` càng cụ thể thì kết quả càng đúng.

| Trường | Ý nghĩa |
|---|---|
| `id` | Tên duy nhất, không dấu, không cách |
| `file` | Đường dẫn tương đối trong `meme_library/`, hoặc `null` với hiệu ứng |
| `type` | `sfx` · `image` · `greenscreen` · `effect` |
| `dung_khi` | Tình huống nên dùng |
| `dai` | Thời lượng (giây) |
| `nguon` | Nguồn và giấy phép — bắt buộc điền để tránh Content ID |

File media không được commit lên GitHub (xem `.gitignore`); chỉ commit `library.jsonl`.
