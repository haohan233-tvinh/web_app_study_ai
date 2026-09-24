"""Strict parser: never fabricate text for missing answer labels."""
import re
from dataclasses import dataclass, field

LABEL = re.compile(r'(?<!\S)[\(\[]?([A-H])[\)\].:]\s*')
NUMBER = re.compile(r'^\s*(?:(?:question|câu|q)\s*\d+\s*[:.)-]?|\d+\s*[.)])\s*', re.I)
FOOTER = re.compile(r'^(?:correct\s*answers?\s*:|explanation\s*:|answer\s*:|feedback\b|check\s*$|finish attempt\b|next page\b)', re.I)
CHROME = re.compile(r'^(?:not yet answered|marked out of|flag question|clear my choice|question\s+\d+\s*$)', re.I)


@dataclass
class Question:
    text: str
    options: dict
    multi: bool = False
    count: int | None = None
    errors: list = field(default_factory=list)


def parse_question(lines, expected_options=4, mode='auto'):
    if isinstance(lines, str):
        lines = lines.splitlines()
    question, options, current, errors = [], {}, None, []
    for raw in lines:
        line = raw.strip().replace('\u00a0', ' ')
        # Lowercase Moodle labels only at row start. Do not split CSS a:hover
        # or a:visited inside an option into additional answer labels.
        line = re.sub(r'^(\s*[\(\[]?)([a-h])([\)\].:]\s+)',
                      lambda m: m[1] + m[2].upper() + m[3], line)
        if not line or CHROME.match(line):
            continue
        if FOOTER.match(line):
            break
        matches = list(LABEL.finditer(line))
        # A sentence beginning with "A ..." is never an option without punctuation.
        # Mid-line labels are accepted only after an option, or after question text.
        if matches:
            prefix = line[:matches[0].start()].strip()
            if prefix:
                if current:
                    options[current] += '\n' + prefix
                else:
                    question.append(NUMBER.sub('', prefix))
            for j, m in enumerate(matches):
                label = m.group(1).upper()
                end = matches[j + 1].start() if j + 1 < len(matches) else len(line)
                text = line[m.end():end].strip()
                if label in options:
                    errors.append(f'Nhãn {label} xuất hiện hai lần; hãy chụp riêng một câu.')
                options[label] = text
                current = label
        elif current:
            options[current] += '\n' + line
        else:
            question.append(NUMBER.sub('', line))
    text = '\n'.join(question).strip()
    normalized = ' '.join(text.lower().split())
    count = None
    count_match = re.search(r'(?:choose|select|chọn)\s+(two|three|four|2|3|4|hai|ba|bốn)\b', normalized)
    if count_match:
        count = {'two': 2, 'three': 3, 'four': 4, 'hai': 2, 'ba': 3, 'bốn': 4,
                 '2': 2, '3': 3, '4': 4}[count_match.group(1)]
    explicit_single = bool(re.search(r'(?:select|choose) (?:one|a single)|chọn (?:một|1)\b', normalized))
    explicit_multi = bool(count or re.search(r'select all|choose all|all that apply|one or more|multiple answers|chọn nhiều|nhiều đáp án', normalized))
    plural = bool(re.search(r'which (?:of the following )?(?:\w+ ){0,4}are\b', normalized))
    multi = not explicit_single and (explicit_multi or plural)
    if mode != 'auto':
        multi = mode == 'multi'
        if not multi:
            count = None
    if not text:
        errors.append('Thiếu nội dung câu hỏi.')
    required = list('ABCDEFGH'[:expected_options])
    if expected_options and set(options) != set(required):
        errors.append(f'Cần đủ {", ".join(required)}; hiện đọc được {", ".join(options) or "không có"}. Chụp lại hoặc đổi số phương án bằng lệnh n.')
    if len(options) < 2 or any(not value.strip() for value in options.values()):
        errors.append('Phương án bị trống hoặc không đủ.')
    return Question(text, options, multi, count, errors)
