#!/usr/bin/env python3
"""Background listener: Ctrl+C to copy as usual, then Ctrl+T types clipboard text."""

from __future__ import annotations

import argparse
import sys
import threading
import time

import keyboard
import pyperclip

from human_type import type_text
from humanize import humanize_clipboard

_state = threading.Lock()
_busy = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Listen for Ctrl+T and type the current clipboard contents."
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=0.12,
        metavar="SEC",
        help="Seconds between keystrokes in robot mode (default: 0.12).",
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=0.10,
        metavar="SEC",
        help="Human-like typing: min delay per key (default: 0.10).",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=0.15,
        metavar="SEC",
        help="Human-like typing: max delay per key (default: 0.15).",
    )
    parser.add_argument(
        "-w",
        "--wait",
        type=float,
        default=2.0,
        metavar="SEC",
        help="Pause after Ctrl+T before typing (default: 2.0).",
    )
    parser.add_argument(
        "--robot",
        action="store_true",
        help="Fixed delay; no human-like variation or typos.",
    )
    parser.add_argument(
        "--typo-rate",
        type=float,
        default=0.025,
        metavar="RATE",
        help="Typo chance per letter, 0–1 (default: 0.025).",
    )
    parser.add_argument(
        "--humanize-hotkey",
        action="store_true",
        help="Also bind Ctrl+Shift+H to humanize clipboard (needs API key or Ollama).",
    )
    return parser.parse_args()


def type_clipboard(
    delay: float,
    wait: float,
    *,
    human: bool,
    typo_rate: float,
    delay_min: float,
    delay_max: float,
) -> None:
    global _busy
    with _state:
        if _busy:
            return
        _busy = True

    def work() -> None:
        global _busy
        try:
            text = pyperclip.paste()
            if not text:
                print("Clipboard is empty — copy text with Ctrl+C first.", flush=True)
                return
            if wait > 0:
                time.sleep(wait)
            print(f"Typing {len(text)} characters…", flush=True)
            type_text(
                text,
                delay,
                human=human,
                typo_rate=typo_rate,
                delay_min=delay_min,
                delay_max=delay_max,
            )
            print("Done.", flush=True)
        except Exception as exc:  # noqa: BLE001 — show hook errors in console
            print(f"Error: {exc}", file=sys.stderr, flush=True)
        finally:
            with _state:
                _busy = False

    threading.Thread(target=work, daemon=True).start()


def main() -> int:
    args = parse_args()
    print(
        "Auto Typer hotkey mode running.\n"
        "  1. Select text and press Ctrl+C (normal copy)\n"
        "  2. Click where you want it typed\n"
        "  3. Press Ctrl+T to type from clipboard\n"
        "Move mouse to a screen corner to abort while typing.\n"
        "Press Ctrl+Shift+Q to quit this listener.\n",
        flush=True,
    )

    human = not args.robot
    typo_rate = max(0.0, min(1.0, args.typo_rate))
    mode = "human-like" if human else "robot"
    print(f"Typing mode: {mode} (typo rate {typo_rate:.3f})\n", flush=True)

    def _type_hk() -> None:
        type_clipboard(
            args.delay,
            args.wait,
            human=human,
            typo_rate=typo_rate,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )

    keyboard.add_hotkey("ctrl+t", _type_hk, suppress=True)
    keyboard.add_hotkey("ctrl+alt+t", _type_hk, suppress=True)
    if args.humanize_hotkey:

        def _humanize_hotkey() -> None:
            def work() -> None:
                try:
                    print("Humanizing clipboard…", flush=True)
                    result = humanize_clipboard()
                    print(f"Done — {len(result)} chars on clipboard.", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"Humanize error: {exc}", file=sys.stderr, flush=True)

            threading.Thread(target=work, daemon=True).start()

        print("Ctrl+Shift+H — humanize clipboard\n", flush=True)
        keyboard.add_hotkey("ctrl+shift+h", _humanize_hotkey, suppress=True)
    keyboard.wait("ctrl+shift+q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
