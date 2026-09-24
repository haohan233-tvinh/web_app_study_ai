import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

with open(r"d:\pop\web_app_study_ai\data\course_knowledge.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for p in data['2-HTML.pdf']['pages']:
    if p['page'] in [14, 15, 16]:
        print(f"=== PAGE {p['page']} ===")
        print(p['content'])
