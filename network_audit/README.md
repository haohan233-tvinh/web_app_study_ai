# Network Restriction Audit & Stealth Diagnostic Suite

Bộ công cụ chuyên dụng kiểm tra, chẩn đoán và thu thập thông tin các chính sách chặn mạng, lọc cổng, tường lửa và Captive Portal trong môi trường mạng nội bộ trường học/phòng thi.

---

## 1. Cấu Trúc Thư Mục

| Tệp tin | Chức năng | Chế độ chạy |
| :--- | :--- | :--- |
| **`run_stealth.vbs`** | **Chạy kiểm tra ẩn danh 100% (Stealth Mode)**: Không mở console, không nháy màn hình, hòa lẫn vào lưu lượng Chrome để tránh bị tường lửa/IDS phát hiện. | Chạy ngầm |
| **`read_stealth_result.bat`** | Đọc và hiển thị ngay kết quả chẩn đoán từ lần chạy Stealth gần nhất. | Giao diện Console |
| **`run_network_audit.bat`** | **Chạy kiểm tra trực quan đầy đủ (Interactive Mode)**: Quét chi tiết từng cổng, hiển thị bảng màu thời gian thực trên màn hình. | Giao diện Console |
| **`network_audit.ps1`** | Script PowerShell chính của chế độ quét trực quan (Timeout 4s, Retry 2x, đo latency .NET Ping). | Core Engine |
| **`stealth_audit.ps1`** | Script PowerShell chính của chế độ ẩn danh (Passive First, Zero-Scan Signature, Jitter 1-2.5s). | Stealth Engine |
| **`launch_on_desktop.ps1`** | Script phụ trợ mở cửa sổ console trực tiếp trên Desktop tương tác (`WinSta0\default`). | Helper |
| **`.network_cache.txt` / `.dat`** | File nhật ký lưu trữ kết quả kiểm tra mạng của chế độ Stealth. | Cache Log |

---

## 2. Hướng Dẫn Sử Dụng Trong Phòng Thi

### Chế độ 1: Ẩn Danh Tuyệt Đối (Khuyến nghị trong phòng thi)
1. Nhấp đúp vào:  
   **`run_stealth.vbs`**
2. Màn hình sẽ hoàn toàn tĩnh lặng. Quá trình kiểm tra ngầm diễn ra trong 5 - 7 giây.
3. Khi muốn xem kết luận mạng, nhấp đúp vào:  
   **`read_stealth_result.bat`**

### Chế độ 2: Kiểm Tra Trực Quan Đầy Đủ
1. Nhấp đúp vào:  
   **`run_network_audit.bat`**
2. Màn hình console sẽ hiện bảng màu chi tiết của từng tầng mạng (Layer 3 Ping, Layer 7 DNS, Layer 4 Port Scan 80/443/22/53/8080/DERP).
