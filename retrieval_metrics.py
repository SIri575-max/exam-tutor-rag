"""Question-ID metrics with explicit unjudged handling; no LLM judge."""


def evaluate(predicted, grades, k, relevant_grade=2, positive_set_complete=False):
    """Grades 0..3; null/unlisted IDs are unjudged. P@K uses K slots.

    Recall is withheld unless the caller explicitly declares the positive set
    complete. Annotated-set coverage is separately named for pooled labels.
    Unknown earlier candidates prevent an exact MRR, rather than becoming zero.
    """
    if type(k) is not int or k<1:raise ValueError('K must be a positive integer')
    if type(positive_set_complete) is not bool:raise ValueError('Completeness must be explicit')
    if type(relevant_grade) is not int or relevant_grade not in [1,2,3]:raise ValueError('Invalid relevance threshold')
    if any(v is not None and (type(v) is not int or v not in range(4)) for v in grades.values()):
        raise ValueError('Grades must be null or integers 0..3')
    if len(set(predicted))!=len(predicted):raise ValueError('Deduplicate parent question IDs before scoring')
    top=predicted[:k];positive={i for i,g in grades.items() if g is not None and g>=relevant_grade}
    known=[i for i in top if grades.get(i) is not None]
    found=[i for i in top if i in positive]
    missing=[i for i in top if grades.get(i) is None]
    first=next((j+1 for j,i in enumerate(top) if i in positive),None)
    unknown_before=any(grades.get(i) is None for i in (top[:first-1] if first else top))
    # Completeness declares that unlisted IDs are negative, but explicit null
    # remains unjudged: a partially filled review cannot silently become labels.
    if positive_set_complete:
        known=[i for i in top if i not in grades or grades[i] is not None]
        missing=[i for i in top if i in grades and grades[i] is None]
        unknown_before=any(i in grades and grades[i] is None for i in (top[:first-1] if first else top))
    return {'k':k,'returned_count':len(top),'judged_returned_count':len(known),
            'hit_at_k':1. if found else None if missing else 0.,
            'precision_at_k':len(found)/k if not missing else None,
            'recall_at_k':len(found)/len(positive) if positive_set_complete and positive and not missing and all(g is not None for g in grades.values()) else None,
            'annotated_positive_coverage_at_k':len(found)/len(positive) if positive else None,
            'reciprocal_rank_at_k':None if unknown_before else 1/first if first else 0.,
            'positive_set_complete':positive_set_complete,'relevance_threshold':relevant_grade,
            'unjudged_ids':missing}
