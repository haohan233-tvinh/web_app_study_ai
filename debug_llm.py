import os
import sys
import re
import time
from llama_cpp import Llama

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

llm = Llama(
    model_path=r"D:\pop\web_app_study_ai\models\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    n_gpu_layers=-1,
    verbose=False
)

context = """
Lists
• <li> tag defines a list item
• List items can be grouped in 3 types:
  – Unordered lists, which are like lists of bullet points: <ul>
  – Ordered lists, which use a sequence of numbers or letters instead of bullet points: <ol>
  – Description lists, which allow you to define and describe a term: <dl>, <dt>, <dd>
"""

question = "Which of the following are valid HTML list types?"
options = {
    "A": "Ordered List",
    "B": "Unordered List",
    "C": "Bullet List",
    "D": "Linear List"
}

is_multi = True
opt_str = "\n".join([f"{k}. {v}" for k, v in sorted(options.items())])

prompt = f"""<|im_start|>system
You are an expert exam solver in Web Application Development.
Review the question and all options (A, B, C, D).
For EACH option, check if it matches the valid concepts in the slide.
Then write:
FINAL ANSWER: [correct letters]
<|im_end|>
<|im_start|>user
[Slide Context]:
{context}

[Question]:
{question}

[Options]:
{opt_str}

Check each option (A, B, C, D) one by one, then output the FINAL ANSWER.
<|im_end|>
<|im_start|>assistant
"""

t0 = time.time()
res = llm(prompt, max_tokens=180, temperature=0.01)
elapsed = time.time() - t0

content = res["choices"][0]["text"].strip()
print(f"Elapsed: {elapsed:.2f}s")
print("Raw output:\n" + content)
