# Web MCQ — offline

Công cụ đọc ảnh câu hỏi từ Clipboard Windows, tìm nội dung trong bài giảng và trả lời bằng model GGUF chạy ngay trên máy. Màn hình kết quả chỉ hiện chữ cái, trạng thái copy và trang tài liệu tham khảo.

## Cài trên máy Windows khác

1. Tải ZIP repository hoặc `git clone`, giải nén vào thư mục bạn có quyền ghi.
2. Khi còn Internet, mở **`setup_windows.bat`**. Script kiểm tra/cài Python 3.12 x64 qua `winget` nếu cần, tạo `.venv`, cài thư viện Python, tải **Qwen2.5-3B Q4_K_M** và **llama.cpp b11159** từ nguồn chính thức, kiểm tra SHA-256 rồi chạy `doctor.py`. Mạng bị ngắt giữa chừng thì chạy lại để tiếp tục tải. Cần khoảng 5 GiB ổ trống cho lần cài CUDA; model khoảng 2.1 GB.
3. Mở `fast_v2\run_fast_solver_visible.bat` để xem cửa sổ kiểm thử, chọn lại vùng câu hỏi trên màn hình của bạn. Bản chạy nền là `fast_v2\run_fast_solver.bat`.

Nếu muốn bỏ OCR cho chữ trên trang web, cài thêm [extension Chrome/Edge](fast_v2/browser_extension/README.md). Mở ứng dụng một lần trước khi tải extension; sau đó chỉ cần cho phép extension đọc trang bài tập và vẽ vùng như cũ. Khi không lấy được HTML, V2 tự dùng OCR ảnh.

