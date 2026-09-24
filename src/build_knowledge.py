"""Rebuild local course corpus, preserving code, entities, page numbers and provenance."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    import fitz
    from bs4 import BeautifulSoup
    settings = json.loads((ROOT / 'settings.json').read_text(encoding='utf-8'))
    course = Path(settings['course_dir'])
    result, manifest = {}, []
    for path in sorted(course.glob('*.pdf')):
        with fitz.open(path) as doc:
            pages = [{'page': i + 1, 'content': page.get_text(sort=True).strip()}
                     for i, page in enumerate(doc)]
        result[path.name] = {'source': path.name, 'type': 'exercise' if 'exercise' in path.name.lower()
                             else 'lecture_slides', 'total_pages': len(pages), 'pages': pages}
        manifest.append({'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'pages': len(pages), 'empty_pages': [p['page'] for p in pages if not p['content']]})
    for path in sorted((course / 'Study Guide').glob('*.html')):
        soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'head']):
            tag.decompose()
        result[path.name] = {'source': path.name, 'type': 'study_guide',
                             'full_text': soup.get_text('\n', strip=True)}
        manifest.append({'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if not result:
        raise RuntimeError(f'No documents in {course}')
    (ROOT / 'data/course_knowledge.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'data/source_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(result)} documents; {sum(len(d.get("pages", [])) for d in result.values())} PDF pages')


if __name__ == '__main__':
    build()
