# Auto Meme Video Editor (`automeme`)

AI phân tích lời thoại trong video tiếng Việt, tìm khoảnh khắc nên chèn meme/reaction, tìm
meme phù hợp theo ngữ nghĩa và render vào đúng lúc. Chạy local: **faster-whisper** nghe,
**Ollama** quyết định, **FFmpeg** dựng.

```
video → audio → transcript → LLM tìm khoảnh khắc → tìm & xếp hạng meme → timeline.json → duyệt → render
```

Mọi quyết định của AI nằm trong `timeline.json` để người sửa được trước khi render — AI không
render trực tiếp.

## Trạng thái

| Bước | Nội dung | Trạng thái |
|---|---|---|
| Stage A | Khung dự án, cấu hình + profile, log, `automeme doctor` | ✅ |
| Iteration 1 | `automeme transcribe` → `transcript.json` | ✅ |
| Iteration 2 | `timeline.json` + render meme PNG/JPG/GIF | ✅ |
| Iteration 3 | Ollama/Claude tìm khoảnh khắc → `analysis.json` | ✅ |
| Iteration 4 | Tìm + xếp hạng meme → `automeme run` | ✅ |
| Stage F | Cache/invalidation + resume toàn pipeline | ✅ |
| Stage G | Web UI local để duyệt timeline và render | ✅ |
| Studio UI | Dashboard, upload, pipeline, editor và kho meme trong một giao diện | ✅ |

