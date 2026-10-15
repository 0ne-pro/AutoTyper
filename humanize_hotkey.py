#!/usr/bin/env python3
"""Ctrl+Shift+H: humanize clipboard in place. Ctrl+Shift+Q: quit."""

from __future__ import annotations

import argparse
import sys
import threading

import keyboard

from humanize_engine import Provider
from humanize import humanize_clipboard

_lock = threading.Lock()
_busy = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hotkey: humanize clipboard text.")
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
        help="Override model name.",
    )
    return parser.parse_args()


def run_humanize(provider: Provider | None, model: str | None) -> None:
    global _busy
    with _lock:
        if _busy:
            return
        _busy = True

    def work() -> None:
        global _busy
        try:
            print("Humanizing clipboard…", flush=True)
            result = humanize_clipboard(provider=provider, model=model)
            print(f"Done — {len(result)} characters on clipboard.", flush=True)
        except ValueError as exc:
            print(str(exc), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr, flush=True)
        finally:
            with _lock:
                _busy = False

    threading.Thread(target=work, daemon=True).start()


def main() -> int:
    args = parse_args()
    provider: Provider | None = args.provider  # type: ignore[assignment]
    print(
        "Humanize hotkey running.\n"
        "  1. Copy text with Ctrl+C\n"
        "  2. Press Ctrl+Shift+H to rewrite it (result replaces clipboard)\n"
        "  3. Use Ctrl+T typer or paste where you need it\n"
        "Quit: Ctrl+Shift+Q\n",
        flush=True,
    )
    keyboard.add_hotkey(
        "ctrl+shift+h",
        lambda: run_humanize(provider, args.model),
        suppress=True,
    )
    keyboard.wait("ctrl+shift+q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
