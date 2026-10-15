#!/usr/bin/env python3
"""Rewrite text so it reads more like a human wrote it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyperclip

from humanize_engine import Provider, humanize


def humanize_clipboard(
    provider: Provider | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> str:
    """Read clipboard, humanize, write back; return new text."""
    text = pyperclip.paste()
    if not text or not text.strip():
        raise ValueError("Clipboard is empty")
    result = humanize(
        text,
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        temperature=temperature,
    )
    pyperclip.copy(result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert text to a more human-sounding version.")
    parser.add_argument(
        "input",
        nargs="?",
        help="Input file path. If omitted, reads stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write result to this file instead of stdout.",
    )
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Read text from clipboard; write result back to clipboard.",
    )
    parser.add_argument(
        "--provider",
        choices=(
            "openai",
            "anthropic",
            "google",
            "groq",
            "openrouter",
            "mistral",
            "together",
            "ollama",
        ),
        help="Override HUMANIZE_PROVIDER from .env",
    )
    parser.add_argument(
        "--model",
        help="Override model name (OpenAI or Ollama).",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Also copy result to clipboard (when using -o or stdout).",
    )
    return parser.parse_args()


def read_input(args: argparse.Namespace) -> str:
    if args.clipboard:
        text = pyperclip.paste()
        if not text or not text.strip():
            raise SystemExit("Clipboard is empty.")
        return text
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        print("Paste text, then Ctrl+Z Enter (Windows) or Ctrl+D (Unix):", file=sys.stderr)
    return sys.stdin.read()


def write_output(result: str, args: argparse.Namespace) -> None:
    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(result)
    if args.copy or args.clipboard:
        pyperclip.copy(result)


def main() -> int:
    args = parse_args()
    try:
        raw = read_input(args)
        provider: Provider | None = args.provider  # type: ignore[assignment]
        result = humanize(raw, provider=provider, model=args.model)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_output(result, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
