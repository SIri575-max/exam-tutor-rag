"""Tiny textbook-free example of retrieval and evaluation."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrieval import bm25
from retrieval_metrics import evaluate


def main():
    query = '正态总体均值的置信区间，方差未知'
    questions = {
        'example-1': '正态总体方差未知时，构造均值的置信区间。',
        'exercise-1': '正态总体方差未知，给定样本统计量，求均值的置信区间。',
        'exercise-2': '对于二项分布，计算恰好两次成功的概率。',
    }
    scores = bm25(query, list(questions.values()))
    ranked = sorted(zip(questions, scores), key=lambda row: -row[1])
    predicted = [identifier for identifier, _ in ranked]
    grades = {'example-1': 3, 'exercise-1': 2, 'exercise-2': 0}
    result = evaluate(predicted, grades, k=2, positive_set_complete=True)
    print(json.dumps({'query': query, 'results': ranked, 'metrics': result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
