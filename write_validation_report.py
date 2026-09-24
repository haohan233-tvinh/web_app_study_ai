"""Build a transparent report from completed measurements, never guessed metrics."""
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT/'artifacts'/name).read_text(encoding='utf-8'))


def main():
    final = load('benchmark-final.json')
    baseline = load('benchmark-1.5b.json')
    ocr = load('ocr-smoke.json')
    runtime = load('runtime-smoke.json')
    rows = final['rows']
    errors = [r for r in rows if not r['correct']]
    infer = [r['result']['inference_seconds'] for r in rows if r['result'].get('inference_seconds',0) > 0]
    gpu = [r['gpu'] for r in rows if r.get('gpu')]
    peak_temp = max(x['temperature_c'] for x in gpu)
    peak_memory = max(x['memory_mib'] for x in gpu)
    added_memory = final['gpu_after_load']['memory_mib'] - final['gpu_baseline']['memory_mib']
    low, high = final['wilson_95_interval']
    lines = [
        '# Kết quả kiểm chứng Web MCQ offline',
        '',
        f"**Bản cuối: {final['correct']}/{final['total']} = {final['accuracy']:.2%} trên bộ 64 câu tự soạn từ tài liệu.**",
        '',
        'Đây là bộ hồi quy đã dùng để chọn model/cấu hình, không phải tập đề thi độc lập. '
        'Chưa xác nhận 90% trên đề thật. Bộ câu hỏi giữ nguyên sau khi tạo; các đáp án không nằm trong kho tìm kiếm. '
        'Câu bị từ chối, lỗi hoặc sai một lựa chọn trong multi-select đều tính sai.',
        '',
        '| Kiểm tra | Kết quả |',
        '|---|---|',
        f"| Baseline Qwen2.5-Coder 1.5B, trước tối ưu | {baseline['correct']}/{baseline['total']} ({baseline['accuracy']:.2%}) |",
        f"| Qwen2.5 3B + BM25 + bộ tính JS cơ bản | {final['correct']}/{final['total']} ({final['accuracy']:.2%}) |",
        f"| Ảnh mô phỏng, đủ tám chương | {ocr['correct']}/{ocr['total']} |",
        f"| Ảnh gốc HTML list + ghi/đọc Clipboard thật | {ocr['clipboard_roundtrip']['read_back']} |",
        f"| Khởi động model | {final['load_seconds']:.2f} giây |",
        f"| Suy luận GPU trung vị, không tính OCR/nghỉ | {statistics.median(infer):.2f} giây |",
        f"| Benchmark text liên tiếp, trung vị / P95, có thời gian nghỉ | {final['median_seconds']:.2f} / {final['p95_seconds']:.2f} giây |",
        f"| Luồng ảnh OCR + giải, trung vị | {ocr['median_total_seconds']:.2f} giây |",
        f"| VRAM tăng sau nạp model (ước tính từ toàn GPU) | {added_memory:.0f} MiB |",
        f"| VRAM toàn GPU lớn nhất trong mẫu đo | {peak_memory:.0f} MiB (bao gồm ứng dụng khác) |",
        f"| CPU tiến trình model khi chờ trong 3 giây | {runtime['idle_cpu_percent_over_3_seconds']:.1f}% |",
        f"| GPU trước test / cao nhất ở mẫu đo sau từng câu | {final['gpu_baseline']['temperature_c']:.0f} / {peak_temp:.0f}°C |",
        '',
        '## Giới hạn nhiệt và tốc độ',
        '',
        'Máy có tải nền. VRAM và nhiệt từ nvidia-smi là của toàn GPU, không chứng minh tác động riêng của tool. '
        'Không đo tiếng quạt; **chưa đạt một bảo đảm máy không nóng/không hú quạt**. '
        'Số mẫu đo sau từng câu có thể bỏ lỡ đỉnh nhiệt/công suất ngắn trong lúc tính. '
        'Tool dùng 2 luồng CPU/OCR, sinh tối đa 48 token, nghỉ tối thiểu 4 giây giữa hai lần suy luận, '
        'tự ngủ sau 15 giây rảnh, và chờ tối đa 20 giây nếu nhiệt GPU từ 85°C. '
        'Nếu vẫn nóng, tool báo lỗi và không copy đáp án. Điều này có thể làm chậm việc giải.',
        '',
        '## Phạm vi dữ liệu và phương pháp',
        '',
        '- 11 PDF / 317 trang vật lý + 1 HTML, có đường dẫn và checksum trong `data/source_manifest.json`.',
        '- Bộ benchmark bao gồm Internet/HTTP, HTML, CSS, JavaScript, Node.js, front-end, Flask, database.',
        '- 16 ảnh mô phỏng được lấy cách đều 4 câu từ bộ 64 câu, không phải tập độc lập; gồm cỡ chữ 19/23.',
        '- Ảnh gốc câu HTML list được kiểm riêng; thiếu phương án C đã được xác nhận là báo lỗi, không tự tạo C.',
        '- 27 unit/contract tests đã chạy, gồm parse, mất nhãn, multi-select, CSS selector, JS, lỗi model, thiếu RAM và ngưỡng nhiệt.',
        f'- Khoảng Wilson 95% minh họa cho tỷ lệ trong mẫu: {low:.1%}–{high:.1%}; không khắc phục thiên lệch do tự soạn/chọn model.',
        '- Bộ tính JavaScript giới hạn chỉ nhận số/chuỗi và phép toán cơ bản; không thực thi mã từ ảnh.',
        '- Chưa kiểm toàn bộ sơ đồ/ảnh nằm trong PDF, chưa kiểm trên giao diện Moodle thật.',
        '',
        '## Offline và tiến trình',
        '',
        '- Trong benchmark, kết nối Python ra ngoài loopback bị chặn bằng kiểm tra socket.',
        '- Tiến trình model chỉ có kết nối/listener tại 127.0.0.1 trong snapshot kiểm tra; yêu cầu không có khóa bị từ chối.',
        '- OCR đọc các file ONNX đã có trong Python; model chỉ đọc GGUF cục bộ. Không có tải tự động khi giải.',
        '- Đã kiểm đóng bình thường và kết thúc đột ngột tiến trình cha: model đều được dọn sạch.',
        '- Chưa tắt Wi-Fi toàn hệ thống trong quá trình kiểm chứng.',
        '- Lượt kiểm bổ sung tự ngủ/nạp lại bị timeout ngay khi khởi động model (quá 90 giây); '
        'Windows lúc kiểm tra chỉ còn khoảng 820 MiB RAM trống. Vì vậy tự ngủ đã cấu hình nhưng vòng ngủ/thức chưa xác nhận. '
        'Sau đó đã thêm kiểm tra RAM tối thiểu 1,5 GiB trước khi khởi động để báo lỗi sớm. '
        'Không thay đổi các đáp án hoặc kết quả benchmark đã ghi.',
        '',
        '## Các câu sai hoặc từ chối trong lượt cuối',
        '',
    ]
    for row in errors:
        predicted = row['result'].get('best_choice', row['result'].get('error', '?'))
        lines.append(f"- {row['id']}: cần `{row['expected']}`, nhận `{predicted}` — {row['question']}")
    if not errors:
        lines.append('Không có trong lượt này.')
    lines += ['', '## Theo chương', '', '| Chương | Đúng/tổng |', '|---|---|']
    for topic, (correct, total) in final['by_topic'].items():
        lines.append(f'| {topic} | {correct}/{total} |')
    lines += ['', '## Nguồn và tái kiểm', '',
        '[Model card Qwen chính thức](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF) — giấy phép qwen-research, '
        'trọng số tải được; không gọi là Apache/OSI open source. '
        '[llama.cpp b11159](https://github.com/ggml-org/llama.cpp/releases/tag/b11159).', '',
        'Chi tiết từng câu: `benchmark-final.json`. Kết quả ảnh: `ocr-smoke.json`. '
        'Kiểm tra tiến trình: `runtime-smoke.json`. Hướng dẫn chạy lại và dùng tool: `../README.md`.', '',
        f"SHA-256 bộ câu hỏi: `{final['dataset_sha256']}`.", '']
    (ROOT/'artifacts/validation-report.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:24]))


if __name__ == '__main__':
    main()