Script tự chọn CUDA nếu thấy GPU NVIDIA; nếu không sẽ dùng CPU (chậm hơn). Có thể chọn rõ bằng `setup_windows.bat -Backend cpu` hoặc `-Backend cuda`. Chạy `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1 -VerifyOnly` để **chỉ kiểm tra**, không cài/tải. Nếu máy thiếu `winget`, cài Python 3.12 x64 từ [python.org](https://www.python.org/downloads/windows/) rồi chạy lại. Lần cài đầu cần Internet; lúc giải câu hỏi thì toàn bộ model, OCR và tài liệu đều ở máy. File cấu hình vùng/phím `fast_v2/ui_settings.json` là cục bộ, không được chia sẻ qua Git.

## Dùng ngay trên máy này

1. Mở `run_exam_solver.bat`, đợi dòng **Sẵn sàng**.
2. Nhấn **Win + Shift + S**, chụp trọn một câu hỏi và cả A, B, C, D. Chữ cần đủ lớn, rõ nét.
3. Quay lại cửa sổ tool, nhấn **Enter**. Đáp án được tự copy; **Ctrl + V** để dán.
4. Nhấn **q** để thoát và giải phóng model/GPU.

Nếu báo thiếu RAM, đóng bớt ứng dụng rồi mở lại. Tool kiểm tra tối thiểu 1,5 GiB RAM trống trước khi nạp model; trên máy hiện tại đã có lúc RAM trống chỉ khoảng 820 MiB, làm lần nạp bổ sung vượt 90 giây. Khoảng 2–3 GiB RAM trống giúp tránh phải phân trang nhiều, nhưng tốc độ thực tế còn phụ thuộc tải máy.

Lệnh **m** chuyển sang nhiều đáp án, **s** sang một đáp án, **a** tự nhận dạng. Dùng **n** nếu câu có 2–8 phương án thay vì mặc định 4. **v** hiển thị văn bản OCR gần nhất khi cần kiểm tra.

`auto` ưu tiên chỉ dẫn “Select one”, “Choose two”, “Select all”, “one or more” và nhận dạng câu “Which … are …”. Ngữ pháp không xác định được mọi dạng multi-select; dùng **m/s** khi loại câu hỏi đã rõ. Tool không tự thao tác hay nộp câu trả lời trên Moodle.

## Độ chính xác, tốc độ và nhiệt

- Mục tiêu là 90%; số đo cụ thể nằm trong `artifacts/validation-report.md` và các file JSON benchmark. Đây là bộ kiểm thử do người phát triển soạn từ tài liệu, chưa phải đề thật độc lập. Không suy rộng kết quả thành cam kết 90% trên mọi đề.
- Sai một lựa chọn trong câu nhiều đáp án được tính là sai cả câu. Câu từ chối trả lời/lỗi cũng được tính là sai, không loại ra để nâng điểm.
- OCR dùng mô hình ONNX cục bộ, Lanczos 2×, tương phản 2×, viền trắng; giữ thứ tự theo tọa độ dòng. Nếu thiếu nhãn, thử ảnh gốc một lần rồi yêu cầu chụp lại. Không chia đôi B để bịa nội dung C.
- Mô hình giữ trong bộ nhớ giữa các câu; sau 15 giây không dùng, server ngủ và tự nạp lại khi có câu mới. CPU/OCR giới hạn 2 luồng; vòng chờ không quay liên tục. Khi xử lý liên tiếp, có khoảng nghỉ mặc định 4 giây sau lần suy luận trước. Thời gian chụp/đọc câu tiếp theo được tính vào khoảng nghỉ này.
- Tool kiểm tra nhiệt GPU trước mỗi lần suy luận; nếu GPU từ 85°C, chờ tối đa 20 giây để nguội, rồi báo lỗi nếu vẫn nóng. Nhiệt vẫn có thể tăng trong một lượt xử lý. Không có phần mềm nào trong dự án này đo tiếng quạt hay bảo đảm máy luôn mát, đặc biệt nếu tải nền đã cao.
- Biểu thức JavaScript cơ bản với số/chuỗi, `+ - * / %` và dấu ngoặc được tính bằng bộ diễn giải giới hạn, không dùng GPU. Không chạy `eval`, hàm, truy cập thuộc tính hay mã tùy ý từ ảnh. Cú pháp không hỗ trợ sẽ chuyển cho model.
- Cache chỉ lưu các câu đã giải trong phiên đang mở, không dùng ngân hàng đáp án kiểm thử.
- **Slide tham khảo** là đoạn model chọn trong kết quả tìm kiếm, không phải bằng chứng đáp án chắc chắn đúng. “Slide” ở đây là số trang PDF tính từ 1; số in trên trang có thể khác.

## Tài liệu

Nguồn: `D:\Study\Vinh\Study\semester 3\Web Application Development`.

Kho được trích lại từ **11 PDF (317 trang vật lý)** và **1 cẩm nang HTML**. Trang có ít chữ hoặc sơ đồ chỉ là nguồn tìm kiếm văn bản hạn chế; chưa có OCR toàn bộ sơ đồ của PDF. Các file mã demo không được đưa vào kho tài liệu này.

- `data/course_knowledge.json`: nội dung tài liệu, trang gốc, mã HTML đã giải mã entity.
- `data/source_manifest.json`: đường dẫn và SHA-256 của từng nguồn.
- `src/build_knowledge.py`: trích lại kho nếu bạn sửa tài liệu.
- `tests/course_benchmark.json`: 64 câu kiểm thử, tách khỏi kho dùng khi suy luận.

## Hoạt động offline

Không cần tài khoản, API key cloud, VPN hoặc Internet khi sử dụng. OCR, model và tài liệu đều nằm trên ổ cứng. Một tiến trình llama.cpp do tool quản lý chỉ lắng nghe tại **127.0.0.1**, dùng khóa ngẫu nhiên trong phiên. Loopback vẫn hoạt động khi ngắt Wi-Fi. Không có lệnh tải model hoặc cập nhật tự động trong luồng giải câu hỏi.

Đóng cửa sổ sẽ kết thúc tiến trình AI thông qua Windows Job Object. Chỉ khi bạn tự chạy script tải/cài đặt mới cần Internet.

## Cấu hình và kiểm chứng

`settings.json` chứa model, đường dẫn tài liệu, thiết bị CUDA, giới hạn nhiệt, số luồng và số phương án mặc định. Mặc định dùng CUDA0 trên RTX 3060. Có thể chạy `run_exam_solver.bat --cpu` để bỏ GPU, nhưng tốc độ CPU phải được đo riêng.

Python đã kiểm chứng trên máy này:

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py doctor.py --hash
& $py -m unittest discover -s tests -p 'test_*.py' -v
& $py benchmark.py --output artifacts\benchmark.json
& $py tests\ocr_smoke.py
```

`tests/ocr_smoke.py` thay Clipboard bằng ảnh kiểm thử rồi đáp án để kiểm chứng ghi/đọc thật. Không chạy nếu cần giữ nguyên nội dung Clipboard hiện tại.

Để giải từ file mà không chạm Clipboard:

```powershell
& $py clipboard_solver.py --image tests\assets\html-lists.png --no-copy
& $py clipboard_solver.py --text question.txt --mode multi --json
```

## Môi trường Python

Launcher dùng `.venv\Scripts\python.exe` nếu có; nếu không dùng Python 3.12 đã cài ở đường dẫn trên. Các phiên bản đã kiểm chứng được ghi trong `requirements.txt`. Máy hiện tại đã có đủ phụ thuộc; không cần cài lại để dùng.

Nếu muốn cài thủ công thay cho `setup_windows.bat`, tạo môi trường và cài phụ thuộc lúc còn Internet, rồi chạy bộ tải tài nguyên:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_assets.py --backend cuda
.\.venv\Scripts\python.exe doctor.py --hash
```

Không tự chạy `download_model.py` cũ: script đó tải model 1.5B ban đầu. `setup_assets.py` dùng `artifacts/download-manifest.json` để lấy đúng bản 3B và checksum. Bản mã ban đầu được giữ trong `backups/`.

Bản Qwen2.5-3B được phát hành với giấy phép **qwen-research**; đây là mô hình có trọng số tải được, không được mô tả trong dự án này là giấy phép Apache hoặc mã nguồn mở OSI. [Model card chính thức](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF) · [llama.cpp b11159](https://github.com/ggml-org/llama.cpp/releases/tag/b11159).
