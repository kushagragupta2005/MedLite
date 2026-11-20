"""Optional plain-language summary from a small local model, behind an output guardrail.

The model only rewrites facts already retrieved from the database. Its output is
shown only if it passes ``check_summary``; otherwise the caller shows the database
facts alone. The model never decides what is looked up or what severity applies.
"""
import json
import re
import urllib.request
from dataclasses import dataclass

MAX_FACT_LINES = 8          # keep the prompt short for a tiny model
MAX_SENTENCES = 3
MAX_TOKENS = 100            # hard cap: no runaway output
SEVERITY_WORDS = ("major", "moderate", "minor")

PROMPT = ("Rewrite these drug-interaction facts as at most 3 short, simple sentences for a patient. "
          "Use ONLY the facts given. Do not add anything. Stop after 3 sentences.\n\n")


@dataclass(frozen=True)
class SummaryResult:
    text: str = None          # summary safe to display, or None
    withheld_reason: str = None


class OllamaClient:
    def __init__(self, url, model, timeout=30):
        self.url, self.model, self.timeout = url, model, timeout

    def generate(self, prompt):
        body = {"model": self.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0, "num_predict": MAX_TOKENS, "repeat_penalty": 1.15}}
        request = urllib.request.Request(self.url, method="POST", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)["response"].strip()


def _sentences(text):
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]


def _mentions(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def check_summary(summary, facts, allowed_drugs, known_terms):
    """Return a reason to withhold ``summary``, or None if it passes.

    ``known_terms`` maps every database name/alias to its normalized drug name.

    * It must be non-empty and at most ``MAX_SENTENCES`` sentences.
    * It must not name (by generic or brand name) a drug other than the recognised ones.
    * It must not use a severity word that does not appear in the facts.
    """
    text = (summary or "").strip().lower()
    if not text:
        return "empty model output"
    if len(_sentences(text)) > MAX_SENTENCES:
        return "model output exceeded the sentence limit"
    allowed = {name.lower() for name in allowed_drugs}
    for term, drug in known_terms.items():
        term, drug = term.lower(), drug.lower()
        if drug in allowed or len(term) < 4:
            continue
        # A term that is a whole word/phrase inside an allowed name is not a different drug
        # ("amphotericin b" inside "amphotericin b (liposomal)").
        if any(_mentions(name, term) for name in allowed):
            continue
        if _mentions(text, term):
            return f"model output named a medicine that was not checked ({term})"
    fact_text = facts.lower()
    for word in SEVERITY_WORDS:
        if _mentions(text, word) and not _mentions(fact_text, word):
            return f"model output used a severity ('{word}') that is not in the database facts"
    return None


def summarize(facts, allowed_drugs, known_terms, client):
    facts = "\n".join(facts.splitlines()[:MAX_FACT_LINES])
    try:
        summary = client.generate(PROMPT + facts)
    except Exception as error:  # network, timeout, malformed reply: never block the database answer
        return SummaryResult(withheld_reason=f"model unavailable ({error.__class__.__name__}); "
                                             "is `ollama serve` running?")
    reason = check_summary(summary, facts, allowed_drugs, known_terms)
    if reason:
        return SummaryResult(withheld_reason=reason)
    return SummaryResult(text=summary)
