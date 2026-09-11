# Auto Meme Video Editor

> AI tự động phân tích hội thoại trong video, xác định những khoảnh khắc phù hợp để chèn meme/reaction, tìm meme theo ngữ nghĩa và render chúng vào đúng timestamp.

**Status:** Early Development / MVP  
**Primary language:** Python  
**Target platform:** Windows 10/11  
**AI-first, local-first, open-source-first**

---

# 1. Giới thiệu

Auto Meme Video Editor là một công cụ mã nguồn mở nhằm tự động hóa quy trình:

```text
Video
  ↓
Speech-to-Text
  ↓
Transcript + Timestamp
  ↓
Context Analysis
  ↓
Meme Decision
  ↓
Semantic Meme Search
  ↓
Meme Ranking
  ↓
Timeline Generation
  ↓
Video Rendering
  ↓
Final Video
```

Ví dụ video có đoạn:

```text
00:13.20

MC:
"Và tổng chi phí cho đám cưới này chỉ khoảng 300 triệu thôi."
```

AI có thể nhận diện đây là một tình huống có khả năng tạo reaction:

```json
{
  "insert_meme": true,
  "timestamp": 13.2,
  "emotion": "shock",
  "intent": "reaction",
  "search_query": "person shocked after hearing an unexpectedly high price"
}
```

Hệ thống tìm meme phù hợp trong thư viện local:

```text
memes/
├── shocked_man.jpg
├── confused_math_lady.jpg
├── crying_inside.jpg
└── surprised_cat.gif
```

sau đó sinh timeline:

```json
{
  "start": 13.4,
  "duration": 1.4,
  "asset": "surprised_cat.gif",
  "mode": "overlay",
  "position": "bottom-right"
}
```

và cuối cùng dùng FFmpeg render thành video mới.

---

# 2. Mục tiêu của dự án

Mục tiêu của phiên bản đầu tiên là xây dựng pipeline có khả năng:

- Nhận đầu vào `.mp4`, `.mov`, `.mkv`.
- Trích xuất âm thanh.
- Speech-to-text tiếng Việt.
- Có timestamp cho từng đoạn thoại.
- Phân tích ngữ cảnh hội thoại.
- Quyết định đoạn nào đáng chèn meme.
- Sinh câu truy vấn meme bằng ngôn ngữ tự nhiên.
- Tìm meme theo semantic similarity.
- Xếp hạng nhiều meme ứng viên.
- Chọn meme phù hợp nhất.
- Sinh timeline dạng JSON.
- Preview timeline trước khi render.
- Render meme vào video bằng FFmpeg.
- Xuất video MP4 hoàn chỉnh.
- Hoạt động local nhiều nhất có thể.

MVP **không đặt mục tiêu** tự động tạo một video hoàn hảo như editor chuyên nghiệp.

Người dùng vẫn cần có khả năng:

```text
AI Suggestion
      ↓
Review
      ↓
Accept / Reject / Replace
      ↓
Render
```

Đây là nguyên tắc quan trọng của dự án.

---

# 3. Use case chính

## 3.1 Video hội thoại

Ví dụ:

```text
A: "Anh bảo với vợ là anh đi nhậu chưa?"

B: "Chưa."

A: "Thế vợ gọi chưa?"

B: "17 cuộc rồi."
```

AI có thể đề xuất:

```text
17 cuộc rồi.
      ↓
awkward / panic reaction meme
```

---

## 3.2 Video quảng cáo

Ví dụ:

```text
"Bạn nghĩ khách sẽ nhớ sân khấu đám cưới?"

"Không."

"Họ nhớ đồ ăn."
```

AI có thể chèn:

```text
food reaction meme
```

hoặc:

```text
guy nodding aggressively
```

---

## 3.3 Podcast

AI phát hiện:

- punchline;
- câu gây sốc;
- disagreement;
- awkward silence;
- sarcasm;
- surprise;
- frustration;
- irony.

Sau đó chèn reaction meme.

---

## 3.4 TikTok / Shorts / Reels

Các hiệu ứng có thể kết hợp:

```text
meme
reaction GIF
zoom
freeze frame
sound effect
subtitle
emoji
B-roll
```

---

# 4. Kiến trúc tổng thể

```text
┌───────────────────────────────────┐
│            INPUT VIDEO            │
│             input.mp4             │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│           MEDIA PREPROCESS        │
│                                   │
│ FFmpeg                            │
│ - normalize video                 │
│ - extract audio                   │
│ - collect metadata                │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│          SPEECH TO TEXT           │
│                                   │
│ faster-whisper                    │
│                                   │
│ audio.wav                         │
│      ↓                            │
│ transcript.json                   │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│         CONTEXT ANALYZER          │
│                                   │
│ Local LLM via Ollama              │
│                                   │
│ transcript                        │
│      ↓                            │
│ meme_candidates.json              │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│          MEME RETRIEVER           │
│                                   │
│ Meme Search                       │
│ semantic retrieval               │
│                                   │
│ query                             │
│   ↓                               │
│ Top-K memes                       │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│           MEME RANKER             │
│                                   │
│ relevance                         │
│ emotion                           │
│ diversity                         │
│ timing                            │
│ duplicate penalty                 │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│       TIMELINE GENERATOR          │
│                                   │
│ timeline.json                     │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│            RENDERER               │
│                                   │
│ FFmpeg                            │
│                                   │
│ meme / gif / zoom / sfx           │
└────────────────┬──────────────────┘
                 │
                 ▼
┌───────────────────────────────────┐
│           OUTPUT VIDEO            │
│                                   │
│ output.mp4                        │
└───────────────────────────────────┘
```

---

# 5. Tech stack

## Core

```text
Python 3.10+
```

Khuyến nghị bắt đầu bằng Python 3.10 hoặc 3.11.

---

## Speech-to-Text

```text
faster-whisper
```

Nhiệm vụ:

```text
audio
  ↓
Vietnamese transcript
  ↓
segment timestamp
  ↓
word timestamp
```

---

## Local LLM

Mặc định:

```text
Ollama
```

Mô hình ban đầu có thể thử:

