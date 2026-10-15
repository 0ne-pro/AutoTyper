"""Clean and filter raw answers."""

from __future__ import annotations

import json
import re
from pathlib import Path

from stackoverflow.html_clean import html_to_text
from stackoverflow.paths import PROCESSED, RAW, USERS_CSV, ensure_dirs

MIN_SCORE = 1
MIN_CHARS = 80
MAX_CHARS = 6000
MIN_ANSWERS_KEPT = 10


def _looks_english(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    if letters < 40:
        return True
    ascii_letters = sum(c.isascii() and c.isalpha() for c in text)
    return ascii_letters / max(letters, 1) > 0.85


def clean_answer(body_html: str) -> str:
    text = html_to_text(body_html)
    text = re.sub(r"https?://\S+", "", text)
    return text.strip()


def run_prepare() -> dict[str, int]:
    ensure_dirs()
    stats = {"users_ok": 0, "users_skipped": 0, "answers_kept": 0}

    if not USERS_CSV.is_file():
        raise RuntimeError("Missing users.csv — run fetch first.")

    import csv

    with USERS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        user_ids = [int(row["user_id"]) for row in reader]

    for uid in user_ids:
        raw_path = RAW / str(uid) / "answers.jsonl"
        if not raw_path.is_file():
            stats["users_skipped"] += 1
            continue
        kept: list[dict] = []
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            score = int(row.get("score") or 0)
            if score < MIN_SCORE:
                continue
            text = clean_answer(row.get("body_html") or "")
            if len(text) < MIN_CHARS or len(text) > MAX_CHARS:
                continue
            if not _looks_english(text):
                continue
            kept.append(
                {
                    "answer_id": row.get("answer_id"),
                    "score": score,
                    "text": text,
                    "has_code": "```" in text or "`" in text,
                }
            )
        out_dir = PROCESSED / str(uid)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "answers_clean.jsonl"
        with out_file.open("w", encoding="utf-8") as wf:
            for item in kept:
                wf.write(json.dumps(item, ensure_ascii=False) + "\n")
        if len(kept) >= MIN_ANSWERS_KEPT:
            stats["users_ok"] += 1
            stats["answers_kept"] += len(kept)
        else:
            stats["users_skipped"] += 1

    return stats
