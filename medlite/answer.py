"""Turn a free-text question into a database-grounded answer (the app's JSON response)."""
import itertools
import os

from .config import DISCLAIMER, Settings
from .db import connect, drug_names
from .llm import OllamaClient, summarize
from .lookup import (facts_text, lookup, missing_pair_line, severity_counts)
from .recognition import AliasIndex, find_drugs

NO_DRUG_FOUND = "No known drug name recognised in your question."
SUGGESTION_NOTE = ("\n\nPossible spelling matches were not checked. "
                   "Confirm a suggestion or enter the medicine name again.")

_index_cache = {}


def cached_alias_index(db, db_path):
    """Reuse the alias index while the database file is unchanged."""
    try:
        stat = os.stat(db_path)
        key = (os.path.abspath(db_path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return AliasIndex.from_db(db)
    if key not in _index_cache:
        _index_cache.clear()
        _index_cache[key] = AliasIndex.from_db(db)
    return _index_cache[key]


def _single_drug_facts(name, counts, records):
    total = sum(counts.values())
    if not total:
        return (f"No interaction records for {name} were found in this database. "
                "This does not establish that the medicine is safe or has no interactions.")
    head = (f"{name} has {total} listed interactions: {counts['major']} major, "
            f"{counts['moderate']} moderate, {counts['minor']} minor, {counts['unknown']} not rated.")
    return (f"{head}\nTop results (most severe first):\n{facts_text(records)}\n\n"
            "To check a specific combination, name your other medicines too.")


def _pair_facts(names, drug_ids, records):
    lines = []
    for first, second in itertools.combinations(drug_ids, 2):
        a, b = names[first], names[second]
        record = next((r for r in records if r.involves(a, b)), None)
        lines.append(facts_text([record]) if record else missing_pair_line(a, b))
    return "\n".join(lines)


def _known_terms(db):
    return dict(db.execute("SELECT a.alias, d.name FROM alias a JOIN drug d ON d.id=a.drug_id"))


def build_answer(db, question, accepted_suggestions=(), settings=None, index=None, llm_client=None):
    settings = settings or Settings()
    index = index or AliasIndex.from_db(db)
    recognition = find_drugs(question, index, accepted_suggestions, fuzzy=settings.fuzzy)
    ids = recognition.drug_ids
    names_by_id = drug_names(db, ids)
    names = [names_by_id[drug_id] for drug_id in ids]

    if not ids:
        response = {"found": [], "facts": NO_DRUG_FOUND}
    else:
        records = lookup(db, ids)
        if len(ids) == 1:
            counts = severity_counts(db, ids[0])
            facts = _single_drug_facts(names[0], counts, records)
        else:
            facts = _pair_facts(names_by_id, ids, records)
        response = {"found": names, "facts": facts,
                    "interaction_records": [record.as_dict() for record in records],
                    "summary": None}
        if len(ids) == 1:
            response["interaction_counts"] = counts
            response["interaction_total"] = sum(counts.values())
        else:
            response["unlisted_pairs"] = [
                {"drug_a": names_by_id[a], "drug_b": names_by_id[b]}
                for a, b in itertools.combinations(ids, 2)
                if not any(r.involves(names_by_id[a], names_by_id[b]) for r in records)]
        # Summaries are only offered when every requested pair has a database record,
        # so the model is never asked to describe a combination the data says nothing about.
        all_pairs_listed = len(ids) > 1 and not response.get("unlisted_pairs")
        if settings.use_llm and all_pairs_listed:
            client = llm_client or OllamaClient(settings.ollama_url, settings.model)
            result = summarize(facts, names, _known_terms(db), client)
            response["summary"] = result.text
            if result.withheld_reason:
                response["summary_withheld"] = result.withheld_reason

    if recognition.suggestions:
        response["facts"] += SUGGESTION_NOTE
    response["corrections"] = [f"{typed} -> {name}" for typed, name in recognition.corrections]
    response["suggestions"] = recognition.suggestions
    response["accepted_suggestions"] = recognition.accepted
    response["database_sources"] = [
        {"name": name, "release": release, "url": url}
        for name, release, url in db.execute(
            "SELECT DISTINCT name, release, source_url FROM data_source ORDER BY name, release")]
    response["disclaimer"] = DISCLAIMER
    if settings.log_queries:
        db.execute("INSERT INTO log(question, found, answer) VALUES(?,?,?)",
                   (question, ", ".join(names), response["facts"]))
        db.commit()
    return response


def answer(question, accepted_suggestions=(), settings=None, llm_client=None):
    """Open the configured database, answer one question and close it."""
    settings = settings or Settings.from_env()
    db = connect(settings.db_path)
    try:
        index = cached_alias_index(db, settings.db_path)
        return build_answer(db, question, accepted_suggestions, settings, index, llm_client)
    finally:
        db.close()
