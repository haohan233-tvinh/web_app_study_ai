"""Small in-memory BM25 index; no external service, embedding download, or answer bank."""
import math
import re
import unicodedata
from collections import Counter

STOP = set('which what of the following a an and or is are to in for with from that this how does do select all apply choose correct true false'.split())
STOP.update('nào là của một các trong có không để và gì sau đây được dùng cho với những thế khi chọn đúng sai thuộc tính thẻ chữ màu liên kết ngôn ngữ cơ sở dữ liệu trình duyệt máy chủ'.split())
VI_TERMS = {'thuộc tính': 'attribute', 'thẻ': 'tag', 'màu chữ': 'text color',
            'liên kết': 'hyperlink', 'ngôn ngữ': 'language', 'phương thức': 'method',
            'hàm': 'function', 'cơ sở dữ liệu': 'database', 'bộ chọn': 'selector',
            'máy chủ': 'server', 'trình duyệt': 'browser', 'danh sách': 'list',
            'đối tượng': 'object', 'tham số': 'parameter', 'sự kiện': 'event',
            'khoảng đệm': 'padding', 'lề ngoài': 'margin', 'giá trị': 'value'}
ALIASES = {'hyperlink': 'link', 'hyperlinks': 'link', 'links': 'link', 'linked': 'link',
           'defines': 'define', 'defining': 'define', 'defined': 'define',
           'elements': 'element', 'attributes': 'attribute', 'types': 'type',
           'lists': 'list', 'functions': 'function', 'objects': 'object',
           'databases': 'database', 'styles': 'style', 'selectors': 'selector',
           'requests': 'request', 'responses': 'response', 'modules': 'module',
           'callbacks': 'callback', 'asynchronous': 'async', 'asynchronously': 'async',
           'rendering': 'render', 'routes': 'route', 'routing': 'route'}


def tokens(text):
    # Split camel case before case folding; preserve programming punctuation tokens.
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = unicodedata.normalize('NFKC', text).casefold()
    text += ' ' + ' '.join(english for vietnamese, english in VI_TERMS.items() if vietnamese in text)
    tags = ['tag_' + t for t in re.findall(r'<\s*/?([a-z][\w-]*)\b[^>]*>', text)]
    words = [ALIASES.get(t, t) for t in re.findall(r'[\w]+(?:[.-][\w]+)*|===|!==|==|=>|\$|#[\w-]+', text)
             if t not in STOP and (len(t) > 1 or t == '$' or t.isdigit())]
    return words + tags


class CourseIndex:
    def __init__(self, data):
        self.chunks = []
        for source, doc in data.items():
            if 'pages' in doc:
                sections = [(p['page'], p['content']) for p in doc['pages']]
            else:
                lines, sections, buf = doc.get('full_text', '').splitlines(), [], ''
                for line in lines:
                    if len(buf) + len(line) > 1600 and buf:
                        sections.append((None, buf))
                        buf = buf[-200:] + '\n'
                    buf += line + '\n'
                if buf:
                    sections.append((None, buf))
            for page, text in sections:
                text = re.sub(r'[ \t]+', ' ', text)
                text = re.sub(r'\n\s*\n+', '\n', text).strip()
                if len(text.strip()) > 25:
                    self.chunks.append({'source': source, 'page': page, 'text': text.strip()})
        self.tf = [Counter(tokens(d['text'])) for d in self.chunks]
        self.lengths = [sum(t.values()) for t in self.tf]
        self.average = sum(self.lengths) / max(1, len(self.lengths))
        df = Counter(term for c in self.tf for term in c)
        n = len(self.chunks)
        self.idf = {t: math.log(1 + (n - freq + .5) / (freq + .5)) for t, freq in df.items()}

    def search(self, question, options=None, top_k=5):
        weights = Counter({t: 2.5 for t in tokens(question)})
        for value in (options or {}).values():
            for term in set(tokens(value)):
                weights[term] += .55
        ranked = []
        for i, tf in enumerate(self.tf):
            norm = 1.2 * (.25 + .75 * self.lengths[i] / max(1, self.average))
            score = sum(weight * self.idf.get(term, 0) * (tf[term] * 2.2) / (tf[term] + norm)
                        for term, weight in weights.items() if tf[term])
            if score > 0:
                ranked.append((score, i))
        ranked.sort(reverse=True)
        return [dict(self.chunks[i], score=round(score, 3)) for score, i in ranked[:top_k]]
