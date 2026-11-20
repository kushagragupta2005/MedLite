"""Read-only interaction queries and the plain-text facts they produce."""
import itertools
from dataclasses import dataclass

from .db import SEV_ORDER_SQL, SEVERITIES, SEVERITY_RANK

_SELECT = """SELECT d1.name, d2.name, i.severity, i.note,
                    ds.name, ds.release, ds.source_file, ds.source_url, i.source_record_id
             FROM interaction i
             JOIN drug d1 ON d1.id=i.a JOIN drug d2 ON d2.id=i.b
             LEFT JOIN data_source ds ON ds.id=i.source_id"""

SINGLE_DRUG_LIMIT = 5


@dataclass(frozen=True)
class InteractionRecord:
    drug_a: str
    drug_b: str
    severity: str
    note: str
    source_name: str
    source_release: str
    source_file: str
    source_url: str
    source_record_id: str

    def as_dict(self):
        return dict(self.__dict__)

    def involves(self, first, second):
        return {self.drug_a, self.drug_b} == {first, second}


def pair_records(db, drug_ids):
    """One record per listed pair among ``drug_ids``, most severe first."""
    records = []
    for first, second in itertools.combinations(dict.fromkeys(drug_ids), 2):
        row = db.execute(_SELECT + " WHERE i.a=? AND i.b=?", (min(first, second), max(first, second))).fetchone()
        if row:
            records.append(InteractionRecord(*row))
    records.sort(key=lambda record: SEVERITY_RANK.get(record.severity, len(SEVERITIES)))
    return records


def single_drug_records(db, drug_id, limit=SINGLE_DRUG_LIMIT):
    rows = db.execute(_SELECT + f" WHERE i.a=? OR i.b=? ORDER BY {SEV_ORDER_SQL} LIMIT ?",
                      (drug_id, drug_id, limit))
    return [InteractionRecord(*row) for row in rows]


def lookup(db, drug_ids):
    """Pair records for 2+ drugs; the most severe few records for a single drug."""
    drug_ids = list(dict.fromkeys(drug_ids))
    if len(drug_ids) >= 2:
        return pair_records(db, drug_ids)
    if drug_ids:
        return single_drug_records(db, drug_ids[0])
    return []


def severity_counts(db, drug_id):
    counts = dict(db.execute("SELECT severity, COUNT(*) FROM interaction WHERE a=? OR b=? GROUP BY severity",
                             (drug_id, drug_id)).fetchall())
    return {severity: counts.get(severity, 0) for severity in SEVERITIES}


def _label(severity):
    return "LISTED, SEVERITY NOT RATED" if severity == "unknown" else severity.upper()


def fact_line(record):
    line = f"- {record.drug_a} + {record.drug_b}: {_label(record.severity)}. {record.note or ''}".rstrip()
    if record.source_name:
        ref = f"{record.source_name} {record.source_release} ({record.source_file})"
        if record.source_record_id:
            ref += f", record {record.source_record_id}"
        if record.source_url:
            ref += f" — {record.source_url}"
        return line + f" Source: {ref}."
    return line + " Source: legacy record; import provenance was not recorded."


def facts_text(records):
    return "\n".join(fact_line(record) for record in records)


def missing_pair_line(first, second):
    return (f"- {first} + {second}: No matching interaction record in this database. "
            "This does not establish that the combination is safe.")
