# Font cho phụ đề

Thả file `.ttf` / `.otf` vào thư mục này rồi đặt đúng **tên font** (không phải tên file)
vào `config/settings.yaml` → `phu_de.font`. Khi thư mục có font, `s7_render` tự truyền
`fontsdir` cho FFmpeg nên không cần cài font vào hệ điều hành.

Gợi ý font có đủ dấu tiếng Việt: **Be Vietnam Pro**, **Roboto**, **Montserrat**
(tải từ Google Fonts, giấy phép SIL Open Font License).

Nếu để trống, phụ đề dùng font hệ thống theo `phu_de.font` (mặc định `Arial`).

File font **không** được commit lên GitHub — xem `.gitignore`.
