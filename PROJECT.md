# PROJECT.md

Đọc file này đầu mỗi phiên làm việc. Cập nhật sau mỗi mốc.

## Quyết định và lý do
- **Giữ nguyên các worker cũ, thêm trình dựng bên cạnh** (`backend/editor/`). Không fork OpenChatCut: dự án đã chạy được bằng Python + FFmpeg trên máy RAM 8GB.
- **Mọi thay đổi timeline đi qua EditorCore** (`core.py`), mỗi lệnh là một phiên bản SQLite. Lệnh `batch` gom một thao tác AI thành một bước hoàn tác.
- **Chọn clip trên giao diện không gửi lên máy chủ** (Vidlab P4): chỉ thay đổi thật mới là lệnh.
- **Xuất video chạy trong hàng đợi chung** (kind `render`), một việc nặng mỗi lúc.
- **Cổng MCP tự viết, không cần thư viện `mcp`**: nói JSON-RPC qua stdin/stdout, gọi API của máy chủ.
- **File nhập vào trình dựng đổi tên ASCII ngắn**; video tốc độ khung hình thay đổi (VFR) được chuyển sang 30 fps cố định.
- **Chặn Host lạ (403)** và đòi header `X-CML: 1` cho mọi API ghi.
- **Thư mục dữ liệu** chỉnh được bằng `CML_DATA_DIR` (mặc định vẫn là `data/`).
- Bản cũ của file đã sửa giữ ở `backend/main.py.truoc-editor.bak`, `backend/jobs.py.truoc-editor.bak`.

## Đã kiểm chứng
- **Trên máy Windows của bạn, 19/11/2026 11:48: 18/18 bài trong `tests/test_editor.py` đạt** (`kiem-tra-editor.bat`).
- Hoàn tác/làm lại, tách clip, batch, từ chối bản cũ, khóa tự hết hạn.
- Cắt theo beat bằng bộ dò có sẵn → thêm phụ đề tiếng Việt → xuất 540x960 dài 6 s, file qua kiểm tra.
- Khoảng trống thành khung đen; kết quả việc phụ đề đưa đúng lên track chữ, đúng độ lệch.
- API: Host lạ bị 403, thiếu header X-CML bị 403, tạo project/sửa/hoàn tác qua HTTP chạy đúng.
- Cổng MCP trả lời initialize và tools/list; máy chủ tắt thì báo lỗi chứ không sập.
- Lỗi tìm thấy khi chạy trên Windows: FFmpeg bản mới bỏ `-filter_complex_script`. Đã sửa (tự chọn `-/filter_complex` theo phiên bản) và có bài kiểm thử giữ lại.

## Chưa kiểm chứng
- MCP với Claude Code thật; phụ đề/khử ồn qua trình dựng trên video thật của bạn.

## Chưa làm
- Giao diện cho trình dựng: bạn tự thiết kế (gọi `/api/editor/...`, hỏi `GET /api/editor/projects/{id}?since_version=N` mỗi giây để thấy chỗ AI sửa).
- Xóa nền người, làm đẹp khuôn mặt, chồng nhiều lớp video, chuyển cảnh, keyframe.

## Bước tiếp theo
1. Chạy `start.bat`, mở http://localhost:8000/docs, thử tạo project và xuất video.
2. Đổi tên `mcp-mau.json` thành `.mcp.json`, mở Claude Code trong thư mục này, thử dựng một video qua MCP.
