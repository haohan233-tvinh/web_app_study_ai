import os
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from huggingface_hub import hf_hub_download

repo_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
filename = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
dest_dir = r"D:\pop\web_app_study_ai\models"

os.makedirs(dest_dir, exist_ok=True)
print(f"[*] Downloading {filename} from {repo_id}...")

downloaded_path = hf_hub_download(
    repo_id=repo_id,
    filename=filename,
    local_dir=dest_dir,
    local_dir_use_symlinks=False
)

print(f"[+] Download complete! Saved to: {downloaded_path}")
