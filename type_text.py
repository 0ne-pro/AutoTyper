#!/usr/bin/env python3

"""Auto-typing: given text, simulates keyboard input after a short countdown."""



from __future__ import annotations



import argparse

import sys

import time



import pyautogui



from human_type import type_text



# Fail fast if the mouse hits a corner (pyautogui safety)

pyautogui.FAILSAFE = True

pyautogui.PAUSE = 0





def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(

        description="Type the given text into whatever window is focused."

    )

    parser.add_argument(

        "text",

        nargs="?",

        help="Text to type. If omitted, reads from stdin (until EOF).",

    )

    parser.add_argument(

        "-d",

        "--delay",

        type=float,

        default=0.12,

        metavar="SEC",

        help="Fixed delay in robot mode (default: 0.12).",

    )

    parser.add_argument(

        "--delay-min",

        type=float,

        default=0.10,

        metavar="SEC",

        help="Human-like: min seconds between keys (default: 0.10).",

    )

    parser.add_argument(

        "--delay-max",

        type=float,

        default=0.15,

        metavar="SEC",

        help="Human-like: max seconds between keys (default: 0.15).",

    )

    parser.add_argument(

        "-w",

        "--wait",

        type=float,

        default=3.0,

        metavar="SEC",

        help="Countdown before typing starts (default: 3).",

    )

    parser.add_argument(

        "--instant",

        action="store_true",

        help="Start typing immediately (no countdown).",

    )

    parser.add_argument(

        "--robot",

        action="store_true",

        help="Fixed delay every key (no human-like variation or typos).",

    )

    parser.add_argument(

        "--typo-rate",

        type=float,

        default=0.025,

        metavar="RATE",

        help="Chance of a typo per letter, 0–1 (default: 0.025).",

    )

    return parser.parse_args()





def read_text(arg_text: str | None) -> str:

    if arg_text is not None:

        return arg_text

    if sys.stdin.isatty():

        print("Enter text to type (finish with Ctrl+Z then Enter on Windows, Ctrl+D on Unix):")

    return sys.stdin.read()





def countdown(seconds: float) -> None:

    if seconds <= 0:

        return

    whole = int(seconds)

    for i in range(whole, 0, -1):

        print(f"Focus the target window… typing in {i}s", flush=True)

        time.sleep(1)

    remainder = seconds - whole

    if remainder > 0:

        time.sleep(remainder)





def main() -> int:

    args = parse_args()

    text = read_text(args.text)

    if not text:

        print("No text to type.", file=sys.stderr)

        return 1



    if not args.instant:

        countdown(args.wait)



    mode = "robot" if args.robot else "human"

    print(f"Typing ({mode})…", flush=True)

    type_text(

        text,

        args.delay,

        human=not args.robot,

        typo_rate=max(0.0, min(1.0, args.typo_rate)),

        delay_min=args.delay_min,

        delay_max=args.delay_max,

    )

    print("Done.", flush=True)

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

