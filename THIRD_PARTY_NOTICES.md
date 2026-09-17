# Third-party notices

AutoMeme Studio phân phối các bản build JavaScript/CSS sau để giao diện chạy hoàn toàn offline.
Toàn văn giấy phép tương ứng được giữ tại `src/automeme/studio/static/vendor/licenses/`.

| Thành phần | Phiên bản | Giấy phép | Nguồn |
|---|---:|---|---|
| FilePond | 4.32.12 | MIT | https://github.com/pqina/filepond |
| Lucide | 1.45.0 | ISC | https://github.com/lucide-icons/lucide |
| Plyr | 3.8.4 | MIT | https://github.com/sampotts/plyr |
| SortableJS | 1.15.7 | MIT | https://github.com/SortableJS/Sortable |
| WaveSurfer.js | 7.12.12 | BSD-3-Clause | https://github.com/katspaugh/wavesurfer.js |

Các thư viện trên chỉ được dùng ở frontend; runtime Python của `automeme` không phụ thuộc npm.

## Thư viện Python để tải video YouTube

| Thành phần | Phiên bản tối thiểu | Giấy phép | Nguồn |
|---|---:|---|---|
| yt-dlp | 2026.8.19 | Unlicense (public domain) | https://github.com/yt-dlp/yt-dlp |

yt-dlp được cài như một phụ thuộc pip (khai báo trong `pyproject.toml`), không được sao chép vào
repository. Video tải về nằm trong `data/input/` và bị `.gitignore` loại khỏi repository; giấy
phép của từng video được ghi trong file `.source.json` đi kèm. Điều khoản của YouTube hạn chế việc
tải video — người dùng tự chịu trách nhiệm chỉ tải nội dung mình có quyền sử dụng.

## Sound effect assets (không nằm trong Git)

Lệnh `automeme install-sfx` tải một tập con 30 file từ **Kenney Interface/Impact/Digital
Sounds**, giấy phép **CC0 1.0**. URL tải dùng mirror
`chenisan/AudioSFX/assets/sfx-library/files` và được ghim tại commit
`fa851a79288bf0ee81cdf6faa9430bbbed48b292`; ứng dụng không sao chép mã nguồn của repository
mirror. Trang nguồn chính thức: https://kenney.nl/assets/interface-sounds. Media tải về nằm
trong `assets/sfx/` và bị `.gitignore` loại khỏi repository.
