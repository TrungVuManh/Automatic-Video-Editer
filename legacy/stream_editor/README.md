# stream-auto-editor

Pipeline tự động cắt highlight và chèn meme cho video stream game, dùng **Claude** để ra quyết
định và **FFmpeg** để dựng. Một lệnh cho mỗi VOD; người chỉ cần duyệt khoảng 15–20 phút.

```
VOD + chat ──► transcript, âm lượng ──► ứng viên (máy lọc) ──► Claude chọn & cắt ──► duyệt ──► render
   bước 1            bước 2                 bước 3                 bước 4            4b     ngang + dọc
                                                                                            có phụ đề
```

## Trạng thái

| Tuần | Nội dung | Trạng thái |
|---|---|---|
| 1 | Tải VOD/chat, transcript, chấm điểm ứng viên, Claude chọn clip, duyệt, render ngang | ✅ |
| 2 | Định dạng dọc (facecam trên / gameplay dưới), phụ đề karaoke | ✅ |
| 3 | Thư viện meme có nhãn, Claude chèn meme, script kiểm tra mật độ | ⏳ |
| 4 | Trang duyệt HTML, vòng phản hồi, metadata (tiêu đề, mô tả, thumbnail) | ⏳ |

Đặc tả chi tiết và nhật ký tiến độ: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Cài đặt

**1. Công cụ hệ thống**

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) (bản đầy đủ, có `ffplay`) — thêm vào `PATH`
- Nếu dùng Twitch: [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader/releases) — thêm vào `PATH`

**2. Thư viện Python**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
```

**3. Nhận dạng giọng nói (cần GPU NVIDIA để chạy nhanh)**

Cài PyTorch bản CUDA theo hướng dẫn tại pytorch.org, sau đó:

```bash
pip install -r requirements-asr.txt
```

Nếu WhisperX khó cài trên Windows, đổi `asr.backend` thành `faster-whisper` trong `config/settings.yaml`.

**4. API key**

```bash
cp .env.example .env     # rồi điền ANTHROPIC_API_KEY
```

**5. Kiểm tra lại toàn bộ**

```bash
python run.py doctor
```

In bảng cho biết thiếu gì và cách khắc phục. Mục `[ HỎNG ]` phải xử lý hết; `[THIẾU ]`
là tùy chọn (ví dụ TwitchDownloaderCLI chỉ cần khi lấy chat Twitch).

## Sử dụng

**Tạo preset streamer** (một lần): sao chép `config/streamer_example.yaml` thành
`config/<ten>.yaml` và sửa phong cách, từ khóa, nội dung cấm. Mô tả phong cách càng cụ thể,
Claude chọn clip càng đúng gu.

**Chạy cho một VOD:**

```bash
# Bước 1–4: tải, transcript, lọc ứng viên, Claude chọn clip
python run.py all --job 2026-09-10_vod01 --streamer ten --platform youtube --url "https://..."

# Duyệt clip trên terminal: y giữ / n loại / p xem thử / s để sau
python run.py review --job 2026-09-10_vod01

# Render bản xem nhanh 480p, rồi bản cuối
python run.py render --job 2026-09-10_vod01 --preview
python run.py render --job 2026-09-10_vod01 --format ca-hai
```

`--format` nhận `ngang` (YouTube), `doc` (Shorts/TikTok 1080×1920) hoặc `ca-hai`; bỏ trống
thì lấy `render.dinh_dang` trong `settings.yaml`. Kết quả ở `jobs/<job>/final/`:
`c01_ngang.mp4`, `c01_doc.mp4`… và `highlight_<định dạng>.mp4` ghép sẵn.

Phụ đề karaoke (chữ đổi màu theo lời nói) được burn sẵn, dựng từ timestamp theo từ trong
`transcript/words.json`. Tắt bằng `render.phu_de: false`. File `.ass` sinh ra được giữ lại ở
`jobs/<job>/subs/` để sửa tay nếu cần.

Mỗi bước bỏ qua nếu output đã tồn tại, nên có thể chạy lại từ giữa chừng. Muốn làm lại một
bước, xóa file output của bước đó (ví dụ `candidates/candidates.json`) rồi chạy lại.

Chạy thử với video có sẵn (không tải): thay `--url` bằng `--video duong_dan.mp4`
(và `--chat chat.json` nếu có).

## Cấu trúc

```
config/          settings.yaml (chung) + preset từng streamer
prompts/         prompt gửi Claude
assets/fonts/    font riêng cho phụ đề (tùy chọn — xem README trong đó)
pipeline/        mỗi bước một module
meme_library/    library.jsonl (mô tả meme) — file media không commit
feedback/        examples.jsonl — lịch sử duyệt, đưa vào prompt lần sau
jobs/<job>/      dữ liệu từng VOD (không commit)
tests/           pytest — chạy không cần GPU hay API key
```

## Tinh chỉnh

- **Ứng viên sai nhiều?** Chạy `python run.py inspect --job X` để xem bảng điểm từng tín hiệu
  (chat, âm lượng, từ khóa) tại mỗi đỉnh, rồi chỉnh `candidates.refs` và `candidates.weights`
  trong `settings.yaml`. Cột `p.*` là điểm sau chuẩn hóa: luôn kịch trần 1.5 thì tăng mức
  tham chiếu tương ứng, luôn ~0 thì giảm.
- **Claude chọn không đúng gu?** Viết lại `phong_cach` trong preset, và ghi chú khi duyệt —
  ghi chú được đưa vào prompt ở lần chạy sau.
- **Phụ đề lệch hoặc thiếu dấu?** Chữ tô theo `transcript/words.json`; nếu file này rỗng thì
  WhisperX chưa căn được theo từ — điền `asr.align_model` (model wav2vec2 tiếng Việt) hoặc đổi
  `asr.backend` sang `faster-whisper`. Thiếu dấu là do font: thả file font vào `assets/fonts/`
  và đặt tên font vào `phu_de.font`.
- **Facecam bị cắt lệch ở bản dọc?** Đo lại `facecam` trong preset streamer trên một khung hình
  thật, và chỉnh `doc.gameplay_center_x`. Streamer không bật cam thì đặt `doc.kieu: khong_cam`.
- **Xem prompt thực tế đã gửi:** `jobs/<job>/candidates/prompt_last.md`.
- **Chi phí API:** `jobs/<job>/usage.json` ghi token vào/ra và ước tính USD từng lần gọi.
- **Báo lỗi:** gửi kèm `jobs/<job>/pipeline.log` (ghi đầy đủ cả lệnh FFmpeg).

## Lưu ý bản quyền

Nhạc nền trong stream và meme cắt từ phim/TV là nguồn dính Content ID phổ biến nhất. Ghi rõ
nguồn và giấy phép của từng meme trong `library.jsonl`, và luôn duyệt bản preview trước khi đăng.
