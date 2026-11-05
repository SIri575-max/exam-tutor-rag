"""Presentation-only formula boundaries from the original OCR; never rewrite math."""
from functools import lru_cache
import json
import re
from process_full_book import BASE
from organize_full_book import formula_segments

FIELDS = {'text', 'question_text', 'full_text', 'snippet', 'quote', 'title'}


@lru_cache(maxsize=2)
def _catalog(stamp):
    pages = {}
    path = BASE / 'normalized-blocks.jsonl'
    with path.open(encoding='utf-8') as source:
        for line in source:
            block = json.loads(line)
            rows = pages.setdefault(block['pdf_page'], {})
            for _, kind, latex in formula_segments(block.get('raw_block', {})):
                if latex.strip():
                    rows[latex] = kind in {'equation', 'equation_interline'}
    return pages


def spans(text, formulas):
    candidates = []
    for latex, display in formulas.items():
        start = 0
        while (at := text.find(latex, start)) >= 0:
            end = at + len(latex)
            # A single variable/number must not split an ordinary word or number.
            if not (re.fullmatch(r'[A-Za-z0-9]+', latex) and
                    ((at and text[at - 1].isascii() and text[at - 1].isalnum()) or
                     (end < len(text) and text[end].isascii() and text[end].isalnum()))):
                candidates.append((at, end, display))
            start = end
    result = []; cursor = 0
    for start, end, display in sorted(candidates, key=lambda row: (row[0], -row[1])):
        if start < cursor:
            continue
        result.append({'start': len(text[:start].encode('utf-16-le')) // 2,
                       'end': len(text[:end].encode('utf-16-le')) // 2,
                       'display': display})
        cursor = end
    return result


def present(value):
    """Add field-level offsets, keeping original strings and retrieval data intact."""
    path = BASE / 'normalized-blocks.jsonl'
    if not path.exists():
        return value
    catalog = _catalog(path.stat().st_mtime_ns)

    def walk(item, inherited=()):
        if isinstance(item, list):
            return [walk(child, inherited) for child in item]
        if not isinstance(item, dict):
            return item
        pages = item.get('pages') or ([item['pdf_page']] if item.get('pdf_page') else inherited)
        if not pages and item.get('citations'):
            pages = [c.get('pdf_page') for c in item['citations'] if isinstance(c, dict)]
        formulas = {}
        for page in pages:
            if isinstance(page, int):
                formulas.update(catalog.get(page, {}))
        result = {key: walk(child, pages) for key, child in item.items()}
        metadata = {key: spans(text, formulas) for key, text in item.items()
                    if key in FIELDS and isinstance(text, str) and formulas}
        metadata = {key: offsets for key, offsets in metadata.items() if offsets}
        if metadata:
            result['_math'] = metadata
        return result
    return walk(value)
