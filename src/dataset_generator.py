"""
Bộ sinh tập dữ liệu huấn luyện (Training & Evaluation Dataset Generator)
Dựa trên tri thức môn Web Application Development đã trích xuất.
Định dạng chuẩn hóa cho Fine-tuning và Benchmark Laya.
"""

import os
import sys
import json
import random

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KNOWLEDGE_FILE = r"D:\pop\web_app_study_ai\data\course_knowledge.json"
TRAIN_FILE = r"D:\pop\web_app_study_ai\data\train_dataset.json"
EVAL_FILE = r"D:\pop\web_app_study_ai\data\eval_dataset.json"

# Ngân hàng câu hỏi trắc nghiệm chuẩn hóa trực tiếp từ nội dung giáo trình bài giảng
EXAM_ITEMS = [
    # --- Module 1: Introduction, Internet, Web, HTTP, DNS ---
    {
        "module": "1-Introduction",
        "question": "Ai là người phát minh ra World Wide Web (WWW) vào năm 1989 tại CERN?",
        "context": "Tim Berners-Lee phát minh ra World Wide Web (WWW) tại CERN năm 1989, bao gồm HTTP, HTML và URL.",
        "choices": {
            "A": "Vint Cerf",
            "B": "Tim Berners-Lee",
            "C": "Marc Andreessen",
            "D": "Brendan Eich"
        },
        "answer": "B",
        "explanation": "Tim Berners-Lee là cha đẻ của WWW, HTTP và HTML."
    },
    {
        "module": "1-Introduction",
        "question": "Giao thức nào chịu trách nhiệm phân giải tên miền (ví dụ: google.com) thành địa chỉ IP?",
        "context": "DNS (Domain Name System) là hệ thống phân giải tên miền thành địa chỉ IP số học để các máy tính có thể định tuyến trên Internet.",
        "choices": {
            "A": "DHCP",
            "B": "FTP",
            "C": "DNS",
            "D": "SMTP"
        },
        "answer": "C",
        "explanation": "DNS (Domain Name System) chuyển đổi tên miền dạng chữ thành địa chỉ IP."
    },
    {
        "module": "1-Introduction",
        "question": "Mã trạng thái HTTP nào biểu thị tài nguyên yêu cầu không được tìm thấy trên máy chủ (Not Found)?",
        "context": "HTTP Status codes: 200 OK, 301 Moved Permanently, 400 Bad Request, 403 Forbidden, 404 Not Found, 500 Internal Server Error.",
        "choices": {
            "A": "200",
            "B": "403",
            "C": "404",
            "D": "500"
        },
        "answer": "C",
        "explanation": "404 Not Found biểu thị máy chủ không tìm thấy tài nguyên theo URL được yêu cầu."
    },
    {
        "module": "1-Introduction",
        "question": "Trong kiến trúc Client-Server của Web, trình duyệt đóng vai trò gì?",
        "context": "Trình duyệt (Browser) đóng vai trò là Client, gửi yêu cầu (HTTP Request) đến Web Server và hiển thị phản hồi (HTTP Response).",
        "choices": {
            "A": "Web Server",
            "B": "Client (User Agent)",
            "C": "Database Server",
            "D": "Router"
        },
        "answer": "B",
        "explanation": "Trình duyệt là Client (User Agent) khởi tạo các yêu cầu HTTP tới máy chủ."
    },

    # --- Module 2: HTML ---
    {
        "module": "2-HTML",
        "question": "Thẻ HTML5 ngữ nghĩa (semantic tag) nào dùng để chứa các liên kết điều hướng chính của trang web?",
        "context": "Semantic HTML5 tags: <header>, <nav> (navigation links), <main>, <article>, <section>, <aside>, <footer>.",
        "choices": {
            "A": "<menu>",
            "B": "<nav>",
            "C": "<navigation>",
            "D": "<link>"
        },
        "answer": "B",
        "explanation": "Thẻ <nav> được dùng trong HTML5 để chứa thanh điều hướng trang web."
    },
    {
        "module": "2-HTML",
        "question": "Thuộc tính nào của thẻ <img> dùng để cung cấp văn bản thay thế khi hình ảnh không thể hiển thị?",
        "context": "Thẻ <img> sử dụng thuộc tính 'src' để chỉ định đường dẫn ảnh và 'alt' (alternative text) cho khả năng tiếp cận và SEO.",
        "choices": {
            "A": "title",
            "B": "description",
            "C": "alt",
            "D": "caption"
        },
        "answer": "C",
        "explanation": "Thuộc tính 'alt' cung cấp văn bản thay thế (alternative text)."
    },
    {
        "module": "2-HTML",
        "question": "Trong thẻ <form>, phương thức HTTP nào thường dùng để gửi dữ liệu nhạy cảm hoặc tạo mới tài nguyên mà không hiển thị trên thanh địa chỉ URL?",
        "context": "Thẻ form hỗ trợ 2 method chính: GET (dữ liệu gắn vào URL query string) và POST (dữ liệu gửi trong body, bảo mật hơn cho form đăng nhập/gửi dữ liệu lớn).",
        "choices": {
            "A": "GET",
            "B": "POST",
            "C": "PUT",
            "D": "HEAD"
        },
        "answer": "B",
        "explanation": "POST gửi dữ liệu trong phần body của request, không hiển thị trên URL."
    },

    # --- Module 3: CSS ---
    {
        "module": "3-CSS",
        "question": "Trong mô hình hộp CSS (Box Model), thứ tự từ trong ra ngoài lần lượt là gì?",
        "context": "CSS Box Model bao gồm từ trong ra ngoài: Content -> Padding -> Border -> Margin.",
        "choices": {
            "A": "Content, Margin, Border, Padding",
            "B": "Content, Padding, Border, Margin",
            "C": "Padding, Content, Border, Margin",
            "D": "Margin, Border, Padding, Content"
        },
        "answer": "B",
        "explanation": "Thứ tự từ lõi ra ngoài: Content (nội dung) -> Padding (khoảng đệm) -> Border (viền) -> Margin (lề ngoài)."
    },
    {
        "module": "3-CSS",
        "question": "Thuộc tính Flexbox nào dùng để căn chỉnh các phần tử con theo trục chính (main axis)?",
        "context": "Flexbox layout: 'justify-content' căn chỉnh dọc theo main-axis; 'align-items' căn chỉnh dọc theo cross-axis.",
        "choices": {
            "A": "align-items",
            "B": "justify-content",
            "C": "align-content",
            "D": "flex-direction"
        },
        "answer": "B",
        "explanation": "justify-content căn chỉnh các flex items dọc theo trục chính (main axis)."
    },
    {
        "module": "3-CSS",
        "question": "Selector CSS nào sau đây có độ ưu tiên (specificity) cao nhất?",
        "context": "Specificity hierarchy: Inline styles (1000) > ID (#id: 100) > Class (.class, pseudo-class: 10) > Element (tag: 1).",
        "choices": {
            "A": "div.container",
            "B": "#main-header",
            "C": "header h1",
            "D": ".nav-link.active"
        },
        "answer": "B",
        "explanation": "ID selector (#main-header) có độ ưu tiên (specificity 100) cao hơn class (10) và tag (1)."
    },

    # --- Module 4: JavaScript ---
    {
        "module": "4-JavaScript",
        "question": "Phương thức nào của DOM API dùng để lấy phần tử đầu tiên khớp với một CSS selector trong trang web?",
        "context": "DOM Selection methods: document.getElementById(), document.querySelector() (trả về 1 phần tử đầu tiên khớp CSS selector), document.querySelectorAll() (trả về NodeList).",
        "choices": {
            "A": "document.findElement()",
            "B": "document.querySelector()",
            "C": "document.getElementBySelector()",
            "D": "document.selectFirst()"
        },
        "answer": "B",
        "explanation": "document.querySelector() trả về phần tử đầu tiên khớp với chuỗi selector CSS truyền vào."
    },
    {
        "module": "4-JavaScript",
        "question": "Trong JavaScript, từ khóa nào dùng để khai báo một biến có phạm vi khối (block-scoped) và không thể gán lại giá trị mới?",
        "context": "JavaScript variable declarations: var (function scope, hoisted), let (block scope, reassignable), const (block scope, immutable binding/constant).",
        "choices": {
            "A": "var",
            "B": "let",
            "C": "const",
            "D": "static"
        },
        "answer": "C",
        "explanation": "const khai báo hằng số có phạm vi block-scoped và không cho phép gán lại biến."
    },
    {
        "module": "4-JavaScript",
        "question": "API Fetch trong JavaScript trả về kiểu đối tượng nào để xử lý tác vụ bất đồng bộ?",
        "context": "fetch(url) trả về một Promise giải quyết thành Response object đại diện cho phản hồi từ server.",
        "choices": {
            "A": "Callback",
            "B": "Promise",
            "C": "Observable",
            "D": "Generator"
        },
        "answer": "B",
        "explanation": "fetch() trả về một Promise đại diện cho kết quả bất đồng bộ."
    },

    # --- Module 6: NodeJS ---
    {
        "module": "6-NodeJS",
        "question": "Node.js xử lý các tác vụ I/O theo kiến trúc nào sau đây?",
        "context": "Node.js là một JavaScript runtime xây dựng trên V8 engine, sử dụng mô hình non-blocking I/O, event-driven và Single-threaded Event Loop.",
        "choices": {
            "A": "Multi-threaded blocking I/O",
            "B": "Single-threaded event-driven non-blocking I/O",
            "C": "Process-per-request I/O",
            "D": "Synchronous FIFO I/O"
        },
        "answer": "B",
        "explanation": "Node.js dùng kiến trúc đơn luồng kết hợp Event Loop bất đồng bộ không chặn (non-blocking I/O)."
    },
    {
        "module": "6-NodeJS",
        "question": "Framework phổ biến nhất trong hệ sinh thái Node.js dùng để xây dựng Web Server và RESTful API là gì?",
        "context": "Express.js là framework tối giản và phổ biến nhất cho Node.js, cung cấp hệ thống routing và middleware mạnh mẽ.",
        "choices": {
            "A": "Django",
            "B": "Express.js",
            "C": "Flask",
            "D": "Spring Boot"
        },
        "answer": "B",
        "explanation": "Express.js là web application framework tiêu chuẩn cho Node.js."
    },

    # --- Module 7: Front-end dev with NodeJS ---
    {
        "module": "7-Front-end dev with NodeJS",
        "question": "Tệp tin cấu hình nào quản lý danh sách thư viện phụ thuộc (dependencies) và metadata của một dự án Node.js?",
        "context": "package.json chứa thông tin dự án, scripts chạy lệnh, và các dependencies/devDependencies của npm.",
        "choices": {
            "A": "node_modules.json",
            "B": "config.js",
            "C": "package.json",
            "D": "manifest.json"
        },
        "answer": "C",
        "explanation": "package.json là tệp trung tâm quản lý dependencies và cấu hình trong hệ sinh thái Node/NPM."
    },

    # --- Module 8: Python Flask ---
    {
        "module": "8-Python Flask",
        "question": "Trong Python Flask, cú pháp decorator nào dùng để định tuyến (routing) hàm xử lý một URL cụ thể?",
        "context": "Flask routing sử dụng decorator @app.route('/path') để gắn hàm xử lý với một endpoint URL.",
        "choices": {
            "A": "@app.route('/path')",
            "B": "@app.endpoint('/path')",
            "C": "@app.url('/path')",
            "D": "@app.get('/path')"
        },
        "answer": "A",
        "explanation": "@app.route() là decorator chuẩn của Flask để định tuyến request."
    },
    {
        "module": "8-Python Flask",
        "question": "Template engine mặc định được tích hợp trong Flask để kết xuất HTML động là gì?",
        "context": "Flask sử dụng Jinja2 làm template engine mặc định, hỗ trợ render biến {{ var }} và logic {% if/for %}.",
        "choices": {
            "A": "Blade",
            "B": "Pug",
            "C": "Jinja2",
            "D": "Handlebars"
        },
        "answer": "C",
        "explanation": "Jinja2 là template engine tiêu chuẩn của framework Flask."
    },

    # --- Module 9: Database ---
    {
        "module": "9-Database",
        "question": "Hệ quản trị cơ sở dữ liệu nào sau đây thuộc loại cơ sở dữ liệu quan hệ (RDBMS) sử dụng SQL?",
        "context": "Relational Databases (RDBMS): PostgreSQL, MySQL, SQLite, Oracle (sử dụng bảng và khóa ngoại). NoSQL: MongoDB, Redis.",
        "choices": {
            "A": "MongoDB",
            "B": "PostgreSQL",
            "C": "Redis",
            "D": "Cassandra"
        },
        "answer": "B",
        "explanation": "PostgreSQL là hệ quản trị cơ sở dữ liệu quan hệ (RDBMS) mã nguồn mở mạnh mẽ."
    },
    {
        "module": "9-Database",
        "question": "Kỹ thuật ORM (Object-Relational Mapping) trong phát triển ứng dụng web nhằm mục đích gì?",
        "context": "ORM (như SQLAlchemy trong Python, Sequelize trong Node.js) ánh xạ các bảng cơ sở dữ liệu thành các lớp/đối tượng trong mã nguồn để thao tác dữ liệu mà không cần viết raw SQL.",
        "choices": {
            "A": "Nén dữ liệu để giảm dung lượng đĩa",
            "B": "Ánh xạ bảng dữ liệu quan hệ sang đối tượng trong code hướng đối tượng",
            "C": "Tăng tốc độ kết nối mạng giữa client và server",
            "D": "Tự động sao lưu database lên cloud"
        },
        "answer": "B",
        "explanation": "ORM cho phép lập trình viên tương tác với cơ sở dữ liệu thông qua các Object thay vì viết câu lệnh SQL thuần."
    }
]

def generate_datasets():
    print(f"[*] Tổng số câu hỏi cơ sở: {len(EXAM_ITEMS)}")
    
    # Chia 80% train, 20% test
    random.seed(42)
    shuffled = EXAM_ITEMS.copy()
    random.shuffle(shuffled)
    split_idx = int(len(shuffled) * 0.8)
    
    train_data = shuffled[:split_idx]
    eval_data = shuffled[split_idx:]
    
    with open(TRAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(train_data, f, ensure_ascii=False, indent=2)
    with open(EVAL_FILE, "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)
        
    print(f"[+] Đã tạo tập Train: {TRAIN_FILE} ({len(train_data)} câu hỏi)")
    print(f"[+] Đã tạo tập Eval:  {EVAL_FILE} ({len(eval_data)} câu hỏi)")

if __name__ == "__main__":
    generate_datasets()
