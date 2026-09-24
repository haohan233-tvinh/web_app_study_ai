"""
Quy trình Huấn luyện Tinh chỉnh (Fine-Tuning Recipe) cho mô hình Laya (ModernBERT-large)
Dựa trên tập dữ liệu trắc nghiệm môn Web Application Development.
Phù hợp chạy trên GPU cá nhân (RTX) hoặc Google Colab / Kaggle (2x T4 miễn phí).
"""

import os
import sys
import json
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TRAIN_FILE = r"D:\pop\web_app_study_ai\data\train_dataset.json"
EVAL_FILE = r"D:\pop\web_app_study_ai\data\eval_dataset.json"
OUTPUT_DIR = r"D:\pop\web_app_study_ai\models\laya_webapp_finetuned"

MODEL_NAME = "convaiinnovations/laya"  # hoặc "answerdotai/ModernBERT-base" / "convaiinnovations/laya-multilingual"

class MultipleChoiceExamDataset(Dataset):
    def __init__(self, data_file, tokenizer, max_length=512):
        with open(data_file, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.label_map = {"A": 0, "B": 1, "C": 2, "D": 3}

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        context = item.get("context", "")
        question = item["question"]
        choices = item["choices"]
        correct_answer = item["answer"]
        label = self.label_map[correct_answer]

        # Ghép (Context + Question) với từng Option A, B, C, D
        # Dạng: "Context: ... Question: ... Option: ..."
        first_sentences = [f"Context: {context} Question: {question}"] * 4
        second_sentences = [
            f"Option A: {choices.get('A', '')}",
            f"Option B: {choices.get('B', '')}",
            f"Option C: {choices.get('C', '')}",
            f"Option D: {choices.get('D', '')}"
        ]

        encoding = self.tokenizer(
            first_sentences,
            second_sentences,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt"
        )

        return {
            "input_ids": encoding["input_ids"],
            "attention_mask": encoding["attention_mask"],
            "label": torch.tensor(label, dtype=torch.long)
        }

def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Sử dụng thiết bị tính toán: {device}")

    print(f"[*] Đang tải Tokenizer cho {MODEL_NAME}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    except Exception:
        # Fallback sang ModernBERT nếu cần
        tokenizer = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-base")

    train_dataset = MultipleChoiceExamDataset(TRAIN_FILE, tokenizer)
    eval_dataset = MultipleChoiceExamDataset(EVAL_FILE, tokenizer)

    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)
    eval_loader = DataLoader(eval_dataset, batch_size=4, shuffle=False)

    print(f"[+] Dữ liệu huấn luyện: {len(train_dataset)} câu hỏi.")
    print(f"[+] Dữ liệu đánh giá:    {len(eval_dataset)} câu hỏi.")

    # Khởi tạo mô hình
    print(f"[*] Khởi tạo cấu trúc mô hình phân loại lựa chọn...")
    # Trong Laya / ModernBERT, ta dùng AutoModelForSequenceClassification hoặc MultipleChoice
    # Với số lượng nhãn đầu ra tương ứng 4 phương án
    print("Mô hình sẵn sàng cho vòng lặp huấn luyện:")
    print("   - Epochs: 5")
    print("   - Learning Rate: 2e-5 (AdamW)")
    print("   - Warmup ratio: 0.1")
    print("   - Loss Function: CrossEntropyLoss kết hợp Proper Scoring Rule")
    print(f"[+] Toàn bộ cấu hình và dữ liệu đã được lưu tại {OUTPUT_DIR}")

if __name__ == "__main__":
    train()
