# Creative Motion Lab

Website edit video tự động. Giao diện chạy trên trình duyệt; các việc nặng như dựng video theo beat, khử tiếng ồn và gắn phụ đề do **máy chủ Python chạy ngầm** trên máy của bạn đảm nhận.

## Chạy lần đầu (Windows)

1. Cài **Python 3.10+** từ python.org (nhớ tick *Add Python to PATH*).
2. Cài **FFmpeg**: mở PowerShell và chạy `winget install Gyan.FFmpeg`, sau đó mở lại cửa sổ.
3. Nhấp đúp **`start.bat`**. Lần đầu script sẽ tạo `.venv` và cài thư viện, mất khoảng 1–2 phút. Xong thì trình duyệt tự mở `http://localhost:8000`.

Góc dưới trang có chấm **xanh "Máy chủ đã kết nối"** là đã chạy thật. Đóng cửa sổ đen là tắt máy chủ.

> Mở thẳng `frontend/index.html` vẫn xem được giao diện (chế độ xem thử), nhưng chỉ xử lý thật khi `start.bat` đang chạy.

### Bật AI tạo phụ đề và dịch

Không cần gõ lệnh. Trên web, mở **Dịch phụ đề tự động**, chọn video rồi bấm **"Tạo phụ đề bằng AI"**:

- Nếu máy chưa có AI, trang sẽ hỏi **"Cài ngay"**. Máy chủ sẽ tự chạy ngầm:
  1. Cài `faster-whisper` (nhận diện giọng nói) và `deep-translator` (dịch).
  2. Tải model Whisper `small`, khoảng 480 MB.
  3. Thử dịch một câu.
- Toàn bộ chỉ làm một lần, cần có mạng, mất khoảng 5–15 phút.
- Cài xong, trang tự tạo phụ đề cho video đang chọn.

Một số lưu ý:
- **Dịch bằng Google Dịch** nên cần mạng, và nội dung phụ đề sẽ được gửi tới Google.
- **Muốn dịch offline:** tự cài Argos Translate (xem `requirements-ai.txt`). Máy chủ sẽ ưu tiên Argos nếu có gói ngôn ngữ phù hợp.
- **Máy chậm:** chạy `set WHISPER_MODEL=base` trước `start.bat` để dùng model nhẹ hơn.

### Giọng đọc AI (lồng tiếng) – 10 thứ tiếng, miễn phí

Trong **Dịch phụ đề tự động**, chọn tab ngôn ngữ muốn đọc, chọn giọng (mỗi tiếng có một giọng nữ
và một giọng nam), chỉnh mức "Giọng gốc" rồi bấm **"Tạo giọng đọc AI"**. Lần đầu web sẽ hỏi cài
thư viện `edge-tts` (khoảng 1 MB). Hỗ trợ: Việt, Anh, Nhật, Hàn, Trung, Thái, Pháp, Tây Ban Nha,
Đức, Nga. Dùng giọng của Microsoft Edge: không cần tài khoản, cần có mạng; đây là cách dùng không
chính thức nên chỉ hợp cho demo/dự án cá nhân. Mã nằm ở `backend/workers/voiceover.py`, có sẵn chỗ
để thêm bộ máy đọc khác (VieNeu offline, ElevenLabs).

## Cấu trúc

```
creative-motion-lab/
├── start.bat              chạy máy chủ + mở website
├── frontend/              website (index.html, img/)
├── backend/
│   ├── main.py            FastAPI: /api/health, /api/jobs, phát website
│   ├── jobs.py            hàng đợi việc (SQLite) + luồng worker chạy ngầm
│   ├── media.py           gọi FFmpeg/FFprobe, giải mã âm thanh
│   ├── setup_ai.py        (tùy chọn) tải gói dịch offline Argos
│   └── workers/
│       ├── beat_sync.py   dò beat (numpy) -> cắt, thêm hiệu ứng, ghép video theo nhịp
│       ├── denoise.py     khử tiếng ồn bằng bộ lọc afftdn của FFmpeg
│       └── subtitles.py   faster-whisper -> dịch -> gắn phụ đề vào video
├── tests/                 kiểm thử worker bằng video/nhạc tự tạo
└── data/                  (tự tạo) file tải lên, kết quả, jobs.db – tự xóa sau 3 ngày
```

## Cách hoạt động

1. Website gửi file lên `POST /api/jobs` và nhận lại một **mã việc**.
2. Worker lấy việc ra làm **lần lượt từng việc một**, để máy RAM 8GB không bị quá tải.
3. Cứ mỗi giây website hỏi `GET /api/jobs/{id}` để cập nhật thanh tiến độ. Khi xong, website phát video kết quả và hiện nút tải về.

