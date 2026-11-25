# Báo cáo kỹ thuật — Creative Motion Lab

**Sinh viên:** Minh Hiển — IT108-K26, PTIT (liên kết Rikkei)
**Dự án:** Creative Motion Lab — website tự động chỉnh sửa video (phụ đề AI, lồng tiếng AI, khử ồn, xóa nền, màu phim)

---

## 1. Mục tiêu và phạm vi

Xây dựng một website chạy cục bộ (local) giúp người dùng phổ thông chỉnh sửa video nhanh mà không cần biết dựng phim chuyên nghiệp, tập trung vào 4 tính năng lõi:

1. **Tự động tạo phụ đề** từ giọng nói trong video (nhận diện + dịch).
2. **Lồng tiếng bằng giọng AI** (text-to-speech nhiều ngôn ngữ).
3. **Tùy chỉnh phông chữ phụ đề** (phông, cỡ, màu, đậm/thường).
4. **Khử tiếng ồn** trong âm thanh gốc.

Ngoài ra giữ lại hai tính năng đã làm trước: **xóa nền video** (background removal bằng AI) và **áp màu phim** (LUT đơn giản). Các tính năng không nằm trong phạm vi trên — dựng video theo nhịp nhạc, áp mẫu dựng sẵn — đã được loại bỏ khỏi giao diện để sản phẩm gọn và đúng trọng tâm.

## 2. Kiến trúc hệ thống

```
Trình duyệt (frontend/)  <——HTTP/JSON——>  FastAPI (backend/)  ——subprocess——>  FFmpeg / FFprobe
                                               │
                                               ├── jobs.py       hàng đợi việc nền (SQLite), 1 việc/lần
                                               ├── workers/      mỗi tính năng AI là 1 worker độc lập
                                               └── editor/       trình dựng nhiều track (timeline)
                                                    ├── store.py    lưu project dạng "version" (event-sourced)
                                                    ├── core.py     áp các lệnh sửa (add_clip, set_project, ...)
                                                    ├── render.py   dựng timeline -> 1 lệnh FFmpeg để xuất video
                                                    └── api.py      REST cho frontend (và MCP cho AI agent)
```

**Vì sao thiết kế như vậy:**

- **Không dùng thư viện xử lý video nặng bằng Python** (moviepy, v.v.) mà gọi thẳng FFmpeg qua `subprocess` — nhanh hơn, ít lỗi hơn, và máy cấu hình thấp (RAM 8GB) vẫn chạy được vì FFmpeg xử lý ở tầng native.
- **Hàng đợi việc tuần tự** (`jobs.py`, SQLite): mỗi lần chỉ chạy 1 việc nặng (phụ đề/khử ồn/xóa nền...), tránh máy quá tải khi nhiều việc chạy cùng lúc.
- **Project được lưu theo phiên bản (event sourcing)**: mỗi thao tác sửa timeline là một bản ghi "version" trong SQLite thay vì ghi đè trực tiếp — nhờ đó có **Undo/Redo** đúng từng bước, và nhiều "tác nhân" (người dùng, AI agent qua MCP) có thể cùng sửa một project mà không đè lệnh của nhau (kiểm tra `expected_version` trước khi áp lệnh).
- **Giao diện "trống trước, hiện dần sau"** (lấy cảm hứng từ Vidlab): mở một dự án mới chỉ thấy một khung lớn "Thả video vào đây để bắt đầu"; toàn bộ timeline, bảng công cụ AI chỉ hiện ra sau khi đã có ít nhất một clip trên timeline. Mục đích: người dùng lần đầu không bị choáng bởi hàng chục nút chưa dùng tới.

## 3. Xử lý từng tính năng AI

