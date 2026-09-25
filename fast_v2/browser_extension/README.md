# Đọc chữ HTML trong vùng đã vẽ (Chrome / Edge)

1. Mở `..\run_fast_solver_visible.bat` **trước**. Ứng dụng sẽ tạo tệp ghép nối cục bộ `bridge-config.json` trong thư mục extension này.
2. Trong Chrome mở `chrome://extensions` (Edge: `edge://extensions`), bật **Developer mode**, chọn **Load unpacked / Tải tiện ích đã giải nén**, rồi chọn chính thư mục `fast_v2\browser_extension`.
3. Mở trang bài tập. Nhấp biểu tượng extension **Web MCQ Fast — đọc chữ trong vùng**, chọn **Cho phép đọc trang này** một lần. Nếu đã nạp extension trước khi mở ứng dụng, bấm **Reload** extension rồi làm lại bước này.
4. Trong ứng dụng, vẽ vùng như trước: **Tự đọc cả vùng** dùng một hình chữ nhật bao đề và đáp án; **Vẽ từng ô** dùng các ô Đề, A, B, C, D theo thứ tự. Extension gửi chữ HTML trong từng vùng về ứng dụng qua `127.0.0.1`; bạn bấm phím giải như cũ. Cửa sổ kiểm thử ghi **DOM xong** khi đọc trực tiếp hoặc **OCR** khi dùng ảnh dự phòng.

Trong Cài đặt có ô **Ưu tiên lấy chữ trực tiếp từ trang web** để bật/tắt tính năng. Cả hai chế độ vẽ vùng đều ưu tiên HTML khi extension sẵn sàng; các vùng thủ công vẫn được gán Đề/A–H theo thứ tự vẽ. Extension chỉ được cấp quyền cho trang bạn chọn, không gửi nội dung ra Internet và không đọc cookie. Tệp `bridge-config.json` chứa khóa kết nối chỉ lưu trên máy, không được đẩy lên Git.

Chỉ chữ HTML đang hiển thị trong tab trình duyệt hoạt động mới được lấy. Canvas, PDF trong trình duyệt, iframe, chữ vẽ thành ảnh, trang `chrome://` và vùng nằm ngoài khung nội dung trình duyệt sẽ quay về OCR. Khi có nhiều câu trong một vùng hoặc không tách đủ đáp án, ứng dụng cũng dùng OCR. Với nhiều màn hình hoặc tỉ lệ DPI khác nhau, kiểm tra văn bản trong cửa sổ visible trước khi tin kết quả của vùng mới.
