"""Strict, non-executing interpreter for a small subset of JavaScript expressions.

No eval, function calls, variables, property access, files, or subprocesses.
Only finite numeric/string literals, parentheses, unary +/- and + - * / %.
Anything outside that grammar is delegated to the language model.
"""
import ast
from decimal import Decimal
import math
import re

TOKEN = re.compile(r'''\s*("[^"\\]*"|'[^'\\]*'|(?:\d+\.?\d*|\.\d+)|[()+*/%\-])''')
QUESTION = re.compile(r'^(?:what\s+is\s+(?:the\s+)?)?(?:javascript|js)\s+(?:value|result|output)\s+of\s+(.+?)\s*\??\s*$', re.I | re.S)


def js_number(value):
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return 0.0
        if not re.fullmatch(r'[+-]?(?:\d+\.?\d*|\.\d+)', value):
            return float('nan')
    return float(value)


def js_string(value):
    if isinstance(value, str):
        return value
    if math.isnan(value):
        return 'NaN'
    if not math.isfinite(value):
        raise ValueError('Non-finite values are outside supported numeric output')
    if value.is_integer():
        return str(int(value))
    if abs(value) < 1e-6:
        raise ValueError('Exponential string conversion is outside supported output')
    return format(Decimal(str(value)), 'f')


class Parser:
    def __init__(self, expression):
        expression = expression.strip()
        if len(expression) > 256:
            raise ValueError('Expression too long')
        self.tokens, self.at = [], 0
        offset = 0
        while offset < len(expression):
            match = TOKEN.match(expression, offset)
            if not match:
                raise ValueError('Unsupported JavaScript syntax')
            if match[1] in {'+', '-'} and expression[match.end():match.end()+1] == match[1]:
                raise ValueError('Increment/decrement syntax is excluded')
            self.tokens.append(match[1])
            offset = match.end()
        if len(self.tokens) > 64:
            raise ValueError('Too many tokens')

    def take(self):
        if self.at >= len(self.tokens):
            raise ValueError('Truncated expression')
        value = self.tokens[self.at]
        self.at += 1
        return value

    def atom(self):
        token = self.take()
        if token == '(':
            value = self.expression(0)
            if self.take() != ')':
                raise ValueError('Unbalanced parentheses')
            return value
        if token in {'+', '-'}:
            value = js_number(self.atom())
            return value if token == '+' else -value
        if token.startswith(('"', "'")):
            return ast.literal_eval(token)
        if not re.fullmatch(r'(?:\d+\.?\d*|\.\d+)', token):
            raise ValueError('Expected literal')
        # Reject legacy octal and very large/overflowing literals instead of guessing.
        if len(token) > 1 and token[0] == '0' and token[1].isdigit():
            raise ValueError('Legacy numeric literal')
        value = float(token)
        if not math.isfinite(value) or abs(value) > 2**53 - 1:
            raise ValueError('Outside safe literal range')
        return value

    def expression(self, minimum=0):
        left = self.atom()
        precedence = {'+':1, '-':1, '*':2, '/':2, '%':2}
        while self.at < len(self.tokens):
            op = self.tokens[self.at]
            level = precedence.get(op, -1)
            if level < minimum:
                break
            self.at += 1
            right = self.expression(level + 1)
            if op == '+' and (isinstance(left, str) or isinstance(right, str)):
                left = js_string(left) + js_string(right)
            else:
                a, b = js_number(left), js_number(right)
                if op == '+': left = a + b
                elif op == '-': left = a - b
                elif op == '*': left = a * b
                elif op == '/':
                    if b == 0: raise ValueError('Division by zero excluded')
                    left = a / b
                else:
                    if b == 0: raise ValueError('Remainder by zero excluded')
                    left = math.fmod(a, b)
                if math.isfinite(left) and abs(left) > 2**53-1:
                    raise ValueError('Result outside safe numeric range')
        return left

    def parse(self):
        result = self.expression()
        if self.at != len(self.tokens):
            raise ValueError('Trailing tokens')
        return result


def solve_expression(question, options):
    match = QUESTION.search(question)
    if not match:
        return None
    expression = match[1].rstrip('?').strip().strip('`')
    try:
        value = Parser(expression).parse()
        chosen = []
        for letter, text in options.items():
            text = text.strip().strip('`')
            try:
                other = float('nan') if text == 'NaN' else Parser(text).parse()
            except (ValueError, SyntaxError):
                continue
            # Keep string and number distinct, as in JavaScript MCQ examples.
            same = type(value) is type(other) and (value == other or
                isinstance(value, float) and math.isnan(value) and math.isnan(other))
            if same:
                chosen.append(letter)
        return (chosen[0], expression) if len(chosen) == 1 else None
    except (ValueError, SyntaxError, OverflowError, ZeroDivisionError, RecursionError):
        return None
