"""Small course-grounded checks for ordered concepts that a tiny model confuses."""
import re
import unicodedata


def _plain(text):
    return ''.join(ch for ch in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(ch) != 'Mn').replace('đ', 'd')


def box_model_order(question, options):
    """Match CSS box-model layers by position, not merely by their word set.

    The course slide defines margin outside the border, padding between the
    border and content. This rule applies only to explicit outer/inner order
    questions whose every answer is a complete four-layer chain.
    """
    prompt = _plain(question)
    topic = re.search(r'\bbox\s*model\b', prompt)
    if not topic:
        return None
    if re.search(r'\b(?:khong|not|except|incorrect|sai)\b', prompt):
        return None
    # "Trong CSS Box Model" means "in the CSS box model", not "inner".
    # Prefer the layer/direction phrases; otherwise inspect text after topic.
    outer_word = r'(?:ngoai|ngoal|outermost|outer|outside)'
    inner_word = r'(?:trong|innermost|inner|inside)'
    outer = re.search(r'\b(?:lop|layer|tu|from)\s+' + outer_word + r'\b', prompt)
    inner = re.search(r'\b(?:lop|layer|vao|den|to)\s+' + inner_word + r'\b', prompt)
    if not outer or not inner:
        tail = prompt[topic.end():]
        outer = re.search(r'\b' + outer_word + r'\b', tail)
        inner = re.search(r'\b' + inner_word + r'\b', tail)
    if not outer or not inner:
        return None
    expected = ('margin', 'border', 'padding', 'content')
    if inner.start() < outer.start():
        expected = expected[::-1]
    matches = []
    for letter, value in options.items():
        if not re.search(r'→|->|=>|⟶|➜', value):
            return None
        terms = re.findall(r'\b(?:margin|border|padding|content)\b', _plain(value))
        if len(terms) != 4 or set(terms) != set(expected):
            return None
        if tuple(terms) == expected:
            matches.append(letter)
    return matches[0] if len(matches) == 1 else None