| Tính năng | Công nghệ | Ghi chú kỹ thuật |
|---|---|---|
| Phụ đề tự động | `faster-whisper` (nhận diện giọng nói) + Google Dịch / Argos Translate (dịch) | Kết quả ghi ra file `.srt`, gắn vào video bằng bộ lọc `subtitles` của FFmpeg (dựa trên `libass`) |
| Lồng tiếng AI | `edge-tts` (giọng đọc của Microsoft Edge) | 10 ngôn ngữ, mỗi ngôn ngữ có giọng nam/nữ; không cần tài khoản, cần mạng |
| Khử tiếng ồn | Bộ lọc `highpass` + `afftdn` (+ `dynaudnorm`) của FFmpeg | Xử lý thuần tín hiệu số, không cần model AI riêng |
| Tùy chỉnh phông chữ phụ đề | `force_style` của bộ lọc `subtitles` (chuẩn ASS/libass) | Phông, cỡ chữ, màu, đậm/thường lưu ở cấp **project**, áp dụng đồng nhất cho mọi dòng chữ khi xuất, khớp với bản xem trước |
| 6 mẫu kiểu chữ phụ đề | Bộ tham số ASS định sẵn (`CAPTION_PRESETS`) | Cổ điển, Nền đen, Pop Art, Kẹo ngọt, Bút dạ quang, Cam tươi — mỗi mẫu đặt màu viền, độ dày viền, nền đặc (`BorderStyle=3`) và chữ nghiêng; xem trước trên web mô phỏng bằng CSS `text-shadow` |
| Che phụ đề gốc | `drawbox` (hộp đen) hoặc `split`+`crop`+`boxblur`+`overlay` (làm mờ) | Vùng che lưu theo **phần trăm khung hình** nên đổi độ phân giải vẫn đúng chỗ; chạy **trước** bộ lọc phụ đề để phụ đề mới nằm đè lên vùng vừa che |
| Xóa nền video | Model **RVM (Robust Video Matting)** chạy qua `onnxruntime` (CPU) | Suy luận từng khung hình, giữ trạng thái đệ quy (recurrent state) giữa các khung để nền không bị "nhấp nháy"; xuất ra định dạng giữ kênh alpha (ProRes 4444 / QuickTime RLE) |
| Màu phim | Bộ lọc màu FFmpeg định sẵn theo từng "look" | Xem trước mô phỏng bằng CSS filter, file xuất dùng đúng công thức FFmpeg |

## 4. Hai lỗi phát hiện và cách sửa

### 4.1. Lỗi `UnicodeEncodeError` khi chạy script trên Windows

**Hiện tượng:** Script Python tự kiểm thử tính năng xóa nền bị dừng giữa chừng, báo lỗi mã hóa ký tự khi `print()` ra tiếng Việt có dấu.

**Nguyên nhân:** Cửa sổ dòng lệnh (console) mặc định của Windows dùng bảng mã cp1252/cp437, không mã hóa được một số ký tự tiếng Việt.

**Cách sửa:** Ép `stdout`/`stderr` của script sang UTF-8 bằng `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`, đồng thời đặt biến môi trường `PYTHONIOENCODING=utf-8` trong script PowerShell gọi nó.

### 4.2. Đường dẫn file bị "gãy" sau khi đổi tên thư mục (lỗi nghiêm trọng hơn)

**Hiện tượng:** Mọi tính năng AI trên trình dựng (khử ồn, phụ đề, xóa nền, xuất video) đều báo lỗi `FileNotFoundError` dù file thật vẫn còn trên ổ đĩa.

**Nguyên nhân:** Cơ sở dữ liệu `editor.db` lưu **đường dẫn tuyệt đối** tới từng file media (ví dụ `D:\ba-vạn-chín-nghìn\...`). Khi thư mục dự án được đổi tên (bỏ dấu tiếng Việt), toàn bộ đường dẫn cũ trong database trở nên sai, nhưng file vật lý vẫn nằm nguyên trong thư mục `data/editor/media/`.

**Cách tìm ra:** Đọc trực tiếp log lỗi trên cửa sổ dòng lệnh, đối chiếu với dữ liệu thô trong bảng `media` của SQLite bằng `sqlite3`, phát hiện cột `path` trỏ tới một thư mục không còn tồn tại.

