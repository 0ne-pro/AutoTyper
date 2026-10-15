"""Build per-user style cards from cleaned answers."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from stackoverflow.paths import INDEX_PATH, PROCESSED, STYLES, USERS_CSV, ensure_dirs

HEDGES = (
    "probably",
    "usually",
    "i think",
    "might",
    "often",
    "generally",
    "typically",
    "perhaps",
)
STARTERS = ("you can", "try", "use", "the issue", "this happens", "note that", "simply")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def analyze_answers(rows: list[dict]) -> dict:
    lengths: list[int] = []
    sents_per: list[int] = []
    hedge_hits = 0
    starter_hits = 0
    code_flags = 0
    word_total = 0
    vocab: dict[str, int] = {}

    for row in rows:
        text = row["text"]
        sents = _sentences(text)
        sents_per.append(len(sents))
        lengths.append(len(text))
        tl = text.lower()
        if any(h in tl for h in HEDGES):
            hedge_hits += 1
        if any(tl.startswith(s) for s in STARTERS):
            starter_hits += 1
        if row.get("has_code"):
            code_flags += 1
        ws = _words(text)
        word_total += len(ws)
        for w in ws:
            if len(w) > 3:
                vocab[w] = vocab.get(w, 0) + 1

    avg_sent_len = 0.0
    if word_total and sents_per:
        avg_sent_len = word_total / max(sum(sents_per), 1)

    top_words = sorted(vocab.items(), key=lambda x: -x[1])[:15]

    return {
        "n_answers": len(rows),
        "avg_chars": round(statistics.mean(lengths), 1) if lengths else 0,
        "avg_sentences": round(statistics.mean(sents_per), 2) if sents_per else 0,
        "avg_words_per_sentence": round(avg_sent_len, 2),
        "hedge_rate": round(hedge_hits / max(len(rows), 1), 3),
        "direct_opener_rate": round(starter_hits / max(len(rows), 1), 3),
        "code_answer_rate": round(code_flags / max(len(rows), 1), 3),
        "top_words": [w for w, _ in top_words],
    }


def _pick_exemplars(rows: list[dict], n: int = 3) -> list[str]:
    if not rows:
        return []
    by_score = sorted(rows, key=lambda r: r.get("score", 0), reverse=True)
    top = by_score[: max(1, n // 2)]
    mid_target = statistics.median([len(r["text"]) for r in rows])
    rest = sorted(rows, key=lambda r: abs(len(r["text"]) - mid_target))
    picks: list[dict] = []
    seen: set[str] = set()
    for r in top + rest:
        aid = str(r.get("answer_id", id(r)))
        if aid in seen:
            continue
        seen.add(aid)
        picks.append(r)
        if len(picks) >= n:
            break
    out: list[str] = []
    for r in picks:
        t = r["text"]
        if len(t) > 700:
            t = t[:700] + "…"
        out.append(t)
    return out


def _style_rules(features: dict) -> list[str]:
    rules = [
        "Write like a helpful Stack Overflow answer: direct, practical, and respectful.",
        "Do not mention Stack Overflow or that you are mimicking someone.",
        "Do not copy phrases verbatim from examples; match rhythm and structure only.",
        "Follow the global prose rules in the base prompt (130-char sentences, no semicolons/em-dashes, contractions, lumpy rhythm).",
    ]
    if features.get("code_answer_rate", 0) > 0.35:
        rules.append("Use short code or `inline code` when it clarifies the fix.")
    if features.get("avg_words_per_sentence", 0) < 14:
        rules.append("Prefer short sentences and get to the point quickly.")
    else:
        rules.append("Use mixed sentence length; explain the why briefly when useful.")
    if features.get("direct_opener_rate", 0) > 0.2:
        rules.append("Open with actionable guidance (You can…, Try…, Use…).")
    return rules


def run_profile() -> dict[str, int]:
    ensure_dirs()
    import csv

    index_users: list[dict] = []
    stats = {"profiles": 0}

    with USERS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        users = list(reader)

    for row in users:
        uid = int(row["user_id"])
        path = PROCESSED / str(uid) / "answers_clean.jsonl"
        if not path.is_file():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(rows) < 10:
            continue
        features = analyze_answers(rows)
        exemplars = _pick_exemplars(rows)
        rules = _style_rules(features)
        card = {
            "user_id": uid,
            "display_name": row.get("display_name") or f"user_{uid}",
            "attribution": "Style derived from public Stack Overflow posts (CC BY-SA).",
            "features": features,
            "style_rules": rules,
            "exemplars": exemplars,
        }
        out = STYLES / f"{uid}.json"
        out.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
        label = f"SO #{uid} ({features['n_answers']} answers, ~{int(features['avg_chars'])} chars)"
        index_users.append({"user_id": uid, "label": label, "file": out.name})
        stats["profiles"] += 1

    index_users.sort(key=lambda x: x["user_id"])
    INDEX_PATH.write_text(
        json.dumps({"count": len(index_users), "users": index_users}, indent=2),
        encoding="utf-8",
    )
    return stats
