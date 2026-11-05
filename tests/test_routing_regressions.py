"""Counterexamples discovered in the external development run; no answer labels."""
import unittest
from unittest.mock import patch
from formula_retrieval import profile
from full_book_tutor import scope_cues, retrieve


class RoutingRegressionTests(unittest.TestCase):
    def test_density_name_does_not_declare_poisson(self):
        for query in [r'设密度函数 p(x)=1/a,0<x<a，求分布',
                      r'设随机变量，P(X=0)=1/2，判断是否服从大数定律']:
            self.assertNotIn('poisson',profile(query)['models'])
        for query in [r'X\sim P(\lambda)，求数学期望', 'X服从泊松分布']:
            self.assertIn('poisson',profile(query)['models'])

    def test_scalar_greek_symbols_and_denominators_are_not_models(self):
        p=profile(r'Y_n\xrightarrow{P}\gamma，\beta 为常数，2/(n(n+1))')
        self.assertNotIn('gamma',p['models'])
        self.assertNotIn('beta',p['models'])
        self.assertNotIn('normal',p['models'])
        self.assertIn('gamma',profile(r'X\sim Gamma(\alpha,\beta)')['models'])
        self.assertIn('beta',profile(r'X\sim Beta(\alpha,\beta)')['models'])
        self.assertIn('normal',profile(r'X\sim N(\mu,\sigma^2)')['models'])

    def test_tex_distribution_and_braced_extrema_are_recognized(self):
        p=profile(r'X\sim\mathrm{Exp}(\lambda)，求Fisher信息量')
        self.assertTrue(p['active'])
        for op in ['min','max']:
            p=profile('Y='+chr(92)+op+r'\{X_1,X_2\}')
            self.assertIn('minimum' if op=='min' else 'maximum',p['operations'])

    def test_shifted_exponential_closed_boundary_does_not_turn_into_poisson(self):
        p=profile(r'设随机变量密度p(x)=e^{-(x-a)},x\geq a，Y_n=\min\{X_1,X_2\}')
        self.assertIn('shifted_exponential',p['models'])
        self.assertNotIn('poisson',p['models'])
        self.assertIn('minimum',p['operations'])

    def test_statistical_symbols_and_terminology_pass_scope_without_generic_algebra(self):
        for query in [r'若P(A\mid B)=1，哪项正确？',r'A\cup B=B，说明什么？',
                      r'X_n\xrightarrow{P}c，如何理解？',r'为什么H_0与H_1不可交换？',
                      '第一类错误和第二类错误的关系是什么？','蒙特卡洛的原理及应用']:
            self.assertTrue(scope_cues(query),query)
        for query in ['a^2+b^2=c^2','今天晚饭吃什么比较好','编写一个库存管理系统']:
            self.assertFalse(scope_cues(query),query)

    def test_unrelated_input_and_incomplete_parameter_request_still_clarify(self):
        with patch('full_book_tutor.vectors.search') as search:
            for query in ['今天晚饭吃什么比较好','请估计参数']:
                self.assertEqual(retrieve(query)['status'],'needs_problem_context')
            search.assert_not_called()


if __name__=='__main__':unittest.main()
