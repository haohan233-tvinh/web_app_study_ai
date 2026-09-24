# Kết quả kiểm chứng Web MCQ offline

**Bản cuối: 60/64 = 93.75% trên bộ 64 câu tự soạn từ tài liệu.**

Đây là bộ hồi quy đã dùng để chọn model/cấu hình, không phải tập đề thi độc lập. Chưa xác nhận 90% trên đề thật. Bộ câu hỏi giữ nguyên sau khi tạo; các đáp án không nằm trong kho tìm kiếm. Câu bị từ chối, lỗi hoặc sai một lựa chọn trong multi-select đều tính sai.

| Kiểm tra | Kết quả |
|---|---|
| Baseline Qwen2.5-Coder 1.5B, trước tối ưu | 54/64 (84.38%) |
| Qwen2.5 3B + BM25 + bộ tính JS cơ bản | 60/64 (93.75%) |
| Ảnh mô phỏng, đủ tám chương | 16/16 |
| Ảnh gốc HTML list + ghi/đọc Clipboard thật | A, B |
| Khởi động model | 3.68 giây |
| Suy luận GPU trung vị, không tính OCR/nghỉ | 1.14 giây |
| Benchmark text liên tiếp, trung vị / P95, có thời gian nghỉ | 5.13 / 20.68 giây |
| Luồng ảnh OCR + giải, trung vị | 4.94 giây |
| VRAM tăng sau nạp model (ước tính từ toàn GPU) | 2047 MiB |
| VRAM toàn GPU lớn nhất trong mẫu đo | 3532 MiB (bao gồm ứng dụng khác) |
| CPU tiến trình model khi chờ trong 3 giây | 0.0% |
| GPU trước test / cao nhất ở mẫu đo sau từng câu | 82 / 91°C |

## Giới hạn nhiệt và tốc độ

Máy có tải nền. VRAM và nhiệt từ nvidia-smi là của toàn GPU, không chứng minh tác động riêng của tool. Không đo tiếng quạt; **chưa đạt một bảo đảm máy không nóng/không hú quạt**. Số mẫu đo sau từng câu có thể bỏ lỡ đỉnh nhiệt/công suất ngắn trong lúc tính. Tool dùng 2 luồng CPU/OCR, sinh tối đa 48 token, nghỉ tối thiểu 4 giây giữa hai lần suy luận, tự ngủ sau 15 giây rảnh, và chờ tối đa 20 giây nếu nhiệt GPU từ 85°C. Nếu vẫn nóng, tool báo lỗi và không copy đáp án. Điều này có thể làm chậm việc giải.

## Phạm vi dữ liệu và phương pháp

- 11 PDF / 317 trang vật lý + 1 HTML, có đường dẫn và checksum trong `data/source_manifest.json`.
- Bộ benchmark bao gồm Internet/HTTP, HTML, CSS, JavaScript, Node.js, front-end, Flask, database.
- 16 ảnh mô phỏng được lấy cách đều 4 câu từ bộ 64 câu, không phải tập độc lập; gồm cỡ chữ 19/23.
- Ảnh gốc câu HTML list được kiểm riêng; thiếu phương án C đã được xác nhận là báo lỗi, không tự tạo C.
- 27 unit/contract tests đã chạy, gồm parse, mất nhãn, multi-select, CSS selector, JS, lỗi model, thiếu RAM và ngưỡng nhiệt.
- Khoảng Wilson 95% minh họa cho tỷ lệ trong mẫu: 85.0%–97.5%; không khắc phục thiên lệch do tự soạn/chọn model.
- Bộ tính JavaScript giới hạn chỉ nhận số/chuỗi và phép toán cơ bản; không thực thi mã từ ảnh.
- Chưa kiểm toàn bộ sơ đồ/ảnh nằm trong PDF, chưa kiểm trên giao diện Moodle thật.

## Offline và tiến trình

- Trong benchmark, kết nối Python ra ngoài loopback bị chặn bằng kiểm tra socket.
- Tiến trình model chỉ có kết nối/listener tại 127.0.0.1 trong snapshot kiểm tra; yêu cầu không có khóa bị từ chối.
- OCR đọc các file ONNX đã có trong Python; model chỉ đọc GGUF cục bộ. Không có tải tự động khi giải.
- Đã kiểm đóng bình thường và kết thúc đột ngột tiến trình cha: model đều được dọn sạch.
- Chưa tắt Wi-Fi toàn hệ thống trong quá trình kiểm chứng.
- Lượt kiểm bổ sung tự ngủ/nạp lại bị timeout ngay khi khởi động model (quá 90 giây); Windows lúc kiểm tra chỉ còn khoảng 820 MiB RAM trống. Vì vậy tự ngủ đã cấu hình nhưng vòng ngủ/thức chưa xác nhận. Sau đó đã thêm kiểm tra RAM tối thiểu 1,5 GiB trước khi khởi động để báo lỗi sớm. Không thay đổi các đáp án hoặc kết quả benchmark đã ghi.

## Các câu sai hoặc từ chối trong lượt cuối

- course-26: cần `A, B, D`, nhận `A, B` — Select all examples of CSS pseudo-classes shown for hyperlinks.
- course-62: cần `D`, nhận `Không có đáp án: GPU đang 85°C (ngưỡng 85°C). Đợi máy nguội rồi thử lại.` — What does SQLAlchemy ORM map Python objects to?
- course-63: cần `C, D`, nhận `Không có đáp án: GPU đang 85°C (ngưỡng 85°C). Đợi máy nguội rồi thử lại.` — Select all benefits of ORM stated in the lecture.
- course-64: cần `A`, nhận `Không có đáp án: GPU đang 85°C (ngưỡng 85°C). Đợi máy nguội rồi thử lại.` — Which extension is named for creating forms in Flask?

## Theo chương

| Chương | Đúng/tổng |
|---|---|
| 1-Introduction | 8/8 |
| 2-HTML | 10/10 |
| 3-CSS | 7/8 |
| 4-JavaScript | 10/10 |
| 6-NodeJS | 8/8 |
| 7-Front-end dev with NodeJS | 6/6 |
| 8-Python Flask | 7/7 |
| 9-Database | 4/7 |

## Nguồn và tái kiểm

[Model card Qwen chính thức](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF) — giấy phép qwen-research, trọng số tải được; không gọi là Apache/OSI open source. [llama.cpp b11159](https://github.com/ggml-org/llama.cpp/releases/tag/b11159).

Chi tiết từng câu: `benchmark-final.json`. Kết quả ảnh: `ocr-smoke.json`. Kiểm tra tiến trình: `runtime-smoke.json`. Hướng dẫn chạy lại và dùng tool: `../README.md`.

SHA-256 bộ câu hỏi: `c4bd826e18924b5f4fa7088592a8d2072a9dcc77066107c165093c43b007cda7`.
