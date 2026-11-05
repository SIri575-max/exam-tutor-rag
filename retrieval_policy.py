"""Explicit stage budgets, distinct from relevance labels and score thresholds."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RetrievalBudget:
    recall_k: int = 20
    typed_lexical_k: int = 20
    formula_k: int = 20
    math_k: int = 12
    practice_k: int = 3
    context_main_k: int = 3
    context_per_kind_k: int = 2

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or not 1 <= value <= 20:
                raise ValueError('Stage budgets must be integers from 1 to 20: '+key)
        if self.practice_k > 5:
            raise ValueError('At most five study recommendations per kind')

    def describe(self, detailed_k=8):
        return {**asdict(self), 'detailed_k': max(1, min(int(detailed_k), 20)),
                'recall_unit': 'unique_parent_question_after_full_exact_scoring_and_rank_fusion',
                'candidate_union_can_exceed_recall_k': True,
                'reranking': 'rule_and_rank_fusion_not_neural_cross_encoder'}


DEFAULT_BUDGET = RetrievalBudget()
EVIDENCE_MAX_UNITS = 8
EVIDENCE_MAX_CHARACTERS = 18000