**Cách sửa:** Thêm cơ chế **"tự chữa đường dẫn"** (`_heal_path`) vào `Store.get_media()`/`list_media()`: nếu đường dẫn lưu trong database không còn tồn tại, hệ thống tự tìm file theo **tên file** (basename) trong đúng thư mục media hiện tại, và ghi đè lại đường dẫn đúng vào database. Nhờ vậy hệ thống tự phục hồi mà không cần người dùng làm gì, kể cả nếu thư mục bị đổi tên lần nữa.

## 5. Tham khảo mã nguồn mở (ghi nhận minh bạch)

- **Vidlab 0.3.6** (xây trên **OpenChatCut**, giấy phép **AGPL-3.0-or-later**): nguồn cảm hứng chính cho giao diện trình dựng (giao diện tối màu, luồng "trống trước — hiện dần sau" khi chưa có video, cách sắp xếp bảng công cụ AI theo tab). Giao diện của Creative Motion Lab được **viết lại hoàn toàn bằng HTML/CSS/JS thuần** (Vidlab dùng React + TypeScript + Vite), không sao chép mã nguồn của Vidlab/OpenChatCut.
- **RVM (Robust Video Matting)**, model ONNX dùng cho tính năng xóa nền — dự án gốc cấp phép **GPL-3.0** (bản `rvm_resnet50`), chỉ dùng cho mục đích học tập/demo cá nhân, không phân phối lại model.
- **faster-whisper, edge-tts, deep-translator, Argos Translate**: các thư viện mã nguồn mở dùng nguyên bản qua `pip`, không chỉnh sửa mã nguồn của chúng.
- Cách cắt/ghép video bằng FFmpeg (`yuv420p`, `faststart`) tham khảo cấu trúc từ *SaarD00/AI-Youtube-Shorts-Generator*; quy trình gọi Whisper tham khảo từ *znyupup/ai-video-editing-skill* — không chép nguyên code, chỉ tham khảo cách tổ chức lệnh FFmpeg.

> Vì RVM dùng giấy phép GPL/AGPL dạng "copyleft mạng", nếu triển khai Creative Motion Lab thành dịch vụ công khai cho nhiều người dùng (không chỉ chạy cục bộ), cần công khai mã nguồn phần liên quan theo đúng điều khoản giấy phép.

## 6. Kết quả kiểm thử

- Kiểm thử tự động có sẵn (`tests/`) cho các worker khử ồn, phụ đề: `pytest tests -q`.
- Kiểm thử thủ công trực tiếp trên trình duyệt (qua Chrome DevTools/console) cho từng thay đổi trong phiên làm việc này:
  - Xóa 4 file mẫu khỏi ổ đĩa và database — xác nhận file thật không bị ảnh hưởng.
  - Giao diện trống (first-run) hiện đúng khi project chưa có clip nào trên timeline, và chuyển sang giao diện đầy đủ ngay khi thêm 1 clip — đã thử thêm rồi hoàn tác (Undo) để xác nhận trạng thái quay lại đúng như cũ.
  - Tùy chỉnh phông chữ phụ đề: đổi giá trị, xác nhận lưu đúng vào project qua API, hoàn tác về giá trị gốc.
  - Toàn bộ thao tác thử nghiệm đều được hoàn tác (Undo) sau khi xác nhận hoạt động đúng, không để lại dữ liệu rác trong project thật của người dùng.

## 7. Hướng phát triển tiếp theo

- Cho phép tùy chỉnh phông chữ **theo từng dòng phụ đề** riêng lẻ (hiện tại áp dụng chung cho cả project).
- Thay model RVM (GPL) bằng một model xóa nền giấy phép thoáng hơn (MIT/Apache) nếu muốn phát hành rộng rãi.
- Viết thêm test tự động cho các API mới của trình dựng (`/media/{id}/delete`, `set_project` với trường `caption_*`).
