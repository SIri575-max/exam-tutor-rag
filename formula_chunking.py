"""Conservative TeX-aware boundaries; not a TeX parser or mathematical validator."""
import re


def escaped(text, offset):
    count = 0
    while offset and text[offset-1] == '\\':
        count += 1
        offset -= 1
    return bool(count % 2)


def protected_spans(text):
    spans = [(m.start(), m.end()) for m in re.finditer(r'\\[A-Za-z]+', text)]
    # Keep multi-digit numbers and decimal/scientific literals intact as well.
    spans += [(m.start(), m.end()) for m in re.finditer(r'\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', text)]
    braces = []; environments = []; dollars = None; delimiters = {}
    for m in re.finditer(r'\\begin\{([^}]+)\}|\\end\{([^}]+)\}|\\[\[\]()]|\$\$?|[{}]', text):
        start, end = m.span(); token = m[0]
        if escaped(text, start):
            continue
        if m[1]:
            environments.append((m[1], start))
        elif m[2]:
            if environments and environments[-1][0] == m[2]:
                _, opening = environments.pop(); spans.append((opening, end))
        elif token in (r'\[', r'\('):
            delimiters[token] = start
        elif token in (r'\]', r'\)'):
            opening = delimiters.pop(r'\[' if token == r'\]' else r'\(', None)
            if opening is not None:
                spans.append((opening, end))
        elif token.startswith('$'):
            if dollars is None:
                dollars = (token, start)
            elif dollars[0] == token:
                spans.append((dollars[1], end)); dollars = None
        elif token == '{':
            braces.append(start)
        elif token == '}' and braces:
            spans.append((braces.pop(), end))
    # Incomplete OCR markup is conservatively protected up to the record end.
    spans += [(start, len(text)) for _, start in environments]
    spans += [(start, len(text)) for start in braces]
    spans += [(start, len(text)) for start in delimiters.values()]
    if dollars is not None:
        spans.append((dollars[1], len(text)))
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def intervals(text, prefix, count_tokens, character_target=320, overlap=64, token_budget=480):
    """Cover all text; protect units when feasible, flag forced hard-budget cuts."""
    spans = protected_spans(text)
    forbidden = {i for a, b in spans for i in range(a+1, b)}
    start = 0; covered_until = 0
    while start < len(text):
        target = min(len(text), start + character_target)
        safe = [i for i in range(start+1, target+1) if i not in forbidden]
        # Prefer a substantial paragraph/sentence, otherwise the last safe cut.
        sentence = [i for i in safe if i-start >= character_target//2
                    and text[i-1] in '\n。；！？;!?']
        # Do not split a short question merely because it has punctuation.
        whole_fits = len(text)-start <= character_target and count_tokens(prefix+text[start:]) <= token_budget
        preferred = ([len(text)] if whole_fits else []) + list(reversed(sentence)) + list(reversed(safe))
        end = next((i for i in preferred if count_tokens(prefix+text[start:i]) <= token_budget), None)
        tail_merged = False
        if end is not None and end-start < character_target//2:
            following = next((b for a,b in spans if a == end),None)
            if following is not None and count_tokens(prefix+text[start:following]) <= token_budget:
                end=following
        if end is None:
            # A long atomic formula may exceed the soft character target but fit
            # the hard model budget. Keep it whole rather than truncate it.
            extended = [b for a, b in spans if a <= start < b and b > target]
            if extended and count_tokens(prefix+text[start:extended[0]]) <= token_budget:
                end = extended[0]
        forced = end is None
        if forced:
            end = target
            while count_tokens(prefix+text[start:end]) > token_budget:
                if end-start < 2:
                    raise ValueError('Cannot fit chunk token budget')
                end = start+(end-start)//2
        if end <= covered_until:
            start=covered_until
            continue
        if 0 < len(text)-end < overlap and count_tokens(prefix+text[start:]) <= token_budget:
            end=len(text);tail_merged=True
        flags = []
        if start in forbidden or end in forbidden:
            flags.append('protected_unit_split_for_token_budget')
        if end-start > character_target:
            flags.append('short_tail_merged_exceeds_character_target' if tail_merged else 'atomic_unit_exceeds_character_target')
        yield start, end, flags
        covered_until=end
        if end == len(text):
            break
        desired = max(start+1, end-min(overlap, (end-start)//4))
        next_safe = next((i for i in range(desired, end+1) if i not in forbidden), None)
        # A forced cut inside a long atomic unit can have no safe overlap start.
        start = next_safe if next_safe is not None else end
