"""Spatial OCR grouping. Geometry is in original screenshot pixels."""
from dataclasses import dataclass
import re

import numpy as np

from .question_parser import structured_question


@dataclass(frozen=True)
class ManualCapture:
    regions: tuple
    crops: tuple


def _text_rows(boxes):
    rows = []
    for box in sorted(boxes, key=lambda item: (item['cy'], item['left'])):
        row = next((candidate for candidate in rows if abs(candidate['cy'] - box['cy']) <=
                    .48 * max(1, min(candidate['height'], box['height']))), None)
        if row is None:
            row = {'cy': box['cy'], 'height': box['height'], 'top': box['top'],
                   'bottom': box['bottom'], 'left': box['left'], 'boxes': []}
            rows.append(row)
        row['boxes'].append(box)
        row['left'] = min(row['left'], box['left'])
        row['bottom'] = max(row['bottom'], box['bottom'])
    for row in rows:
        row['boxes'].sort(key=lambda box: box['left'])
        row['text'] = ' '.join(box['text'] for box in row['boxes'])
    return rows


def _card_borders(image):
    """Find long pale blue/grey 1px strokes used by Moodle-like answer cards."""
    rgb = np.asarray(image.convert('RGB'))
    if rgb.shape[0] < 70 or rgb.shape[1] < 160:
        return []
    r, g, b = [rgb[:, :, i].astype(np.int16) for i in range(3)]
    pale = ((r >= 165) & (g >= 175) & (b >= 185) &
            (r <= 248) & (g <= 250) & (b <= 253) &
            ((b - r >= 7) | (g - r >= 7)))
    count = pale.sum(axis=1)
    ys = np.flatnonzero(count >= image.width * .48)
    runs = []
    for y in ys:
        if not runs or y > runs[-1][-1] + 2:
            runs.append([int(y)])
        else:
            runs[-1].append(int(y))
    return [int(np.median(run)) for run in runs]


def _remove_badge(text, expected, row, width):
    boxes = row['boxes']
    badge = {expected}
    if expected == 'A':
        badge.add('4')
    if (len(boxes) > 1 and boxes[0]['right'] < width * .09 and
            boxes[0]['text'].strip('().:[]').upper() in badge):
        return ' '.join(box['text'] for box in boxes[1:])
    if row['left'] < width * .09:
        return re.sub(r'^\s*' + re.escape(expected) + r'\s+(?=\S)', '',
                      text, count=1, flags=re.I)
    return text


def _group_card_rows(image, boxes, expected):
    borders = _card_borders(image)
    rows = _text_rows(boxes)
    cards = []
    for top, bottom in zip(borders, borders[1:]):
        if bottom - top < 27 or bottom - top > max(250, image.height * .45):
            continue
        inside = [row for row in rows if top + 3 <= row['cy'] <= bottom - 2]
        if inside:
            cards.append((top, bottom, inside))
    # Consecutive card top/bottom strokes leave a short gap between cards.
    if len(cards) > expected:
        cards = cards[-expected:]
    if len(cards) != expected:
        return None
    options = {}
    for index, (_, _, inside) in enumerate(cards):
        lines = [_remove_badge(row['text'], chr(65 + index), row, image.width)
                 if row is inside[0] else row['text'] for row in inside]
        options[chr(65 + index)] = '\n'.join(line for line in lines if line.strip()).strip()
    question = '\n'.join(row['text'] for row in rows if row['cy'] < cards[0][0]).strip()
    q = structured_question(question, options, expected)
    return {'question': q, 'method': 'card_borders', 'weak': False}


def _group_radio_rows(image, boxes, expected):
    rgb = np.asarray(image.convert('RGB'))
    if rgb.shape[0] < 60 or rgb.shape[1] < 100:
        return None
    width = min(max(35, int(image.width * .17)), 130)
    patch = rgb[:, :width].astype(np.int16)
    light = ((patch.min(axis=2) >= 130) & (patch.max(axis=2) <= 250) &
             (patch.max(axis=2) - patch.min(axis=2) <= 28))
    # Text is normally dark. Radio/checkbox backgrounds leave repeated light
    # compact marks in the left gutter even if OCR drops their labels.
    candidate = np.flatnonzero(light.sum(axis=1) >= 9)
    runs = []
    for y in candidate:
        if not runs or y > runs[-1][-1] + 1:
            runs.append([int(y)])
        else:
            runs[-1].append(int(y))
    marks = []
    for run in runs:
        if not 9 <= len(run) <= 40:
            continue
        points = np.argwhere(light[run[0]:run[-1]+1])
        if len(points) < 45:
            continue
        xs = points[:, 1]
        if np.percentile(xs, 90) - np.percentile(xs, 10) > 42:
            continue
        marks.append((sum(run) / len(run), float(np.median(xs))))
    if len(marks) < expected:
        return None
    marks = marks[-expected:]
    if max(x for _, x in marks) - min(x for _, x in marks) > 20:
        return None
    rows = _text_rows(boxes)
    options = {}
    first_y = marks[0][0]
    for index, (cy, x) in enumerate(marks):
        low = (marks[index-1][0] + cy) / 2 if index else cy - 25
        high = (cy + marks[index+1][0]) / 2 if index+1 < expected else image.height
        inside = [row for row in rows if low <= row['cy'] < high]
        options[chr(65 + index)] = '\n'.join(
            _remove_badge(row['text'], chr(65 + index), row, image.width)
            if row is inside[0] else row['text'] for row in inside).strip() if inside else ''
    question = '\n'.join(row['text'] for row in rows if row['cy'] < first_y - 25)
    q = structured_question(question, options, expected)
    return {'question': q, 'method': 'radio_markers', 'weak': False}


def _group_indent_rows(boxes, expected):
    """Last resort for themes with no cards or labels; never invent text."""
    rows = _text_rows(boxes)
    if len(rows) < expected + 1:
        return None
    # Large spacing often marks the question/answer boundary. Wrapped lines
    # typically begin farther right than the first line of their option.
    gaps = [(rows[i]['top'] - rows[i-1]['bottom'], i) for i in range(1, len(rows))]
    candidates = sorted(gaps, reverse=True)
    start = next((i for _, i in candidates if len(rows) - i >= expected), 1)
    answer_rows = rows[start:]
    baseline = min(row['left'] for row in answer_rows)
    starts = [i for i, row in enumerate(answer_rows)
              if row['left'] <= baseline + max(9, row['height'] * .7)]
    if len(starts) != expected or starts[0] != 0:
        if len(answer_rows) == expected:
            starts = list(range(expected))
        else:
            gaps = [(answer_rows[i]['top'] - answer_rows[i-1]['bottom'], i)
                    for i in range(1, len(answer_rows))]
            if len(gaps) < expected - 1:
                return None
            starts = [0] + sorted(i for _, i in sorted(gaps, reverse=True)[:expected-1])
    options = {}
    for index, begin in enumerate(starts):
        end = starts[index + 1] if index + 1 < expected else len(answer_rows)
        options[chr(65 + index)] = '\n'.join(row['text'] for row in answer_rows[begin:end])
    question = '\n'.join(row['text'] for row in rows[:start])
    return {'question': structured_question(question, options, expected),
            'method': 'line_indent', 'weak': True}


def group_auto(image, boxes, expected):
    card = _group_card_rows(image, boxes, expected)
    if card and not card['question'].errors:
        return card
    radio = _group_radio_rows(image, boxes, expected)
    if radio and not radio['question'].errors:
        return radio
    return _group_indent_rows(boxes, expected) or card or radio
