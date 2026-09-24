import os
import sys
import time
from PIL import Image

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from clipboard_solver import ExamSolver

TEST_IMAGES = [
    r"C:\Users\vinh1\.gemini\antigravity\brain\b41a1844-ac23-455d-a2a6-aa0ae301ba1e\.user_uploaded\media_1790251324357.png",
    r"C:\Users\vinh1\.gemini\antigravity\brain\b41a1844-ac23-455d-a2a6-aa0ae301ba1e\.user_uploaded\media_1790251205632.png"
]

def run_tests():
    print("=== KIỂM THỬ TỰ ĐỘNG BỘ GIẢI V3.0 VỚI ẢNH MẪU ===")
    solver = ExamSolver(use_gpu=True)

    for idx, img_path in enumerate(TEST_IMAGES, 1):
        if not os.path.exists(img_path):
            print(f"[-] Không tìm thấy ảnh test {idx}: {img_path}")
            continue

        print(f"\n--- [TEST {idx}] Đang xử lý: {os.path.basename(img_path)} ---")
        img = Image.open(img_path)
        
        t0 = time.time()
        lines = solver.ocr_image(img)
        question, options, is_multi = solver.parse_exam_text(lines)
        result = solver.solve(question, options, is_multi_select=is_multi)
        elapsed = time.time() - t0

        print(f"📝 Câu hỏi: {question}")
        print("📌 Lựa chọn:")
        for k, v in options.items():
            print(f"   [{k}] {v}")

        print(f"🎯 ĐÁP ÁN:  [  {result['best_choice']}  ]")
        print(f"⚡ Thời gian xử lý: {elapsed:.2f}s | Phương pháp: {result.get('method')}")
        print(f"📖 Slide đối chiếu: {result.get('matched_source')}")

if __name__ == "__main__":
    run_tests()