```text
qwen3:8b
```

Máy yếu hơn:

```text
qwen3:4b
```

Không hard-code model.

Model phải được cấu hình trong:

```text
.env
```

---

# 6. Meme Search Engine

Phiên bản đầy đủ sử dụng:

```text
Meme Search
```

Meme Search chịu trách nhiệm:

```text
Meme image
     ↓
Image description
     ↓
Embedding
     ↓
Vector database
     ↓
Semantic search
```

Ví dụ query:

```text
guy realizing he made a terrible mistake
```

không cần filename chứa:

```text
mistake
```

AI vẫn có thể tìm được meme tương ứng dựa trên nội dung.

Meme Search nên chạy như một service riêng:

```text
Auto Meme Editor
       │
       │ HTTP
       ▼
Meme Search API
       │
       ▼
Meme Database
```

Không truy cập trực tiếp database của Meme Search.

---

# 7. Video rendering

Renderer ban đầu:

```text
FFmpeg
```

Không dùng MoviePy cho render chính ở MVP.

Python chịu trách nhiệm:

```text
build command
manage assets
generate timeline
execute FFmpeg
```

FFmpeg chịu trách nhiệm:

```text
decode
scale
overlay
trim
audio
encode
GIF
video
```

---

# 8. Yêu cầu hệ thống

## Minimum

```text
Windows 10/11

Python:
3.10+

RAM:
16 GB recommended

Storage:
10 GB+

FFmpeg:
installed

Git:
installed
```

CPU-only vẫn có thể chạy.

---

## Recommended

```text
CPU:
6+ cores

RAM:
32 GB

GPU:
NVIDIA

VRAM:
8 GB+

Docker Desktop:
installed

Ollama:
installed
```

---

# 9. Kiểm tra môi trường

PowerShell:

```powershell
python --version
```

Nếu Windows có nhiều Python:

```powershell
py -0p
```

Kiểm tra Python 3.10:

```powershell
py -3.10 --version
```

Kiểm tra Git:

```powershell
git --version
```

Kiểm tra FFmpeg:

```powershell
ffmpeg -version
```

Kiểm tra Docker:

```powershell
docker --version
docker compose version
```

Kiểm tra GPU:

```powershell
nvidia-smi
```

Kiểm tra Ollama:

```powershell
ollama --version
```

---

# 10. Khởi tạo project

Tạo thư mục:

```powershell
mkdir auto-meme-video
cd auto-meme-video
```

Khởi tạo Git:

```powershell
git init
```

Tạo virtual environment:

```powershell
py -3.10 -m venv .venv
```

Activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Sau đó chạy lại:

```powershell
.\.venv\Scripts\Activate.ps1
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Nên dùng:

```powershell
python -m pip
```

thay vì gọi `pip` trực tiếp để tránh vấn đề PATH trên Windows.

---

# 11. Dependencies

File:

```text
requirements.txt
```

Ban đầu:

```text
faster-whisper
pydantic
pydantic-settings
requests
httpx
typer
rich
numpy
opencv-python
Pillow
ollama
python-dotenv
orjson

pytest
pytest-cov
ruff
```

Cài đặt:

```powershell
python -m pip install -r requirements.txt
```

---

# 12. Project structure

Cấu trúc đề xuất:

```text
auto-meme-video/
│
├── README.md
├── LICENSE
├── .gitignore
├── .env
├── .env.example
├── requirements.txt
├── pyproject.toml
│
├── assets/
│   ├── memes/
│   ├── gifs/
│   ├── sfx/
│   └── fonts/
│
├── data/
│   ├── input/
│   ├── temp/
│   ├── cache/
│   ├── transcripts/
│   ├── timelines/
│   └── output/
│
├── configs/
│   ├── default.yaml
│   ├── funny.yaml
│   └── subtle.yaml
│
├── prompts/
│   ├── meme_detector.txt
│   ├── meme_query.txt
│   └── meme_ranker.txt
│
├── src/
│   └── automeme/
│       │
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── pipeline.py
│       │
│       ├── media/
│       │   ├── __init__.py
│       │   ├── ffmpeg.py
│       │   ├── audio.py
│       │   └── probe.py
│       │
│       ├── transcription/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── whisper.py
│       │
│       ├── analyzer/
│       │   ├── __init__.py
│       │   ├── context.py
│       │   ├── llm.py
│       │   └── prompts.py
│       │
│       ├── memes/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── local.py
│       │   ├── meme_search.py
│       │   └── ranker.py
│       │
│       ├── timeline/
│       │   ├── __init__.py
│       │   ├── builder.py
│       │   ├── validator.py
│       │   └── schema.py
│       │
│       ├── rendering/
│       │   ├── __init__.py
│       │   ├── renderer.py
│       │   ├── overlay.py
│       │   └── filters.py
│       │
│       └── utils/
│           ├── files.py
│           ├── logger.py
│           └── timestamps.py
│
├── scripts/
│   ├── transcribe.py
│   ├── analyze.py
│   ├── search_memes.py
│   ├── build_timeline.py
│   └── render.py
│
└── tests/
    ├── test_transcription.py
    ├── test_analyzer.py
    ├── test_meme_search.py
    ├── test_timeline.py
    └── test_renderer.py
```

---

# 13. Thiết kế module

Một nguyên tắc quan trọng:

```text
Whisper
Ollama
Meme Search
FFmpeg
```

không được gọi trực tiếp khắp project.

Mỗi thành phần phải có adapter.

Ví dụ:

```python
class Transcriber:
    def transcribe(self, audio_path):
        raise NotImplementedError
```

Implementation:

```python
class FasterWhisperTranscriber(Transcriber):
    ...
```

Sau này có thể thêm:

```text
WhisperCppTranscriber
OpenAITranscriber
ParakeetTranscriber
```

mà không phải sửa pipeline.

Tương tự:

```python
class MemeProvider:
    def search(self, query: str, limit: int = 5):
        raise NotImplementedError
```

Implementation:

```text
LocalMemeProvider
MemeSearchProvider
```

---

# 14. Environment configuration

Tạo:

```text
.env.example
```

Nội dung:

```env
# =========================================================
# Application
# =========================================================