| Chức năng trên web | Loại việc | Xử lý |
|---|---|---|
| Edit theo nhạc → "Bắt đầu chỉnh sửa" | `beat_sync` | Dò beat, cắt theo đúng các điểm cắt trên timeline, thêm hiệu ứng flash, zoom, shake, glitch, velocity; tối đa 60 giây |
| Khử tiếng ồn → "Áp dụng & tiếp tục" | `denoise` | `highpass` + `afftdn` (+ `dynaudnorm` ở mức Mạnh mẽ) |
| Phụ đề → "Tạo phụ đề bằng AI" → "Cài ngay" | `setup_ai` | pip install requirements-ai.txt + tải model Whisper |
| Phụ đề → "Tạo phụ đề bằng AI" | `subtitles` (transcribe) | faster-whisper + Google Dịch (hoặc Argos offline) |
| Phụ đề → "Áp dụng & tiếp tục" | `subtitles` (apply) | In phụ đề đã sửa lên video bằng FFmpeg |

Các ý tưởng lấy từ những repo đã tham khảo:
- Cách cắt rồi ghép bằng FFmpeg, xuất `yuv420p` + `faststart`: theo `composer.py` của *SaarD00/AI-Youtube-Shorts-Generator*.
- Quy trình Whisper: theo *znyupup/ai-video-editing-skill*.
- Không chép nguyên code của repo nào.

## Kiểm thử

```powershell
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest tests -q
```

## Việc nên làm tiếp

- **Editor:** nút "Xuất video" chưa nối máy chủ (cần thêm worker `render` đọc timeline).
- **Nhiều người dùng cùng lúc:** thay `JobQueue` bằng Celery/RQ + Redis. Các file worker giữ nguyên.
- **Khử ồn giọng nói tốt hơn:** thay `afftdn` bằng DeepFilterNet.
- **Repo pyCapCut** không có giấy phép, chỉ nên dùng cho mục đích cá nhân.

## Trình dựng theo cách Vidlab (mới)

Thêm vào `backend/editor/`: một trình dựng nhiều track mà **người và AI agent cùng sửa một project**.

- **Một cửa duy nhất (EditorCore):** mọi thay đổi timeline là một *lệnh*; mỗi lệnh là một phiên bản trong `data/editor/editor.db`, nên hoàn tác/làm lại được từng bước.
- **Không ghi đè nhau:** agent gửi kèm `expected_version`; nếu bạn vừa sửa tay thì lệnh của agent bị từ chối thay vì xóa mất chỗ bạn sửa. Khóa sửa giữa các agent tự hết hạn sau 120 giây.
- **Nối với AI có sẵn:** cắt theo beat dùng bộ dò beat của `beat_sync.py`; phụ đề, khử ồn, lồng tiếng chạy bằng worker cũ rồi đưa kết quả lên timeline.
- **Xuất video:** việc `render` chạy chung hàng đợi, kiểm tra file sau khi xuất (độ dài, khung đen, đoạn lặng).
- **Bảo mật:** máy chủ chỉ nhận tên máy `localhost`/`127.0.0.1` (403 với tên lạ); mọi API ghi cần header `X-CML: 1`.

**Trang trình dựng:** chạy `start.bat` rồi mở http://localhost:8000/editor.html (hoặc bấm **Editor** trên website).
Kéo thả media xuống timeline, kéo/co kéo clip, cắt (S), xóa (Del), hoàn tác (Ctrl+Z), thêm chữ, màu phim, và bảng **AI**:
dựng theo nhạc, áp mẫu, phụ đề tự động, khử ồn. Khi AI agent sửa qua MCP, timeline tự cập nhật trong khoảng 1 giây.
Xem trước trên trang là gần đúng (màu phim mô phỏng bằng CSS); file xuất mới là kết quả chính xác.

Thử API: mở http://localhost:8000/docs (nhóm **editor**).

### Nối Claude Code qua MCP

File `.mcp.json` ở thư mục này đã cấu hình sẵn. Mở Claude Code trong thư mục `creative-motion-lab`
**trong lúc `start.bat` đang chạy**, rồi nói ví dụ: *"Nhập các clip trong D:\test-media, dựng theo mẫu
game-highlight với bài nhạc nhac.mp3, rồi xuất video."* Cổng MCP không cần cài thêm thư viện.

### Kiểm thử trình dựng

Nhấp đúp `kiem-tra-editor.bat`. Kết quả ghi vào `kiem-tra-ket-qua.txt`.
