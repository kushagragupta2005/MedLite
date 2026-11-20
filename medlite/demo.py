"""Small built-in demo dataset so the app runs without the licensed DDInter files."""
from .db import add_drug, add_interaction, register_source

DEMO_DRUGS = {
    "warfarin": ["coumadin"], "ibuprofen": ["brufen", "advil", "motrin"],
    "aspirin": ["ecosprin", "disprin"], "paracetamol": ["acetaminophen", "crocin", "dolo", "tylenol"],
    "lisinopril": [], "simvastatin": ["zocor"], "clarithromycin": [], "sildenafil": ["viagra"],
    "nitroglycerin": ["glyceryl trinitrate", "gtn"], "fluoxetine": ["prozac"], "tramadol": [],
    "clopidogrel": ["plavix"], "omeprazole": ["prilosec"], "metformin": ["glycomet"],
    "digoxin": [], "amiodarone": [],
}

DEMO_INTERACTIONS = [
    ("warfarin", "ibuprofen", "major", "Higher risk of serious bleeding, especially stomach bleeding."),
    ("warfarin", "aspirin", "major", "Higher risk of bleeding."),
    ("warfarin", "paracetamol", "moderate", "Regular use may raise INR and bleeding risk."),
    ("ibuprofen", "aspirin", "moderate", "Ibuprofen may weaken low-dose aspirin's heart protection; more stomach irritation."),
    ("lisinopril", "ibuprofen", "moderate", "NSAIDs can reduce blood-pressure control and strain the kidneys."),
    ("simvastatin", "clarithromycin", "major", "Raises simvastatin levels; risk of severe muscle damage."),
    ("sildenafil", "nitroglycerin", "major", "Can cause a dangerous drop in blood pressure. Do not combine."),
    ("fluoxetine", "tramadol", "major", "Risk of serotonin syndrome and seizures."),
    ("clopidogrel", "omeprazole", "moderate", "Omeprazole can reduce clopidogrel's effect."),
    ("digoxin", "amiodarone", "major", "Raises digoxin levels; risk of toxicity."),
]


def load_demo(db):
    """Insert the demo records (idempotent) and commit."""
    source_id = register_source(db, "MedLite demo", "synthetic-demo-v1", "built-in", "not-applicable",
                                license_note="Synthetic demonstration records; do not use clinically.")
    ids = {name: add_drug(db, name, aliases) for name, aliases in DEMO_DRUGS.items()}
    for first, second, severity, note in DEMO_INTERACTIONS:
        add_interaction(db, ids[first], ids[second], severity, note, source_id, "demo")
    db.commit()