APP_ENV=development
LOG_LEVEL=INFO

# =========================================================
# Whisper
# =========================================================

WHISPER_MODEL=large-v3
WHISPER_LANGUAGE=vi

# cuda / cpu
WHISPER_DEVICE=cuda

# float16 / int8_float16 / int8
WHISPER_COMPUTE_TYPE=float16

WHISPER_BEAM_SIZE=5

# =========================================================
# Ollama
# =========================================================

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# =========================================================
# Meme Search
# =========================================================

MEME_SEARCH_BASE_URL=http://127.0.0.1:3000
MEME_SEARCH_TOKEN=

MEME_SEARCH_TOP_K=10

# =========================================================
# Editing
# =========================================================

MEME_MIN_DURATION=0.8
MEME_MAX_DURATION=2.5

MEME_COOLDOWN=7.0

MEME_SCORE_THRESHOLD=0.65

MAX_MEMES_PER_MINUTE=5

# =========================================================
# Output
# =========================================================

VIDEO_CODEC=libx264
AUDIO_CODEC=aac
OUTPUT_CRF=18
OUTPUT_PRESET=medium
```

Copy:

```powershell
Copy-Item .env.example .env
```

---

# 15. Phase 1 — Video preprocessing

Đầu tiên chưa cần AI.

Chỉ cần đảm bảo:

```text
input.mp4
   ↓
audio.wav
```

Command mẫu:

```powershell
ffmpeg -i data/input/input.mp4 -vn -ac 1 -ar 16000 data/temp/audio.wav
```

Mục tiêu:

```text
mono
16 kHz
PCM audio
```

Python wrapper:

```python
import subprocess
from pathlib import Path


def extract_audio(video: Path, audio: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio),
    ]

    subprocess.run(cmd, check=True)
```

---

# 16. Phase 2 — Speech-to-Text

File:

```text
src/automeme/transcription/whisper.py
```

Skeleton:

```python
from faster_whisper import WhisperModel


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_name="large-v3",
        device="cuda",
        compute_type="float16",
    ):
        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(self, audio_path):
        segments, info = self.model.transcribe(
            str(audio_path),
            language="vi",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )

        results = []

        for segment in segments:
            results.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                }
            )

        return {
            "language": info.language,
            "segments": results,
        }
```

---

# 17. Transcript schema

Không truyền object của Whisper trực tiếp sang module khác.

Normalize thành schema riêng.

Ví dụ:

```json
{
  "video": "wedding.mp4",
  "language": "vi",
  "duration": 47.83,
  "segments": [
    {
      "id": 0,
      "start": 0.42,
      "end": 3.21,
      "text": "Hôm nay chúng ta sẽ hỏi chú rể một câu."
    },
    {
      "id": 1,
      "start": 3.32,
      "end": 5.45,
      "text": "Ai là người giữ tiền trong nhà?"
    },
    {
      "id": 2,
      "start": 5.81,
      "end": 6.73,
      "text": "Tôi."
    },
    {
      "id": 3,
      "start": 7.12,
      "end": 8.73,
      "text": "Vợ tôi giữ hộ."
    }
  ]
}
```

Output:

```text
data/transcripts/wedding.json
```

---

# 18. Phase 3 — Context windows

Không nên gửi từng câu độc lập cho LLM.

Ví dụ câu:

```text
"Vợ tôi giữ hộ."
```

không hài nếu đứng một mình.

Nhưng:

```text
Q:
"Ai giữ tiền trong nhà?"

A:
"Tôi."

A:
"Vợ tôi giữ hộ."
```

lại có punchline.

Vì vậy analyzer phải sử dụng context window.

Ví dụ:

```text
previous 2 segments
current segment
next 1 segment
```

Input:

```json
{
  "previous": [
    "Ai là người giữ tiền trong nhà?",
    "Tôi."
  ],
  "current": "Vợ tôi giữ hộ.",
  "next": []
}
```

---

# 19. Phase 4 — Meme Opportunity Detection

Đây là phần quan trọng nhất của hệ thống.

LLM **không được yêu cầu tìm meme ngay lập tức**.

Đầu tiên phải trả lời câu hỏi:

> Có nên chèn meme ở đây không?

Các tín hiệu:

```text
punchline
surprise
awkwardness
sarcasm
irony
failure
confusion
shock
embarrassment
bragging
unexpected answer
disagreement
frustration
dramatic reveal
```

---

# 20. Meme opportunity schema

```json
{
  "segment_id": 3,
  "insert_meme": true,

  "confidence": 0.91,

  "trigger": "Vợ tôi giữ hộ.",

  "reason": "The speaker initially claims control but immediately contradicts himself.",

  "emotion": "awkward realization",

  "reaction_type": "embarrassed",

  "search_query": "man realizing his wife actually controls the money",

  "preferred_style": "reaction",

  "timing": {
    "anchor": 8.73,
    "delay": 0.15,
    "duration": 1.3
  }
}
```

---

# 21. LLM system prompt

File:

```text
prompts/meme_detector.txt
```

Ví dụ:

```text
You are an AI video editor specializing in short-form comedy videos.

Analyze the supplied Vietnamese conversation.

Your job is NOT to insert as many memes as possible.

Only recommend a meme when a reaction image or short GIF would materially improve the comedic timing or audience comprehension.

Good opportunities include:

- punchlines
- surprising statements
- contradictions
- awkward situations
- irony
- sarcasm
- embarrassment
- confusion
- frustration
- sudden realization
- unexpected numbers or prices

Avoid memes for:

- normal informational statements
- introductions
- transitions
- sentences without emotional or comedic significance
- consecutive sentences where another meme was inserted recently

For every candidate return:

segment_id
insert_meme
confidence
emotion
reaction_type
reason
search_query
anchor
delay
duration

search_query must describe the VISUAL REACTION we want.

Bad:
"wedding money"

Good:
"man shocked after hearing an unexpectedly expensive price"

