"""The one drug-name matcher used by the app, the CLI and the benchmark.

Aliases and input text are tokenized the same way (lowercase ``[a-z0-9]+``),
so names with punctuation such as ``"amphotericin b (liposomal)"`` or
``"anti-inhibitor coagulant complex"`` match however they are typed. Matching
is greedy left-to-right longest-match with no fixed n-gram cap.

Spelling tolerance never silently changes what is looked up: ``fuzzy_candidates``
only proposes names. The app asks the user to confirm one; the benchmark's
``top1_confirmed`` mode simulates that confirmation by taking the best one.
"""
import difflib
import re
from dataclasses import dataclass, field

TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

FUZZY_THRESHOLD = 0.84
FUZZY_MIN_WORD_LENGTH = 6     # shorter typed words are never fuzzily matched
FUZZY_MIN_ALIAS_LENGTH = 5
FUZZY_LENGTH_SLACK = 2
MAX_SUGGESTIONS = 3


def tokenize(text):
    """Return ``(lowercase_word, start, end)`` for every token in ``text``."""
    return [(match.group(0).lower(), match.start(), match.end()) for match in TOKEN.finditer(text)]


@dataclass(frozen=True)
class Candidate:
    drug_id: int
    name: str
    alias: str
    score: float


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    surface: str
    drug_id: int
    normalized: str
    fuzzy: bool = False

    def as_benchmark_dict(self):
        return {"start": self.start, "end": self.end, "surface": self.surface, "normalized": self.normalized}


@dataclass
class AliasIndex:
    exact: dict                                  # tuple(tokens) -> (drug_id, normalized name)
    by_first_letter_and_length: dict = field(default_factory=dict)
    max_tokens: int = 0

    @classmethod
    def from_rows(cls, rows):
        """Build from ``(alias, drug_id, drug_name)`` rows. The first alias wins on a token collision."""
        exact, fuzzy = {}, {}
        for alias, drug_id, name in rows:
            parts = tuple(word for word, _, _ in tokenize(alias))
            if not parts or parts in exact:
                continue
            exact[parts] = (drug_id, name)
            if len(parts) == 1 and parts[0].isalpha() and len(parts[0]) >= FUZZY_MIN_ALIAS_LENGTH:
                fuzzy.setdefault((parts[0][0], len(parts[0])), []).append((parts[0], drug_id, name))
        return cls(exact=exact, by_first_letter_and_length=fuzzy,
                   max_tokens=max((len(parts) for parts in exact), default=0))

    @classmethod
    def from_db(cls, db):
        rows = db.execute("""SELECT a.alias, a.drug_id, d.name FROM alias a
                             JOIN drug d ON d.id = a.drug_id ORDER BY a.alias""")
        return cls.from_rows(rows)


def fuzzy_candidates(word, index, threshold=FUZZY_THRESHOLD, exclude_ids=()):
    """Best-scoring alias per drug for a possibly misspelled single word, best first."""
    word = word.lower()
    if not word.isalpha() or len(word) < FUZZY_MIN_WORD_LENGTH:
        return []
    best = {}
    low = max(FUZZY_MIN_ALIAS_LENGTH, len(word) - FUZZY_LENGTH_SLACK)
    for length in range(low, len(word) + FUZZY_LENGTH_SLACK + 1):
        for alias, drug_id, name in index.by_first_letter_and_length.get((word[0], length), ()):
            if drug_id in exclude_ids:
                continue
            score = difflib.SequenceMatcher(None, word, alias).ratio()
            if score < threshold:
                continue
            current = best.get(drug_id)
            if current is None or (-score, alias) < (-current.score, current.alias):
                best[drug_id] = Candidate(drug_id, name, alias, round(score, 3))
    return sorted(best.values(), key=lambda c: (-c.score, c.name, c.alias))


def recognize(text, index, top1_fuzzy=False, threshold=FUZZY_THRESHOLD):
    """Find drug mentions with character spans.

    With ``top1_fuzzy`` an unmatched word takes its best fuzzy candidate. That
    models a user confirming the first suggestion; it is a benchmark setting,
    not something the app does on its own.
    """
    tokens = tokenize(text)
    words = [word for word, _, _ in tokens]
    mentions, position = [], 0
    while position < len(tokens):
        match = None
        for length in range(min(index.max_tokens, len(tokens) - position), 0, -1):
            entry = index.exact.get(tuple(words[position:position + length]))
            if entry:
                match = (length, entry[0], entry[1], False)
                break
        if match is None and top1_fuzzy:
            candidates = fuzzy_candidates(words[position], index, threshold)
            if candidates:
                match = (1, candidates[0].drug_id, candidates[0].name, True)
        if match is None:
            position += 1
            continue
        length, drug_id, name, was_fuzzy = match
        start, end = tokens[position][1], tokens[position + length - 1][2]
        mentions.append(Mention(start, end, text[start:end], drug_id, name, was_fuzzy))
        position += length
    return mentions


@dataclass
class Recognition:
    drug_ids: list            # unique, in order of first appearance
    corrections: list         # (typed word, confirmed name) pairs applied this request
    suggestions: list         # [{"input", "options": [{drug_id, name, alias, score}]}] awaiting confirmation
    accepted: list            # confirmations that were used, echoed back to the client


def _parse_confirmations(accepted_suggestions):
    confirmed = set()
    for value in accepted_suggestions or ():
        if not isinstance(value, dict):
            continue
        try:
            confirmed.add((str(value["input"]).lower(), int(value["drug_id"])))
        except (KeyError, TypeError, ValueError):
            continue
    return confirmed


def find_drugs(text, index, accepted_suggestions=(), fuzzy=True):
    """App-facing recognition: exact matches plus confirm-before-use spelling suggestions."""
    exact = recognize(text, index)
    found = list(dict.fromkeys(mention.drug_id for mention in exact))
    covered = set()
    for mention in exact:
        covered.update(range(mention.start, mention.end))
    result = Recognition(found, [], [], [])
    if not fuzzy:
        return result
    confirmed = _parse_confirmations(accepted_suggestions)
    for word, start, _ in tokenize(text):
        if start in covered:
            continue
        options = fuzzy_candidates(word, index, exclude_ids=set(result.drug_ids))[:MAX_SUGGESTIONS]
        if not options:
            continue
        chosen = next((option for option in options if (word, option.drug_id) in confirmed), None)
        if chosen:
            result.drug_ids.append(chosen.drug_id)
            result.corrections.append((word, chosen.name))
            result.accepted.append({"input": word, "drug_id": chosen.drug_id})
        else:
            result.suggestions.append({"input": word, "options": [
                {"drug_id": o.drug_id, "name": o.name, "alias": o.alias, "score": o.score} for o in options]})
    return result
