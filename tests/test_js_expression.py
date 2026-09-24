import unittest
from src.js_expression import Parser, solve_expression


class JavaScriptExpressionTests(unittest.TestCase):
    def test_left_to_right_string_conversion(self):
        self.assertEqual(Parser('"4" + 3 + 1').parse(), '431')
        self.assertEqual(Parser('4 + 3 + "1"').parse(), '71')
        self.assertEqual(Parser('"35" - 3').parse(), 32.0)

    def test_arithmetic_precedence_and_grouping(self):
        self.assertEqual(Parser('2 + 3 * 4').parse(), 14.0)
        self.assertEqual(Parser('(2 + 3) * 4').parse(), 20.0)
        self.assertEqual(Parser('10 - 3 - 2').parse(), 5.0)

    def test_javascript_remainder_sign(self):
        self.assertEqual(Parser('-7 % 3').parse(), -1.0)
        self.assertEqual(Parser('7 % -3').parse(), 1.0)

    def test_unary_and_empty_string_conversion(self):
        self.assertEqual(Parser('+"12" + 3').parse(), 15.0)
        self.assertEqual(Parser('"" - 3').parse(), -3.0)

    def test_do_not_execute_code_or_guess_unsupported(self):
        for expression in ['fetch("https://example.com")', 'process.exit()', '__import__("os")',
                           '1; 2', '[1]+2', '012+1', '1/0', 'Math.random()', 'x + 1', '2**3', '2++3', '2--3']:
            with self.subTest(expression=expression):
                self.assertIsNone(solve_expression('JavaScript value of '+expression+'?', dict(A='1',B='2',C='3',D='4')))

    def test_unique_typed_answer_and_question_scope(self):
        options = dict(A='"431"', B='431', C='8', D='"71"')
        self.assertEqual(solve_expression('What is the JavaScript value of "4" + 3 + 1?', options)[0], 'A')
        self.assertIsNone(solve_expression('What is the Python value of "4" + 3 + 1?', options))
        self.assertIsNone(solve_expression('Which is NOT the JavaScript value of "4" + 3 + 1?', options))
        self.assertIsNone(solve_expression('JavaScript value of "4"+3+1?', dict(A='"431"',B='"431"')))


if __name__ == '__main__':
    unittest.main()
