"""Compose humanize prompts from SO style profiles."""

from __future__ import annotations

import json
from pathlib import Path

from stackoverflow.paths import INDEX_PATH, STYLES


def list_profiles() -> list[dict]:
    if not INDEX_PATH.is_file():
        return []
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return data.get("users") or []


def load_profile(user_id: int | str) -> dict | None:
    path = STYLES / f"{int(user_id)}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compose_with_style(base_prompt: str, user_id: int | str | None) -> str:
    if user_id is None or str(user_id).strip() in ("", "0", "none"):
        return base_prompt.strip()
    profile = load_profile(user_id)
    if not profile:
        return base_prompt.strip()

    rules = profile.get("style_rules") or []
    exemplars = profile.get("exemplars") or []
    features = profile.get("features") or {}

    block = [
        base_prompt.strip(),
        "",
        "--- Stack Overflow style profile (SO-inspired; do not impersonate) ---",
        f"Profile user_id: {profile.get('user_id')} (public posts; CC BY-SA).",
        "Style rules:",
        *[f"- {r}" for r in rules],
        "",
        f"Stats hint: avg ~{features.get('avg_words_per_sentence', '?')} words/sentence, "
        f"code in ~{int(float(features.get('code_answer_rate', 0)) * 100)}% of answers.",
    ]
    if exemplars:
        block.append("")
        block.append("Tone examples (match voice, do NOT copy sentences):")
        for i, ex in enumerate(exemplars[:3], 1):
            block.append(f"Example {i}: {ex[:500]}{'…' if len(ex) > 500 else ''}")

    return "\n".join(block).strip()
