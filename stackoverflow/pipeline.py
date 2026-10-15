#!/usr/bin/env python3
"""Run fetch → prepare → profile for Stack Overflow styles."""

from __future__ import annotations

import argparse
from pathlib import Path

from stackoverflow.fetch import load_user_ids_from_file, run_fetch
from stackoverflow.prepare import run_prepare
from stackoverflow.profile import run_profile
from stackoverflow.paths import ensure_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SO style profiles for Auto Typer.")
    parser.add_argument("--tag", default="python", help="Tag for top answerers (default: python)")
    parser.add_argument("--users", type=int, default=100, help="Number of users (default: 100)")
    parser.add_argument("--max-answers", type=int, default=80, help="Max answers per user")
    parser.add_argument("--user-ids-file", type=Path, help="Optional file with user IDs")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--skip-profile", action="store_true")
    parser.add_argument("--quick", action="store_true", help="5 users, 15 answers (test run)")
    args = parser.parse_args()

    ensure_dirs()
    users = 5 if args.quick else args.users
    max_ans = 15 if args.quick else args.max_answers

    user_ids = None
    if args.user_ids_file and args.user_ids_file.is_file():
        user_ids = load_user_ids_from_file(args.user_ids_file)

    if not args.skip_fetch:
        run_fetch(
            user_ids=user_ids,
            tag=args.tag,
            user_count=users,
            max_answers_per_user=max_ans,
        )

    if not args.skip_prepare:
        stats = run_prepare()
        print("Prepare:", stats)

    if not args.skip_profile:
        stats = run_profile()
        print("Profiles:", stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
