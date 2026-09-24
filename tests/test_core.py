import json
from pathlib import Path
import unittest
from unittest.mock import patch
from clipboard_solver import ExamSolver, ROOT
from src.question_parser import parse_question
from src.retrieval import CourseIndex


class ParserTests(unittest.TestCase):
    def test_number_and_inline_merged_labels(self):
        q = parse_question('Câu 12: Which are valid list types?\nA) Ordered\nB) Unordered C) Linear\nD) Description')
        self.assertEqual(q.text, 'Which are valid list types?')
        self.assertEqual(q.options, dict(A='Ordered', B='Unordered', C='Linear', D='Description'))
        self.assertTrue(q.multi)
        self.assertFalse(q.errors)

    def test_missing_c_never_fabricated(self):
        q = parse_question('1. What is a list?\nA) One\nB) Two three four five\nD) Six')
        self.assertEqual(q.options['B'], 'Two three four five')
        self.assertNotIn('C', q.options)
        self.assertTrue(q.errors)

    def test_article_a_is_question(self):
        q = parse_question('A web browser performs which role?\nA) Client\nB) Compiler\nC) Disk\nD) Printer')
        self.assertEqual(q.text, 'A web browser performs which role?')
        self.assertFalse(q.errors)

    def test_are_alone_does_not_force_multi(self):
        q = parse_question('How many heading levels are there?\nA) 6\nB) 4\nC) 3\nD) 8')
        self.assertFalse(q.multi)
        q = parse_question('What are the two parts of a CSS rule?\nA) Selector and declaration\nB) a\nC) b\nD) c')
        self.assertFalse(q.multi)

    def test_single_overrides_plural(self):
        q = parse_question('Select one: Which of the following are valid?\nA) One\nB) Two\nC) Three\nD) Four')
        self.assertFalse(q.multi)

    def test_choose_two(self):
        q = parse_question('Choose two valid types.\nA) One\nB) Two\nC) Three\nD) Four')
        self.assertEqual(q.count, 2)
        self.assertTrue(q.multi)

    def test_footer_never_leaks_answer(self):
        q = parse_question('Question 9: List types?\nA) Ordered\nB) Unordered\nC) Linear\nD) Grid\nCorrect Answers: C, D\nExplanation: bad')
        self.assertEqual(q.options['D'], 'Grid')
        self.assertNotIn('Correct', str(q))

    def test_moodle_noise_and_wrapped_option(self):
        q = parse_question('Question 7\nNot yet answered\nMarked out of 1.00\nWhich is correct?\nSelect one:\nA) a function\npassed into another function\nB) b\nC) c\nD) d\nClear my choice')
        self.assertIn('passed into', q.options['A'])
        self.assertEqual(q.options['D'], 'd')
        self.assertFalse(q.errors)

    def test_duplicates_and_two_questions_rejected(self):
        q = parse_question('Q1. Test?\nA) a\nB) b\nC) c\nD) d\nQ2. Test?\nA) e\nB) f\nC) g\nD) h')
        self.assertTrue(q.errors)

    def test_valid_code_continuation(self):
        q = parse_question('What is output?\nA) const x = 2;\nconsole.log(x);\nB) two\nC) three\nD) four')
        self.assertIn('console.log(x);', q.options['A'])
        self.assertFalse(q.errors)

    def test_css_pseudo_classes_are_not_answer_labels(self):
        q = parse_question('Which pseudo class?\nA) a:hover\nB) a:active\nC) a:visited\nD) a.href')
        self.assertEqual(q.options, dict(A='a:hover', B='a:active', C='a:visited', D='a.href'))
        self.assertFalse(q.errors)

    def test_lowercase_moodle_labels(self):
        q = parse_question('Which selector?\na. .highlight\nb. #highlight\nc. highlight\nd. a:hover')
        self.assertEqual(q.options['D'], 'a:hover')
        self.assertFalse(q.errors)


class IntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.solver = ExamSolver()

    def test_real_corpus_and_tag_preservation(self):
        s = self.solver
        slides = s.index.search('Which HTML element creates a hyperlink?', {'A':'<a>', 'B':'<link>', 'C':'<url>', 'D':'<href>'})
        self.assertIn(('2-HTML.pdf', 22), [(p['source'],p['page']) for p in slides])
        html = [p['text'] for p in s.slides if p['source'].endswith('.html')]
        self.assertTrue(any('<html>' in p or '<head>' in p for p in html))
        self.assertLess(max(map(len, html)), 2500)

    def test_model_failure_is_not_guess(self):
        with patch.object(self.solver, '_thermal_gate', return_value=0), \
             patch.object(self.solver.model, 'chat', side_effect=RuntimeError('offline model absent')):
            result = self.solver.solve('Unique failure test HTML element?', dict(A='<a>',B='<b>',C='<c>',D='<d>'))
        self.assertIn('error', result)
        self.assertNotIn('best_choice', result)

    def test_bad_labels_rejected(self):
        result = self.solver.solve('Which tag?', {'A':'x','Z':'y'})
        self.assertIn('error', result)

    def test_corpus_contains_no_benchmark_answer_bank(self):
        data = json.loads((ROOT/'data/course_knowledge.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data), 12)
        self.assertEqual(sum(len(d.get('pages',[])) for d in data.values()), 317)
        self.assertNotIn('course_benchmark.json', data)


if __name__ == '__main__':
    unittest.main()
