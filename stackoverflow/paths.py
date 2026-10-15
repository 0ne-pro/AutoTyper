"""Data directories for Stack Overflow style pipeline."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "so"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
STYLES = DATA / "styles"
INDEX_PATH = STYLES / "index.json"
USERS_CSV = DATA / "users.csv"


def ensure_dirs() -> None:
    for p in (DATA, RAW, PROCESSED, STYLES):
        p.mkdir(parents=True, exist_ok=True)
