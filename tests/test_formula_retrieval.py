"""Formula patterns must preserve material differences and avoid answer reuse."""
import unittest
from formula_retrieval import normalize,profile,comparison,candidates,describe
from full_book_tutor import retrieve
from unittest.mock import patch


def rec(identifier,text,kind='exercise',chapter='6'):
    return {'id':identifier,'question_text':text,'kind':kind,'chapter':chapter,'section':chapter+'.1','pages':[1]}


class FormulaRetrievalTests(unittest.TestCase):
    def test_unicode_and_tex_uniform_order_statistics_match_features(self):
        a=profile('Y₁,Y₂,Y₃ ~ U(0,ϑ)，(4/3)max(Y₁,Y₂,Y₃) 与 4min(Y₁,Y₂,Y₃)')
        b=profile(r'X_1,X_2,X_3\sim U(0,\theta),\frac{4}{3}X_{(3)},4X_{(1)}')
        self.assertEqual(a['models'],b['models'])
        self.assertEqual(set(a['operations']),{'minimum','maximum'})
        self.assertEqual(a['conditions']['fractions'],b['conditions']['fractions'])

    def test_renamed_shifted_exponential_has_same_model_not_same_question_claim(self):
        q=profile('f(t|a)=exp(-(t-a)) I(t>a)，求置信区间')
        c=profile(r'p(x;\theta)=e^{-(x-\theta)}I_{x>\theta}，求置信区间')
        self.assertIn('shifted_exponential',q['models'])
        self.assertTrue(comparison(q,c)['eligible'])

    def test_binomial_coefficient_with_unicode_prior_is_recognized(self):
        q=profile('f(y|q)=C(y-1,r-1)q^r(1-q)^(y-r)，先验Beta(α,β)')
        self.assertEqual(q['models'],['negative_binomial'])
        self.assertIn('prior_beta',q['operations'])
        self.assertIn('negative_binomial',profile(r'f(x|p)=\binom{x-1}{k-1}p^k(1-p)^{x-k}')['models'])

    def test_density_coefficient_next_to_exp_is_not_a_word_boundary_error(self):
        self.assertIn('exponential',profile('p(x;λ)=λ exp(-λx),x>0')['models'])

    def test_model_and_goal_mismatch_are_not_silently_equivalent(self):
        q=profile('X~U(0,a)，求置信区间')
        c=profile('X~U(0,b)，求最大似然估计')
        self.assertTrue(any('置信区间' in d for d in comparison(q,c)['differences']))
        self.assertFalse(comparison(q,profile('X~N(0,1)，求置信区间'))['eligible'])

    def test_support_and_known_mean_differences_are_visible(self):
        out=comparison(profile('X~U(0,a)，n=4'),profile('X~U(b,2b)，n=3'))
        self.assertTrue(any('支持区间' in d for d in out['differences']))
        self.assertTrue(any('样本量' in d for d in out['differences']))
        out=comparison(profile(r'X~N(\mu,\sigma^2)，均值已知'),profile(r'X~N(\mu,\sigma^2)，均值未知'))
        self.assertTrue(any('均值' in d for d in out['differences']))

    def test_changed_fraction_is_not_normalized_away(self):
        self.assertIn('2/3',profile('X~U(0,a), (2/3)max(X_1,X_2,X_3)')['conditions']['fractions'])
        out=comparison(profile('X~U(0,a), (2/3)max(X_1,X_2,X_3)'),profile('X~U(0,b), (4/3)max(X_1,X_2,X_3)'))
        self.assertTrue(any('分数系数' in d for d in out['differences']))

    def test_general_sample_not_inferred_as_size_three_from_ellipsis(self):
        self.assertNotIn('sample_size',profile(r'X_1,X_2,X_3,\ldots,X_n~U(0,a)')['conditions'])
        self.assertNotIn('maximum',profile(r'X_1,X_2,X_3,\ldots,X_n~U(0,a),X_{(3)}')['operations'])
        self.assertEqual(profile('X~U(0,a),n=4')['conditions']['sample_size'],'4')

    def test_explicit_four_observation_list_is_not_size_three(self):
        self.assertEqual(profile('Z_1,Z_2,Z_3,Z_4~U(0,a)')['conditions']['sample_size'],'4')
        self.assertEqual(profile('Z_i~U(0,a),i=1,2,3,4')['conditions']['sample_size'],'4')

    def test_population_capital_N_is_not_the_sample_size(self):
        self.assertNotIn('sample_size',profile('N=1000,样本来自二项分布')['conditions'])

    def test_generic_formula_retrieval_asks_for_context_without_solving(self):
        p=profile(r'T=\sum a_iY_i')
        self.assertTrue(p['active']);self.assertTrue(describe(p)['missing_context'])
        self.assertNotIn('unbiased',p['operations'])

    def test_arbitrary_algebra_does_not_receive_statistical_matches(self):
        rows={'a':rec('a','X~U(0,1)，求概率')}
        hits,p=candidates('a^2+b^2=c^2',rows)
        self.assertFalse(hits);self.assertFalse(p['active'])

    def test_bare_expectation_and_covariance_retrieve_related_stems(self):
        p=profile('Cov(X,Y)=E[XY]-E[X]E[Y]')
        self.assertTrue(p['active']);self.assertIn('expectation',p['operations']);self.assertIn('covariance',p['operations'])
        self.assertNotIn('variance',profile('求协方差')['operations'])
        rows={'a':rec('a','设随机变量，计算协方差和数学期望'),'b':rec('b','设X~U(0,1)，求分布函数')}
        hits,_=candidates('Cov(X,Y)=E[XY]-E[X]E[Y]',rows)
        self.assertEqual([r['id'] for r in hits],['a'])

    def test_operatorname_variance_and_mathbb_expectation(self):
        p=profile(r'\operatorname{Var}(Z)=\mathbb{E}[Z^2]-(\mathbb{E}[Z])^2')
        self.assertTrue(p['active']);self.assertIn('variance',p['operations']);self.assertIn('expectation',p['operations'])

    def test_scope_and_type_filters_survive_formula_matching(self):
        rows={'a':rec('a','X~U(0,a),求无偏估计'),
              'b':rec('b','Y~U(0,b),求无偏估计',chapter='5'),
              'c':rec('c','Z~U(0,c),求无偏估计',kind='example')}
        hits,_=candidates('T~U(0,k),求无偏估计',rows,kind='exercise',chapter='6')
        self.assertEqual([r['id'] for r in hits],['a'])
        self.assertEqual(hits[0]['formula_match']['status'],'structural_candidate_not_equivalence')

    def test_formula_bypasses_plain_text_scope_rejection_but_calls_no_model(self):
        item=rec('a','X_1,X_2,X_3~U(0,b)，比较max(X_1,X_2,X_3)和min(X_1,X_2,X_3)')
        with patch('full_book_tutor.vectors.search',return_value={'hits':[item],'filtered_records':1}),patch('full_book_tutor.vectors.snapshot',return_value=(None,{'a':item})),patch('full_book_tutor.study_context',return_value={}):
            result=retrieve('Y₁,Y₂,Y₃~U(0,a)，max(Y₁,Y₂,Y₃) 和 min(Y₁,Y₂,Y₃)',kind='exercise')
        self.assertEqual(result['route'],'formula_assisted_fusion')
        self.assertFalse(result['llm_used'])


if __name__=='__main__':unittest.main()
