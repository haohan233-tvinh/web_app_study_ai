"""Summarize frozen baseline and V2 measurements with explicit limits."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def main():
    a = read(BASE / 'artifacts/benchmark-final.json')
    b = read(ROOT / 'artifacts/benchmark-v2.json')
    ao = read(BASE / 'artifacts/ocr-smoke.json')
    bo = read(ROOT / 'artifacts/ocr-benchmark.json')
    bp = read(ROOT / 'artifacts/prefetch-benchmark.json')
    idle = read(ROOT / 'artifacts/idle-benchmark.json')
    packaged = read(ROOT / 'artifacts/package-ocr-smoke.json')
    lines = ['# Web MCQ Fast V2 — A/B', '',
             'Bộ 64 câu và 16 ảnh là bộ tự tạo để kiểm tra hồi quy; chưa có đề thi độc lập kèm đáp án chuẩn.',
             'V1 và V2 được đo ở các thời điểm khác nhau. Chênh lệch nhiệt, RAM và ứng dụng nền có thể làm lệch so sánh tốc độ.',
             '', '| Phép đo | V1 | V2 |', '|---|---:|---:|']
    def val(record, key, unit=''):
        if not record or key not in record:
            return 'Chưa đo'
        value = record[key]
        return f"{value:.3f}{unit}" if isinstance(value, float) else f"{value}{unit}"
    lines += [f"| Đúng trên 64 câu | {val(a,'correct')}/64 | {val(b,'correct')}/64 |",
              f"| Trung vị 64 câu văn bản | {val(a,'median_seconds',' s')} | {val(b,'median_seconds',' s')} |",
              f"| P95 64 câu văn bản | {val(a,'p95_seconds',' s')} | {val(b,'p95_seconds',' s')} |",
              f"| Đúng trên 16 ảnh | {val(ao,'correct')}/16 | {val(bo,'correct')}/16 |",
              f"| Trung vị ảnh đến kết quả | {val(ao,'median_total_seconds',' s')} | {val(bo,'median_seconds',' s')} |",
              '', '## OCR trước khi bấm phím giải', '']
    if bp:
        lines += [f"- {bp['correct']}/{bp['total']} ảnh đúng; {bp['reread_count']} ảnh phải đọc lại.",
                  f"- Ảnh xuất hiện → kết quả: trung vị {bp['median_image_to_answer_seconds']} s; P95 {bp['p95_image_to_answer_seconds']} s.",
                  f"- Phím giải → kết quả: trung vị {bp['median_enter_to_answer_seconds']} s; P95 {bp['p95_enter_to_answer_seconds']} s.",
                  f"- Nạp model: {bp['model_load_seconds']} s. Ảnh đã OCR xong trước khi bấm phím trong phép đo này."]
    else:
        lines += ['Chưa có phép đo Enter sau OCR.']
    lines += ['', '## Nghiệm thu', '']
    if b and bo:
        lines += [f"- Mốc hồi quy 60/64 và 16/16: {'ĐẠT' if b['correct'] >= 60 and bo['correct'] == 16 else 'CHƯA ĐẠT'}."]
    else:
        lines += ['- Chưa chạy đủ cả hai phép đo V2.']
    if bp and a:
        gain = (1-bp['median_enter_to_answer_seconds']/a['median_seconds'])*100
        lines += [f'- Thời gian sau phím giải giảm {gain:.1f}% so với trung vị V1 lưu từ lần đo trước; đây là so sánh lịch sử, chưa phải A/B cùng điều kiện.']
    if b:
        max_vram = max((row['gpu'].get('memory_mib', 0) for row in b['rows']), default=0)
        max_temp = max((row['gpu'].get('temperature_c', 0) for row in b['rows']), default=0)
        baseline_vram = b['gpu_baseline'].get('memory_mib', 0)
        lines += [f'- V2 dùng tối đa khoảng {max_vram-baseline_vram:.0f} MiB VRAM tăng thêm so với trước khi nạp; GPU lên đến {max_temp:.0f}°C trong 64 câu. Số đo gồm tải nền của máy.']
    if idle:
        cases = ', '.join(f"{row['case']} {row['seconds']:.2f} s" for row in idle['rows'])
        lines += [f'- Thử nạp đầu và nghỉ 20/65 giây: {cases}.']
    if packaged:
        lines += [f"- OCR bên trong bản .exe: {'ĐẠT' if packaged.get('passed') else 'CHƯA ĐẠT'}."]
    lines += ['- Mức nhiệt và quạt phụ thuộc tải máy. Từ 85°C, V2 chờ rồi từ chối nếu không nguội; không cam kết máy luôn mát.',
              '- Đã mở bản Web MCQ Fast.exe, xác nhận model con nạp được, shortcut Startup trỏ đúng .exe và đóng đột ngột không để lại model con.',
              '- Logic gán phím và trạng thái overlay đã qua kiểm thử Qt; hook phím toàn hệ thống và vị trí overlay chưa được thử bằng thao tác trực tiếp trên desktop thật.',
              '- Báo cáo độ chính xác không thay thế thử nghiệm trên đề thi thật.', '']
    target = ROOT / 'artifacts/ab-report.md'
    target.write_text('\n'.join(lines), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