**Hướng dẫn chi tiết** (cài đặt từng bước, cấu hình, xử lý sự cố):
[`docs/GUIDE.md`](docs/GUIDE.md). Đặc tả đầy đủ: [`docs/SPEC.md`](docs/SPEC.md). Tiến độ và các
quyết định đã chốt: [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Cài đặt (Windows, PowerShell)

**1. Công cụ hệ thống**

- Python 3.10+ (khuyên 3.11)
- FFmpeg: `winget install Gyan.FFmpeg`
- Ollama: `winget install Ollama.Ollama`, rồi `ollama pull qwen3:8b`
- Docker Desktop — chỉ cần nếu dùng Meme Search

**2. Môi trường Python**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

PowerShell chặn script thì chạy một lần:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
Không muốn kích hoạt venv: gọi thẳng `.\.venv\Scripts\automeme.exe` hoặc
`.\.venv\Scripts\python.exe -m automeme`.

Nhận dạng giọng nói (cần cho `transcribe`): `python -m pip install -e ".[asr-cuda]"` khi có
GPU NVIDIA — nhóm này kèm sẵn cuBLAS và cuDNN nên không phải cài CUDA Toolkit. Máy không có
GPU: `python -m pip install -e ".[asr]"`.

Phân tích bằng Ollama (cần cho `analyze`): `python -m pip install -e ".[llm]"`.

**3. Kiểm tra**

```powershell
automeme doctor
```

Mục `[ HỎNG ]` phải xử lý hết; `[THIẾU ]` là thứ chưa cần cho bước hiện tại.

## Sử dụng

```powershell
automeme --help
automeme doctor                              # kiểm tra môi trường
automeme transcribe data\input\video.mp4     # lời thoại + thời điểm từng từ
automeme transcribe data\input\video.mp4 --force   # nhận dạng lại
automeme analyze data\input\video.mp4        # transcript → analysis.json
automeme analyze data\input\video.mp4 --force     # gọi LLM phân tích lại
automeme install-memes                             # cài kho 100 meme có nhãn song ngữ
automeme install-gifs                              # cài thêm 30 reaction GIF động
automeme run data\input\video.mp4 --profile funny # chạy trọn pipeline MVP
automeme review data\input\video.mp4               # duyệt trên giao diện web local
automeme studio                                     # mở giao diện đầy đủ (khuyên dùng)
```

### Dùng giao diện AutoMeme Studio

```powershell
automeme studio
automeme studio --profile funny --port 8765
automeme studio --no-browser --port 0
```

Studio mở trong trình duyệt và gom toàn bộ quy trình vào một nơi: kéo-thả video, chọn profile,
theo dõi từng bước AI, tiếp tục từ cache, duyệt/chỉnh meme trên waveform, đọc transcript,
render/tải output và quản lý metadata kho meme. Server chỉ bind `127.0.0.1`, có token phiên và
không cần Internet để tải giao diện.

Frontend tận dụng các dự án mã nguồn mở đã vendoring để chạy offline: Plyr, WaveSurfer.js,
SortableJS, Lucide và FilePond. Phiên bản, nguồn và giấy phép xem
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Node/npm chỉ cần khi người phát triển muốn
dựng lại vendor bằng `npm install && npm run build:studio`; người dùng ứng dụng không cần Node.

Trong trang **Kho meme**, bấm **Cài bộ 100 meme** để tải 100 template phổ biến vào máy. Có thể
dùng CLI tương đương `automeme install-memes`. Catalog đi kèm nhãn ngữ nghĩa Việt–Anh; AI tìm
theo reaction rồi rank theo cảm xúc, phong cách, chất lượng và độ mới. Ba template nhạy cảm
được giữ để nhận diện nhưng đặt `safe=false`, nên không bao giờ được chọn tự động.

Bấm **Cài 30 GIF động** hoặc chạy `automeme install-gifs` để thêm reaction chuyển động. GIF
được lấy từ hai kho GitHub, ghim theo commit, kiểm tra đúng MIME và có ít nhất hai frame trước
khi đưa vào thư viện. Prompt AI đặt style `animated` cho phản ứng cần chuyển động để ranker ưu
tiên GIF; 2 GIF có chữ thô tục/nhân vật chính trị mặc định `safe=false`.

`transcribe` cần faster-whisper: `python -m pip install -e ".[asr-cuda]"` (máy không có GPU
NVIDIA thì dùng `".[asr]"` rồi đặt `WHISPER_DEVICE=cpu`). Lần chạy đầu tải model khoảng 3 GB.
Kết quả ở `data/transcripts/<tên-video>.json`; chạy lại thì bỏ qua vì đã có cache.

`analyze` cần transcript có sẵn và Ollama đang chạy với model đã tải. Kết quả ở
`data/analysis/<tên-video>.json`; mọi output đều qua schema pydantic, JSON hỏng được thử lại
một lần, rồi code áp ngưỡng confidence, cooldown, mật độ, duration và timing cuối câu.

`run` tìm meme local theo metadata/tên file; nếu có token thì dùng Meme Search vector API và
fallback về local khi dịch vụ lỗi. Sau đó lệnh sinh timeline, kiểm tra và render. Bạn vẫn có
thể duyệt hoặc sửa timeline rồi render lại:

```powershell
automeme inspect data\timelines\video.timeline.json --video data\input\video.mp4
automeme review data\input\video.mp4
automeme render data\input\video.mp4
```

`review` chỉ mở trên `127.0.0.1`: phát video kèm meme preview, hiển thị transcript, cho
Accept/Reject, thay meme trong thư viện, chỉnh thời điểm/vị trí/tỉ lệ và bấm Render. Sự kiện
rejected vẫn nằm trong timeline để hoàn tác nhưng renderer sẽ bỏ qua.

`inspect` in bảng sự kiện, báo lỗi chặn render (thiếu file meme, meme vượt quá thời lượng video,
hai meme cùng vị trí trùng giờ) và cảnh báo mềm (meme quá dày, quá dài). `render` ghi ra
`data/output/<tên-video>_automeme.mp4`, giữ nguyên tiếng gốc. Cách viết timeline: xem
[`docs/GUIDE.md`](docs/GUIDE.md) mục 5.4.

Lệnh chạy trọn MVP (SPEC §78):

```powershell
automeme run input.mp4 --profile funny
```

## Cấu hình

Thứ tự ưu tiên, cao đè thấp:

```
cờ CLI  >  biến môi trường / .env  >  profile (--profile)  >  configs/default.yaml
```

- `configs/default.yaml` — đủ mọi khóa, có chú thích.
- `configs/subtle.yaml`, `funny.yaml`, `chaotic.yaml` — profile, chỉ ghi khóa muốn đổi.
- `.env` — cấu hình của máy (model Whisper, `cuda`/`cpu`, địa chỉ Ollama…). Tên biến xem
  `.env.example`. Tham số dựng video (`MEME_COOLDOWN`…) để dạng comment: bỏ comment sẽ đè
  **mọi** profile.

Gõ sai tên khóa hoặc giá trị ngoài khoảng cho phép sẽ bị báo lỗi, không bị lặng lẽ bỏ qua.

Log hiện trên console và ghi đầy đủ (kèm nguyên lệnh FFmpeg) vào `data/logs/automeme.log` —
gửi file này khi báo lỗi.

## Cấu trúc

```
configs/         default.yaml + profile
prompts/         prompt gửi LLM (từ Iteration 3)
src/automeme/    cli, config, doctor, pipeline, cache, workspace, media/ (FFmpeg),
                 transcription/ (faster-whisper), timeline/ (schema + kiểm tra),
                 analyzer/ (context + Ollama/Claude), memes/ (local/API + ranking),
                 timeline/ (schema + builder), rendering/ (filtergraph), review/ (quick review),
                 studio/ (dashboard + editor + asset library), utils/
tests/           pytest — không cần GPU hay Ollama; test FFmpeg tự bỏ qua nếu máy không có
data/            input, cache, transcripts, analysis, timelines, output, logs — không commit
assets/          media không commit; có `library.example.jsonl` làm mẫu metadata
docs/            GUIDE.md (hướng dẫn), SPEC.md (đặc tả gốc), HANDOFF.md (tiến độ, quyết định)
legacy/          code cũ stream-auto-editor (cắt highlight stream game) — không bảo trì
```

## Phát triển

```powershell
pytest -q
ruff check src tests
```

## Bản quyền

License cho code chưa chọn (SPEC §83 gợi ý MIT hoặc Apache-2.0). Repo không commit media meme.
Lệnh cài tải template do người dùng đăng lên Imgflip và ghi nguồn/cảnh báo quyền sử dụng vào
metadata; việc tải được không đồng nghĩa media là mã nguồn mở. Hãy tự kiểm tra quyền trước khi
đăng hoặc dùng thương mại.
