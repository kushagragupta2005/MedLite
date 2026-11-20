"""MedLite: offline drug-interaction lookup where the database, not the model, is the source of truth.

Information tool only - not medical advice.
"""
from .answer import answer, build_answer
from .config import Settings
from .db import connect
from .recognition import AliasIndex, find_drugs, recognize

__all__ = ["AliasIndex", "Settings", "answer", "build_answer", "connect", "find_drugs", "recognize"]
__version__ = "0.2.0"