Return valid JSON only.
```

---

# 22. Một nguyên tắc rất quan trọng

Đừng để AI sinh query như:

```text
đám cưới
tiền
vợ
chồng
```

Đây là keyword search.

Ta cần **reaction search**.

Ví dụ:

```text
Transcript:
"Tiền của anh thì vợ anh giữ."
```

Query tệ:

```text
wife money
```

Query tốt:

```text
man smiling awkwardly after realizing he has no control
```

Đây là điểm tạo ra sự khác biệt giữa:

```text
B-roll search
```

và:

```text
Meme reaction search
```

---

# 23. Phase 5 — Local LLM

Ollama chạy độc lập với Python application.

Kiểm tra:

```powershell
ollama list
```

Download model:

```powershell
ollama pull qwen3:8b
```

Chạy thử:

```powershell
ollama run qwen3:8b
```

Python:

```python
from ollama import chat


def analyze_context(prompt: str):
    response = chat(
        model="qwen3:8b",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.message.content
```

Production code không hard-code model.

Dùng:

```python
settings.ollama_model
```

---

# 24. Structured JSON

Không parse output LLM bằng regex kiểu:

```python
re.findall(...)
```

Hãy ép output về schema.

Pydantic:

```python
from pydantic import BaseModel, Field


class MemeTiming(BaseModel):
    anchor: float
    delay: float = 0.1
    duration: float = Field(ge=0.5, le=5.0)


class MemeOpportunity(BaseModel):
    segment_id: int

    insert_meme: bool

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    trigger: str

    reason: str

    emotion: str

    reaction_type: str

    search_query: str

    preferred_style: str

    timing: MemeTiming
```

Nếu JSON invalid:

```text
retry once
```

Nếu vẫn invalid:

```text
skip candidate
```

Không crash toàn bộ pipeline.

---

# 25. Phase 6 — Meme database

Tạo collection ban đầu khoảng:

```text
200–500 memes
```

Không cần hàng chục nghìn meme ở MVP.

Các nhóm nên có:

```text
shock
confused
awkward
angry
crying
laughing
facepalm
celebration
panic
disappointed
thinking
suspicious
proud
failure
success
money
relationship
waiting
silence
surprise
```

---

# 26. Meme metadata

Ngay cả khi dùng Meme Search, project vẫn nên có metadata của riêng mình.

Ví dụ:

```json
{
  "id": "meme_00042",

  "filename": "assets/memes/confused_math_lady.jpg",

  "type": "image",

  "tags": [
    "confused",
    "thinking",
    "math",
    "reaction"
  ],

  "emotion": [
    "confusion"
  ],

  "intensity": 0.8,

  "safe": true,

  "language": "none",

  "usage_count": 7
}
```

Điều này rất hữu ích khi ranking.

---

# 27. Meme Search

Meme Search nên chạy bằng Docker.

Clone repository bằng GitHub CLI:

```powershell
gh repo clone meme-search/meme-search
```

Sau đó:

```powershell
cd meme-search
docker compose up
```

Ứng dụng chính giao tiếp với Meme Search thông qua API adapter.

Không để logic Meme Search nằm trong:

```text
pipeline.py
```

Tạo:

```text
src/automeme/memes/meme_search.py
```

---

# 28. Meme provider interface

```python
from abc import ABC, abstractmethod


class MemeProvider(ABC):

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        ...
```

Meme Search implementation:

```python
class MemeSearchProvider(MemeProvider):

    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        ...
```

Fallback:

```python
class LocalMemeProvider(MemeProvider):

    def search(
        self,
        query: str,
        limit: int = 10,
    ):
        ...
```

---

# 29. Không phụ thuộc hoàn toàn vào Meme Search

MVP nên có fallback:

```text
Meme Search unavailable
        ↓
Local JSON / simple search
```

Điều này giúp development không bị block.

---

# 30. Phase 7 — Candidate ranking

Semantic similarity chưa đủ.

Ví dụ AI tìm:

```text
shocked Pikachu
shocked man
surprised cat
exploding head
```

Tất cả đều semantic-match.

Nhưng meme nào tốt nhất phụ thuộc:

```text
context
emotion
style
history
duration
```

Score:

```text
final_score =
    semantic_score   × 0.45
  + emotion_score    × 0.20
  + style_score      × 0.10
  + quality_score    × 0.10
  + novelty_score    × 0.15
```

---

# 31. Duplicate penalty

Không nên dùng cùng meme liên tục.

Ví dụ:

```python
if meme.id in recent_memes:
    score -= 0.30
```

Recent window:

```text
60 seconds
```

Có thể lưu:

```python
recent_memes = deque(maxlen=10)
```

---

# 32. Meme cooldown

Meme xuất hiện quá thường xuyên sẽ phá video.

Mặc định:

```text
MEME_COOLDOWN=7 seconds
```

Ví dụ:

```text
00:05 meme
00:08 candidate → reject
00:13 candidate → allowed
```

---

# 33. Meme density

Đặt giới hạn:

```text
MAX_MEMES_PER_MINUTE=5
```

Mode sau này:

```text
subtle:
2 memes/min

normal:
4 memes/min

chaotic:
8 memes/min
```

---

# 34. Phase 8 — Timeline

Đây là artifact quan trọng nhất của pipeline.

Ví dụ:

```json
{
  "version": 1,

  "video": "wedding.mp4",

  "events": [
    {
      "id": "event_001",

      "type": "meme",

      "start": 8.88,

      "duration": 1.35,

      "asset": "assets/memes/awkward_smile.gif",

      "confidence": 0.91,

      "query": "man smiling awkwardly after realizing he has no control",

      "mode": "overlay",

      "position": "bottom-right",

      "scale": 0.30
    }
  ]
}
```

Save:

```text
data/timelines/wedding.timeline.json
```

---

# 35. Tách analysis và render

Pipeline không được:

```text
AI → render ngay
```

Phải:

```text
AI
 ↓
timeline.json
 ↓
review
 ↓
render
```

Điều này giúp:

- debug;
- sửa meme;
- thay timestamp;
- thử renderer khác;
- không cần chạy LLM lại;
- xây GUI dễ hơn.

---

# 36. Editing modes

MVP hỗ trợ hai mode.

## Overlay

```text
┌─────────────────────────────┐
│                             │
│      ORIGINAL VIDEO         │
│                             │
│                  ┌────────┐ │
│                  │ MEME   │ │
│                  └────────┘ │
└─────────────────────────────┘
```

Mode:

```json
"mode": "overlay"
```

---

## Cutaway

```text
Original video
      ↓
Full-screen meme
      ↓
Original video
```

Mode:

```json
"mode": "cutaway"
```

MVP nên làm:

```text
overlay
```

trước.

Cutaway làm ở Phase 2.

---

# 37. Overlay position

Supported:

```text
top-left
top-right
bottom-left
bottom-right
center
```

Default:

```text
bottom-right
```

---

# 38. Meme sizing

Default:

```text
30% video width
```

Không scale theo pixel cố định.

Ví dụ video:

```text
1080 × 1920
```

meme width:

```text
324 px
```

Video:

```text
1920 × 1080
```

meme width:

```text
576 px
```

---

# 39. Render rule

Meme không được che:

```text
face
subtitle
important text
```

MVP chưa cần face detection.

Default:

```text
bottom-right
```

nhưng nếu subtitle nằm dưới:

```text
top-right
```

Sau này có thể dùng object detection để chọn vùng trống.

---

# 40. Phase 9 — FFmpeg Renderer

Pseudo-flow:

```text
input.mp4
   +
meme.png
   +
timeline event
   ↓
filter_complex
   ↓
output.mp4
```

Ví dụ conceptual filter:

```text
scale meme
    ↓
overlay
    ↓
enable between(t,start,end)
```

Renderer Python chịu trách nhiệm build filter graph.

Không tạo command bằng string concatenation.

Dùng:

```python
cmd = [
    "ffmpeg",
    ...
]
```

và:

```python
subprocess.run(cmd, check=True)
```

để tránh escaping lỗi trên Windows.

---

# 41. GIF support

GIF phải được xử lý khác ảnh tĩnh.

Meme asset schema nên có:

```json
{
  "type": "gif"
}
```

Renderer:

```text
GIF
 ↓
loop
 ↓
scale
 ↓
overlay
```

Không giả định mọi meme là PNG/JPG.

---

# 42. Audio

Meme mặc định không thay đổi audio.

Sau này có thể support:

```text
Vine boom
record scratch
bruh
dramatic hit
crowd laugh
```

Timeline:

```json
{
  "type": "sfx",
  "start": 14.2,
  "asset": "assets/sfx/vine_boom.wav",
  "gain_db": -6
}
```

---

# 43. Complete pipeline

File:

```text
src/automeme/pipeline.py
```

Pseudo-code:

```python
def process_video(video_path):

    # 1
    metadata = probe_video(video_path)

    # 2
    audio = extract_audio(video_path)

    # 3
    transcript = transcriber.transcribe(audio)

    # 4
    contexts = build_context_windows(transcript)

    # 5
    opportunities = analyzer.analyze(contexts)

    # 6
    opportunities = filter_opportunities(
        opportunities,
        confidence_threshold=0.65,
    )

    # 7
    for opportunity in opportunities:

        candidates = meme_provider.search(
            opportunity.search_query,
            limit=10,
        )

        ranked = rank_memes(
            opportunity,
            candidates,
        )

        opportunity.selected_meme = ranked[0]

    # 8
    timeline = build_timeline(
        metadata,
        opportunities,
    )

    # 9
    validate_timeline(timeline)

    # 10
    save_timeline(timeline)

    return timeline
```

Render là command riêng:

```python
renderer.render(
    input_video,
    timeline,
    output_video,
)
```

---

# 44. CLI

Mục tiêu cuối MVP:

```powershell
automeme analyze video.mp4
```

Output:

```text
✓ Audio extracted
✓ Transcript generated
✓ 27 speech segments detected
✓ 6 meme opportunities detected
✓ 4 passed confidence threshold
✓ Meme search completed

Timeline:
data/timelines/video.timeline.json
```

Preview:

```powershell
automeme inspect data/timelines/video.timeline.json
```

Render:

```powershell
automeme render video.mp4
```

Hoặc end-to-end:

```powershell
automeme run video.mp4
```

---

# 45. Typer CLI

Skeleton:

```python
import typer

app = typer.Typer()


@app.command()
def transcribe(video: str):
    pass


@app.command()
def analyze(video: str):
    pass


@app.command()
def render(video: str):
    pass


@app.command()
def run(video: str):
    pass


if __name__ == "__main__":
    app()
```

---

# 46. pyproject.toml

```toml
[project]
name = "automeme"
version = "0.1.0"
description = "AI-powered automatic meme insertion for video"
requires-python = ">=3.10"

[project.scripts]
automeme = "automeme.cli:app"
```

Development install:

```powershell
python -m pip install -e .
```

Sau đó:

```powershell
automeme --help
```

---

# 47. Logging

Mỗi stage phải log riêng.

Ví dụ:

```text
[21:03:11] INFO  Loading video
[21:03:12] INFO  Extracting audio
[21:03:15] INFO  Loading Whisper large-v3
[21:03:21] INFO  Transcribing
[21:03:32] INFO  Found 43 segments
[21:03:34] INFO  Analyzing meme opportunities
[21:03:39] INFO  Found 7 candidates
[21:03:39] INFO  Rejected 3 candidates
[21:03:40] INFO  Searching memes
[21:03:42] INFO  Timeline created
```

Không dùng `print()` khắp project.

---

# 48. Cache

Không chạy Whisper lại nếu transcript đã tồn tại.

Cache key nên phụ thuộc:

```text
video hash
Whisper model
language
settings
```

Ví dụ:

```text
cache/
└── a81dc9/
    ├── audio.wav
    ├── transcript.json
    ├── analysis.json
    └── meme_search.json
```

---

# 49. Pipeline resumability

Phải có khả năng:

```text
transcribe
    ↓
STOP

analyze
    ↓
STOP

render
```

Không bắt buộc chạy lại từ đầu.

Ví dụ:

```powershell
automeme transcribe video.mp4

automeme analyze video.mp4

automeme render video.mp4
```

---

# 50. Configuration profiles

Ví dụ:

```text
configs/subtle.yaml
```

```yaml
editing:
  max_memes_per_minute: 2
  cooldown: 12
  threshold: 0.8

meme:
  duration_min: 0.8
  duration_max: 1.5
```

Funny:

```yaml
editing:
  max_memes_per_minute: 5
  cooldown: 6
  threshold: 0.65
```

Chaotic:

```yaml
editing:
  max_memes_per_minute: 9
  cooldown: 3
  threshold: 0.5
```

Usage:

```powershell
automeme run video.mp4 --profile funny
```

---

# 51. Confidence filtering

Không tin toàn bộ LLM output.

Ví dụ:

```python
if opportunity.confidence < threshold:
    reject()
```

Ngoài ra:

```python
if opportunity.timing.duration > max_duration:
    clamp()
```

```python
if too_close_to_previous_meme:
    reject()
```

```python
if meme_already_used_recently:
    apply_penalty()
```

---

# 52. Timing strategy

Reaction thường hiệu quả hơn **sau câu nói**, không phải giữa câu.

Default:

```text
segment.end + 0.10–0.30 s
```

Ví dụ:

```text
Speaker:
"Vợ tôi quản lý tiền."

speech ends:
8.73

meme begins:
8.88
```

Delay:

```text
150 ms
```

Đây nên là configurable parameter.

---

# 53. Không để LLM tự quyết định mọi thứ

LLM đề xuất:

```text
semantic information
```

Code quyết định:

```text
hard constraints
```

LLM:

```text
emotion
reaction
query
confidence
timing suggestion
```

Code:

```text
cooldown
max meme count
duration bounds
overlap
duplicate protection
valid timestamp
asset existence
```

Đây là nguyên tắc kiến trúc quan trọng.

---

# 54. Timeline validation

Validator phải kiểm tra:

```text
start >= 0
end <= video duration
duration > 0
asset exists
no illegal overlap
valid position
valid scale
valid event type
```

Ví dụ:

```python
assert event.start >= 0

assert (
    event.start + event.duration
    <= video_duration
)
```

---

# 55. Meme safety

Một số meme có thể:

```text
NSFW
racist
political
offensive
copyright-sensitive
```

Metadata nên có:

```json
{
  "safe": true,
  "nsfw": false,
  "political": false
}
```

MVP nên mặc định:

```text
safe memes only
```

---

# 56. Copyright

Phần mềm có thể open source nhưng **meme asset không tự động trở thành open source**.

Do đó repository chính không nên bundle hàng nghìn ảnh meme lấy từ Internet.

Recommended:

```text
repo
├── code
└── example assets only
```

Người dùng tự thêm:

```text
assets/memes/
```

hoặc kết nối collection của mình.

---

# 57. Unit tests

## Transcription

Test:

```text
audio exists
transcript not empty
timestamps monotonic
```

---

## Analyzer

Input:

```text
"Giá cái này 20 triệu."

"20 triệu á?"
```

Expect:

```text
candidate exists
confidence valid
query not empty
```

---

## Timeline

Ensure:

```text
no negative timestamp
no event outside video
no invalid duration
```

---

## Renderer

Dùng video sample 5 giây.

Render một PNG từ:

```text
1.0 → 2.0 s
```

Sau đó kiểm tra:

```text
output exists
duration ≈ 5 seconds
exit code = 0
```

---

# 58. Integration test

File:

```text
tests/assets/sample.mp4
```

Pipeline:

```text
sample.mp4
 ↓
sample.wav
 ↓
transcript
 ↓
analysis
 ↓
timeline
 ↓
render
 ↓
sample_output.mp4
```

Một integration test thành công là milestone rất quan trọng.

---

# 59. MVP roadmap

## Milestone 0 — Environment

Hoàn thành khi:

```text
Python works
FFmpeg works
Ollama works
Docker works
GPU visible
```

---

## Milestone 1 — Transcription

Command:

```powershell
automeme transcribe video.mp4
```

phải sinh:

```text
transcript.json
```

Không làm LLM trước khi bước này ổn định.

---

## Milestone 2 — Meme detector

Command:

```powershell
automeme analyze video.mp4
```

phải sinh:

```text
analysis.json
```

Trong đó AI xác định:

```text
3–10 potential meme moments
```

---

## Milestone 3 — Manual meme overlay

Chưa cần Meme Search.

Timeline thủ công:

```json
{
  "start": 5.2,
  "duration": 1.5,
  "asset": "assets/memes/test.png"
}
```

Renderer phải chèn được meme.

Đây là bước cực kỳ quan trọng.

Nếu chưa render được 1 meme ổn định thì chưa làm semantic search.

---

## Milestone 4 — Meme Search integration

Input:

```text
awkward man realizing he made a mistake
```

Output:

```text
top 10 memes
```

---

## Milestone 5 — Auto selection

Kết nối:

```text
LLM
 ↓
query
 ↓
Meme Search
 ↓
ranker
 ↓
timeline
```

---

## Milestone 6 — End-to-end

Command:

```powershell
automeme run video.mp4
```

phải sinh:

```text
output/video_automeme.mp4
```

mà không cần sửa code.

---

# 60. Thứ tự code khuyến nghị

Đừng bắt đầu từ GUI.

Làm theo đúng thứ tự:

```text
1. FFmpeg video → audio

2. faster-whisper → transcript.json

3. FFmpeg manual meme overlay

4. timeline.json

5. timeline → FFmpeg renderer

6. Ollama → meme opportunities

7. Meme Search → candidates

8. ranking

9. full pipeline

10. preview UI

11. desktop/web UI
```

Đặc biệt:

```text
Whisper
+
Renderer
```

nên hoàn thành trước:

```text
LLM
+
Semantic Search
```

---

# 61. Definition of Done cho MVP

MVP được coi là hoàn thành khi:

```text
Given:
1 video tiếng Việt dài 30–90 giây

System can:
✓ transcribe automatically
✓ preserve timestamps
✓ detect meme opportunities
✓ generate reaction queries
✓ retrieve meme candidates
✓ choose suitable assets
✓ prevent excessive meme usage
✓ create editable timeline JSON
✓ render memes automatically
✓ preserve original audio
✓ export MP4

Without:
manual modification of Python source
```

---

# 62. Chất lượng cần đánh giá

Không nên chỉ đánh giá:

```text
Does it run?
```

Cần đánh giá ba thứ.

## Meme Timing Accuracy

```text
Meme xuất hiện đúng lúc không?
```

## Meme Relevance

```text
Meme có đúng tình huống không?
```

## Meme Density

```text
Có quá nhiều meme không?
```

---

# 63. Dataset đánh giá nội bộ

Tạo:

```text
evaluation/
├── videos/
├── annotations/
└── results/
```

Annotation:

```json
{
  "video": "001.mp4",

  "moments": [
    {
      "start": 12.1,
      "end": 13.4,
      "should_have_meme": true,
      "reaction": [
        "shock",
        "confused"
      ]
    }
  ]
}
```

Khoảng:

```text
30–50 short videos
```

đã đủ hữu ích để benchmark phiên bản đầu.

---

# 64. Metrics tương lai

Opportunity detection:

```text
Precision
Recall
F1
```

Retrieval:

```text
Recall@5
Recall@10
MRR
```

Human evaluation:

```text
Relevance
Timing
Humor
Annoyance
```

Ví dụ rating:

```text
1–5
```

---

# 65. Architecture tương lai

Sau MVP:

```text
Transcript
   +
Audio emotion
   +
Video frames
   ↓
Multimodal Context Analyzer
```

AI khi đó không chỉ nghe lời thoại.

Nó còn hiểu:

```text
facial expression
visual action
pause
speaker emotion
scene
gesture
```

Ví dụ người nói không nói gì nhưng nhìn camera:

```text
awkward stare
```

AI vẫn có thể chèn meme.

---

# 66. Speaker diarization

Phiên bản đầu chưa cần.

Sau này:

```text
Speaker A
Speaker B
Speaker C
```

sẽ giúp AI hiểu hội thoại tốt hơn.

Pipeline:

```text
audio
 ↓
diarization
 ↓
speaker-aware transcript
```

Ví dụ:

```text
Speaker A:
"Anh có sợ vợ không?"

Speaker B:
"Không."

Speaker B:
"Em nói thế được chưa vợ?"
```

Context mạnh hơn nhiều.

---

# 67. Scene understanding

Sau này sampling:

```text
1 frame / second
```

hoặc tại:

```text
candidate timestamps
```

Sau đó dùng VLM để nhận dạng:

```text
person expression
setting
object
action
```

---

# 68. Meme recommendation UI

UI tương lai:

```text
┌───────────────────────────────┐
│ VIDEO                         │
│                               │
│        preview                │
│                               │
├───────────────────────────────┤
│ Transcript                    │
│                               │
│ 00:13.4 "300 triệu thôi..."   │
│                               │
├───────────────────────────────┤
│ AI Meme Suggestion            │
│                               │
│ [meme 1] [meme 2] [meme 3]   │
│                               │
│ Accept     Reject             │
├───────────────────────────────┤
│ Timeline                      │
│ ────────[MEME]────────────    │
└───────────────────────────────┘
```

---

# 69. GUI technology

Không làm trong MVP.

Sau khi CLI ổn định có thể cân nhắc:

```text
Gradio
Streamlit
PySide6
Tauri
React
```

Nếu muốn desktop editor thật sự:

```text
Tauri + frontend
        │
        ▼
Python backend
```

là hướng đáng cân nhắc.

---

# 70. API architecture tương lai

```text
Frontend
   │
   ▼
FastAPI
   │
   ├── /transcribe
   ├── /analyze
   ├── /memes/search
   ├── /timeline
   └── /render
```

Nhưng không cần FastAPI trong MVP CLI đầu tiên.

---

# 71. Optional sound-effect system

Sau meme có thể thêm:

```text
SFX Retriever
```

AI output:

```json
{
  "insert_sfx": true,
  "sfx_type": "dramatic_hit"
}
```

Sau đó:

```text
assets/sfx/
├── dramatic_hit.wav
├── record_scratch.wav
├── pop.wav
└── crowd_laugh.wav
```

---

# 72. Optional automatic zoom

Timeline:

```json
{
  "type": "zoom",
  "start": 17.2,
  "duration": 0.7,
  "scale": 1.15
}
```

Sau này có thể tạo:

```text
Meme
+
Zoom
+
SFX
```

cho cùng một punchline.

---

# 73. Event model tổng quát

Nên thiết kế timeline từ đầu để không chỉ hỗ trợ meme.

```text
Event
├── MemeEvent
├── SoundEvent
├── ZoomEvent
├── CaptionEvent
├── FreezeFrameEvent
└── BrollEvent
```

Ví dụ:

```json
{
  "type": "meme"
}
```

hoặc:

```json
{
  "type": "sfx"
}
```

---

# 74. Development principles

### Local-first

Ưu tiên:

```text
local transcription
local LLM
local meme index
local rendering
```

---

### Deterministic renderer

AI không render trực tiếp.

AI tạo:

```text
structured edit instructions
```

Renderer thực thi chúng.

---

### Human editable

Mọi quyết định phải tồn tại dưới dạng:

```text
JSON
```

để con người sửa được.

---

### Replaceable components

Không khóa project với:

```text
Whisper
Ollama
Meme Search
```

Mỗi component phải có interface.

---

### Fail gracefully

Nếu Meme Search chết:

```text
fallback
```

Nếu Ollama output sai:

```text
retry / skip
```

Nếu một meme lỗi:

```text
skip meme
```

Không làm hỏng toàn bộ video.

---

# 75. Git branches

Có thể dùng:

```text
main
develop
feature/transcription
feature/timeline
feature/renderer
feature/ollama
feature/meme-search
```

---

# 76. First commits

Gợi ý commit history:

```text
chore: initialize project structure

feat: add ffmpeg audio extraction

feat: add faster-whisper transcription

feat: add transcript schema

feat: add timeline schema

feat: add static meme overlay renderer

feat: add ollama context analyzer

feat: add meme opportunity detector

feat: integrate meme search provider

feat: add meme ranking

feat: implement end-to-end pipeline
```

---

# 77. .gitignore

```gitignore
.venv/
__pycache__/
*.pyc

.env

data/input/*
data/temp/*
data/cache/*
data/output/*
data/transcripts/*
data/timelines/*

assets/memes/*
assets/gifs/*

models/

.pytest_cache/
.coverage

.vscode/
.idea/
```

Có thể thêm:

```text
.gitkeep
```

vào các folder cần giữ.

---

# 78. Lệnh chạy mong muốn cuối cùng

Simple:

```powershell
automeme run input.mp4
```

Advanced:

```powershell
automeme run input.mp4 `
    --profile funny `
    --language vi `
    --whisper large-v3 `
    --max-memes 5
```

Chỉ analyze:

```powershell
automeme analyze input.mp4
```

Render lại mà không chạy AI:

```powershell
automeme render `
    input.mp4 `
    --timeline data/timelines/input.timeline.json
```

---

# 79. Development checklist

## Stage A

```text
[ ] Project structure
[ ] Virtual environment
[ ] Configuration
[ ] Logging
[ ] FFmpeg detection
```

## Stage B

```text
[ ] Extract audio
[ ] Whisper model loading
[ ] Vietnamese transcription
[ ] Timestamp normalization
[ ] Save transcript.json
```

## Stage C

```text
[ ] Timeline schema
[ ] Manual timeline
[ ] PNG overlay
[ ] JPG overlay
[ ] GIF overlay
[ ] MP4 output
```

## Stage D

```text
[ ] Ollama adapter
[ ] Prompt manager
[ ] Context windows
[ ] Meme opportunity detection
[ ] JSON validation
```

## Stage E

```text
[ ] Meme Search installation
[ ] Meme Search adapter
[ ] Semantic query
[ ] Top-K retrieval
[ ] Ranking
[ ] Duplicate penalty
```

## Stage F

```text
[ ] Complete pipeline
[ ] Cache
[ ] Resume
[ ] Error handling
[ ] Integration tests
```

## Stage G

```text
[ ] Preview UI
[ ] Accept/reject meme
[ ] Replace meme
[ ] Adjust timestamp
[ ] Render
```

---

# 80. Việc đầu tiên cần làm

Không triển khai toàn bộ kiến trúc cùng lúc.

Iteration đầu tiên chỉ cần đạt:

```text
input.mp4
    ↓
audio.wav
    ↓
transcript.json
```

Iteration thứ hai:

```text
input.mp4
    +
manual timeline.json
    +
meme.png
    ↓
output.mp4
```

Iteration thứ ba:

```text
transcript.json
    ↓
Ollama
    ↓
analysis.json
```

Iteration thứ tư:

```text
analysis.json
    ↓
Meme Search
    ↓
timeline.json
    ↓
FFmpeg
```

Khi bốn bước này hoạt động riêng lẻ, mới nối thành:

```text
automeme run input.mp4
```

---

# 81. MVP success example

Input:

```text
video.mp4
```

Transcript:

```text
00:04.1
"Anh có sợ vợ không?"

00:06.0
"Không."

00:07.3
"Đúng không em?"
```

Analysis:

```json
{
  "segment_id": 2,
  "insert_meme": true,
  "confidence": 0.94,
  "emotion": "awkward",
  "reaction_type": "nervous",
  "search_query": "man nervously checking if his wife approves"
}
```

Retrieval:

```text
1. nervous_smile.gif      0.91
2. sweating_man.jpg       0.86
3. awkward_monkey.jpg     0.81
```

Timeline:

```json
{
  "type": "meme",
  "start": 8.1,
  "duration": 1.3,
  "asset": "nervous_smile.gif",
  "position": "top-right"
}
```

Result:

```text
output.mp4
```

Nếu pipeline thực hiện được ví dụ này ổn định thì core MVP đã thành công.

---

# 82. Project vision

Mục tiêu dài hạn không chỉ là:

```text
AI meme inserter
```

mà là:

```text
Open-source AI Short-Form Video Editor
```

Architecture:

```text
                   Video
                     │
                     ▼
            Content Understanding
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
    Speech         Vision        Audio
       │             │             │
       └─────────────┼─────────────┘
                     ▼
               Story Context
                     │
                     ▼
              Editing Agent
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
       Meme         B-roll         SFX
        │            │             │
        ├────────────┼─────────────┤
        ▼            ▼             ▼
      Zoom        Caption       Effects
        │            │             │
        └────────────┼─────────────┘
                     ▼
                Timeline
                     │
                     ▼
                  FFmpeg
                     │
                     ▼
                Final Short
```

---

# 83. License

Khuyến nghị cho phần source code:

```text
MIT
```

hoặc:

```text
Apache-2.0
```

Asset meme cần được quản lý license riêng.

---

# 84. Priority

Trong giai đoạn đầu:

```text
Quality of meme timing
        >
Number of features
```

và:

```text
Quality of meme selection
        >
Number of memes inserted
```

Một video có:

```text
3 meme rất đúng
```

tốt hơn:

```text
15 meme gần đúng.
```

---

# 85. TL;DR

Stack ban đầu:

```text
Python
    │
    ├── faster-whisper
    │       └── speech → transcript
    │
    ├── Ollama
    │       └── transcript → meme opportunity
    │
    ├── Meme Search
    │       └── query → meme candidates
    │
    ├── Meme Ranker
    │       └── candidates → selected meme
    │
    ├── Timeline
    │       └── editing instructions
    │
    └── FFmpeg
            └── timeline → final video
```

Development order:

```text
Whisper
   ↓
Manual Renderer
   ↓
Timeline
   ↓
LLM
   ↓
Meme Search
   ↓
Ranker
   ↓
Full Pipeline
   ↓
GUI
```

**Đừng bắt đầu bằng GUI. Hãy làm cho `automeme run input.mp4` hoạt động ổn định trước.**