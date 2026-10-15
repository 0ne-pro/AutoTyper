"""Fetch users and answers from Stack Overflow."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable

from stackoverflow.api import StackExchangeClient
from stackoverflow.paths import RAW, USERS_CSV, ensure_dirs


def load_user_ids_from_file(path: Path) -> list[int]:
    ids: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ids.append(int(line.split()[0]))
    return ids


def fetch_top_answerers(
    client: StackExchangeClient,
    tag: str = "python",
    count: int = 100,
) -> list[dict]:
    data = client.get(
        f"/tags/{tag}/top-answerers/all_time",
        pagesize=min(count, 100),
    )
    users: list[dict] = []
    for item in data.get("items") or []:
        user = item.get("user") or {}
        uid = user.get("user_id")
        if uid is None:
            continue
        users.append(
            {
                "user_id": int(uid),
                "display_name": user.get("display_name") or f"user_{uid}",
                "reputation": user.get("reputation"),
                "post_count_tag": item.get("post_count"),
            }
        )
    return users[:count]


def fetch_user_answers(
    client: StackExchangeClient,
    user_id: int,
    max_answers: int = 100,
) -> list[dict]:
    collected: list[dict] = []
    page = 1
    while len(collected) < max_answers:
        data = client.get(
            f"/users/{user_id}/answers",
            order="desc",
            sort="creation",
            pagesize=min(100, max_answers - len(collected)),
            page=page,
            filter="withbody",
        )
        items = data.get("items") or []
        if not items:
            break
        for it in items:
            collected.append(
                {
                    "answer_id": it.get("answer_id"),
                    "question_id": it.get("question_id"),
                    "score": it.get("score", 0),
                    "creation_date": it.get("creation_date"),
                    "body_html": it.get("body") or "",
                }
            )
        if not data.get("has_more"):
            break
        page += 1
    return collected[:max_answers]


def run_fetch(
    *,
    user_ids: list[int] | None = None,
    tag: str = "python",
    user_count: int = 100,
    max_answers_per_user: int = 80,
    log: Callable[[str], None] | None = None,
) -> None:
    ensure_dirs()
    client = StackExchangeClient()

    def _log(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    if user_ids:
        users = [
            {"user_id": uid, "display_name": f"user_{uid}", "reputation": None, "post_count_tag": None}
            for uid in user_ids
        ]
    else:
        _log(f"Fetching top {user_count} '{tag}' answerers…")
        users = fetch_top_answerers(client, tag=tag, count=user_count)

    with USERS_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["user_id", "display_name", "reputation", "post_count_tag"],
        )
        w.writeheader()
        for u in users:
            w.writerow(u)

    for i, u in enumerate(users, 1):
        uid = u["user_id"]
        folder = RAW / str(uid)
        folder.mkdir(parents=True, exist_ok=True)
        out_path = folder / "answers.jsonl"
        if out_path.exists() and out_path.stat().st_size > 0:
            _log(f"[{i}/{len(users)}] skip user {uid} (cached)")
            continue
        _log(f"[{i}/{len(users)}] user {uid} ({u.get('display_name')})…")
        answers = fetch_user_answers(client, uid, max_answers=max_answers_per_user)
        with out_path.open("w", encoding="utf-8") as af:
            for row in answers:
                af.write(json.dumps(row, ensure_ascii=False) + "\n")
        _log(f"    saved {len(answers)} answers")
