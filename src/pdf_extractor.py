"""
Trích xuất toàn bộ nội dung giáo trình Web Application Development từ PDF & HTML
Lưu trữ thành cơ sở tri thức có cấu trúc (Knowledge Base) phục vụ Fine-tuning và RAG.
"""

import os
import sys
import json
import re
import pypdf

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SOURCE_DIR = r"D:\Study\Vinh\Study\semester 3\Web Application Development"
OUTPUT_FILE = r"D:\pop\web_app_study_ai\data\course_knowledge.json"

def clean_text(text: str) -> str:
    """Loại bỏ ký tự rác, khoảng trắng thừa, chuẩn hóa ngắt dòng"""
    text = re.sub(r'\x00', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def extract_pdfs():
    knowledge_base = {}
    
    # 1. Quét các file PDF bài giảng và bài tập
    for fname in sorted(os.listdir(SOURCE_DIR)):
        if fname.endswith(".pdf"):
            full_path = os.path.join(SOURCE_DIR, fname)
            print(f"[*] Đang trích xuất: {fname} ...")
            try:
                reader = pypdf.PdfReader(full_path)
                pages_data = []
                for idx, page in enumerate(reader.pages):
                    raw_text = page.extract_text() or ""
                    cleaned = clean_text(raw_text)
                    if cleaned:
                        pages_data.append({
                            "page": idx + 1,
                            "content": cleaned
                        })
                
                # Tổng hợp text toàn bài
                full_content = "\n\n".join([f"--- Slide {p['page']} ---\n{p['content']}" for p in pages_data])
                knowledge_base[fname] = {
                    "source": fname,
                    "type": "lecture_slides" if "Exercise" not in fname else "exercise",
                    "total_pages": len(reader.pages),
                    "pages": pages_data,
                    "full_text": full_content
                }
                print(f"    -> Đã trích xuất {len(pages_data)}/{len(reader.pages)} trang có nội dung.")
            except Exception as e:
                print(f"[!] Lỗi khi đọc {fname}: {e}")

    # 2. Quét file cẩm nang ôn tập HTML
    study_guide_path = os.path.join(SOURCE_DIR, "Study Guide", "study_guide_lesson1_2.html")
    if os.path.exists(study_guide_path):
        print("[*] Đang trích xuất: Study Guide (study_guide_lesson1_2.html) ...")
        try:
            with open(study_guide_path, "r", encoding="utf-8", errors="ignore") as f:
                html_raw = f.read()
                # Loại bỏ thẻ style, script
                html_clean = re.sub(r'<style.*?</style>', '', html_raw, flags=re.DOTALL)
                html_clean = re.sub(r'<script.*?</script>', '', html_clean, flags=re.DOTALL)
                # Chuyển các thẻ HTML thành text
                text_clean = re.sub(r'<[^>]+>', ' ', html_clean)
                text_clean = clean_text(text_clean)
                knowledge_base["study_guide_lesson1_2.html"] = {
                    "source": "study_guide_lesson1_2.html",
                    "type": "study_guide",
                    "full_text": text_clean
                }
                print(f"    -> Đã trích xuất cẩm nang ôn thi ({len(text_clean)} ký tự).")
        except Exception as e:
            print(f"[!] Lỗi khi đọc study guide: {e}")

    # 3. Lưu vào tệp JSON
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(knowledge_base, f, ensure_ascii=False, indent=2)
    
    print(f"\n[+] HOÀN THÀNH: Đã lưu toàn bộ tri thức vào {OUTPUT_FILE}")
    print(f"    Tổng số tài liệu đã xử lý: {len(knowledge_base)}")

if __name__ == "__main__":
    extract_pdfs()
