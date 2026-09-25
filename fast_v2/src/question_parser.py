"""Strict parser: never fabricate text for missing answer labels."""
import re
from dataclasses import dataclass, field

LABEL = re.compile(r'(?<!\S)[\(\[]?([A-H])[\)\].:]\s*')
NUMBER = re.compile(r'^\s*(?:(?:question|câu|q)\s*\d+\s*[:.)-]?|\d+\s*[.)])\s*', re.I)
FOOTER = re.compile(r'^(?:correct\s*answers?\s*:|explanation\s*:|answer\s*:|feedback\b|check\s*$|finish attempt\b|next page\b)', re.I)
CHROME = re.compile(r'^(?:not yet answered|marked out of|flag question|clear my choice|question\s+\d+\s*$)', re.I)
BARE_LABEL = re.compile(r'^\s*([A-Ha-h])\s+\S')
START_LABEL = re.compile(r'^\s*[\(\[]?([A-H])[\)\].:]', re.I)


def _promote_badge_labels(lines, expected_options):
    """Accept bare A-D badges only when a complete ordered option run is visible.

    Some quiz themes put letters inside circles. OCR returns ``A text`` with
    no punctuation; a lone ``A ...`` can also be the question itself, so one
    isolated letter is never enough to reinterpret a line as an option.
    """
    if not 3 <= expected_options <= 8:
        return lines
    expected = list('ABCDEFGH'[:expected_options])
    candidates = []
    for index, line in enumerate(lines):
        marked = START_LABEL.match(line)
        bare = None if marked else BARE_LABEL.match(line)
        if marked or bare:
            candidates.append((index, (marked or bare).group(1).upper(), bare is not None))
    for start in range(len(candidates) - expected_options, -1, -1):
        selected = candidates[start:start + expected_options]
        if (selected[0][1] != 'A' or
                [letter for _, letter, _ in selected] != expected or
                not any(line.strip() for line in lines[:selected[0][0]])):
            continue
        normalized = list(lines)
        for index, _, bare in selected:
            if bare:
                normalized[index] = re.sub(r'^(\s*)([A-Ha-h])(\s+)',
                                           r'\1\2)\3', normalized[index], count=1)
        return normalized
    return lines


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
    lines = _promote_badge_labels(lines, expected_options)
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
    multi, count = infer_selection(text, mode)
    if not text:
        errors.append('Thiếu nội dung câu hỏi.')
    required = list('ABCDEFGH'[:expected_options])
    if expected_options and set(options) != set(required):
        errors.append(f'Cần đủ {", ".join(required)}; hiện đọc được {", ".join(options) or "không có"}. Chụp lại hoặc đổi số phương án bằng lệnh n.')
    if len(options) < 2 or any(not value.strip() for value in options.values()):
        errors.append('Phương án bị trống hoặc không đủ.')
    return Question(text, options, multi, count, errors)


def infer_selection(text, mode='auto'):
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
    return multi, count


def structured_question(text, options, expected_options=4, mode='auto'):
    text = NUMBER.sub('', text.strip())
    options = {key: value.strip() for key, value in options.items()}
    multi, count = infer_selection(text, mode)
    errors = []
    if not text:
        errors.append('Thiếu nội dung câu hỏi.')
    if set(options) != set('ABCDEFGH'[:expected_options]) or any(not value for value in options.values()):
        errors.append('Thiếu hoặc trống một phương án. Hãy chỉnh vùng chụp rồi giải lại.')
    return Question(text, options, multi, count, errors)
