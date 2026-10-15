"""Human-like typing: variable timing, pauses, occasional typos and corrections."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Literal

import pyautogui

PauseKind = Literal["key", "space", "punct", "newline", "typo_notice", "burst"]

# Lowercase QWERTY neighbors for plausible mistypes
_NEIGHBORS: dict[str, str] = {
    "a": "qwsz",
    "b": "vghn",
    "c": "xdfv",
    "d": "serfcx",
    "e": "wsdr",
    "f": "drtgvc",
    "g": "ftyhbv",
    "h": "gyujnb",
    "i": "ujko",
    "j": "huikmn",
    "k": "jiolm",
    "l": "kop",
    "m": "njk",
    "n": "bhjm",
    "o": "iklp",
    "p": "ol",
    "q": "wa",
    "r": "edft",
    "s": "awedxz",
    "t": "rfgy",
    "u": "yhji",
    "v": "cfgb",
    "w": "qase",
    "x": "zsdc",
    "y": "tghu",
    "z": "asx",
}

_PUNCT = frozenset(".,!?;:")


@dataclass
class HumanTypingConfig:
    base_delay: float = 0.12
    delay_min: float = 0.10
    delay_max: float = 0.15
    typo_rate: float = 0.025
    human: bool = True


def _clamp_delay(seconds: float, minimum: float = 0.025) -> float:
    return max(minimum, seconds)


def _press_char(ch: str) -> None:
    if ch == "\n":
        pyautogui.press("enter")
    elif ch == "\t":
        pyautogui.press("tab")
    elif ord(ch) >= 32:
        pyautogui.write(ch, interval=0)


def _typo_char(ch: str) -> str | None:
    lower = ch.lower()
    neighbors = _NEIGHBORS.get(lower)
    if not neighbors:
        return None
    wrong = random.choice(neighbors)
    return wrong.upper() if ch.isupper() else wrong


def _sleep_human(
    config: HumanTypingConfig, kind: PauseKind, keys_since_break: int, base: float
) -> None:
    if kind == "key":
        delay = random.gauss(base, base * 0.35)
    elif kind == "space":
        delay = random.gauss(base * 1.35, base * 0.4)
    elif kind == "punct":
        delay = random.uniform(base * 2.5, base * 6.0)
    elif kind == "newline":
        delay = random.uniform(base * 4.0, base * 10.0)
    elif kind == "typo_notice":
        delay = random.uniform(base * 3.0, base * 8.0)
    else:
        delay = random.gauss(base * 0.75, base * 0.25)

    if keys_since_break > 0 and random.random() < 0.022:
        delay += random.uniform(0.4, 1.8)

    time.sleep(_clamp_delay(delay))


def _maybe_typo_and_correct(ch: str, config: HumanTypingConfig, base: float) -> bool:
    """If a typo happens, type wrong char, pause, backspace, return True."""
    if not ch.isalpha() or random.random() >= config.typo_rate:
        return False
    wrong = _typo_char(ch)
    if wrong is None:
        return False

    _press_char(wrong)
    time.sleep(_clamp_delay(random.uniform(base * 2, base * 5)))
    pyautogui.press("backspace")
    time.sleep(_clamp_delay(random.uniform(base * 0.8, base * 2)))
    return True


def type_text_human(text: str, config: HumanTypingConfig | None = None) -> None:
    cfg = config or HumanTypingConfig()
    keys_since_break = 0
    burst_left = 0

    lo = min(cfg.delay_min, cfg.delay_max)
    hi = max(cfg.delay_min, cfg.delay_max)

    for i, ch in enumerate(text):
        if ord(ch) < 32 and ch not in "\n\t":
            continue

        base = random.uniform(lo, hi) if hi > lo else lo

        if ch.isalpha() and cfg.human:
            _maybe_typo_and_correct(ch, cfg, base)

        _press_char(ch)

        keys_since_break += 1
        if burst_left <= 0 and ch.isalnum() and random.random() < 0.12:
            burst_left = random.randint(3, 7)

        if ch == "\n":
            kind: PauseKind = "newline"
            burst_left = 0
        elif ch == " ":
            kind = "space"
        elif ch in _PUNCT:
            kind = "punct"
        elif burst_left > 0:
            kind = "burst"
            burst_left -= 1
        else:
            kind = "key"

        if cfg.human and ch == " ":
            j = i + 1
            while j < len(text) and text[j] == " ":
                j += 1
            word_len = 0
            while j + word_len < len(text) and text[j + word_len].isalpha():
                word_len += 1
            if word_len >= 8 and random.random() < 0.4:
                time.sleep(_clamp_delay(random.uniform(base * 2, base * 6)))

        _sleep_human(cfg, kind, keys_since_break, base)


def type_text(
    text: str,
    delay: float = 0.12,
    *,
    human: bool = True,
    typo_rate: float = 0.025,
    delay_min: float | None = None,
    delay_max: float | None = None,
) -> None:
    if not human:
        for ch in text:
            if ch == "\n":
                pyautogui.press("enter")
            elif ch == "\t":
                pyautogui.press("tab")
            elif ord(ch) < 32:
                continue
            else:
                pyautogui.write(ch, interval=0)
            if delay:
                time.sleep(delay)
        return

    dmin = delay_min if delay_min is not None else delay
    dmax = delay_max if delay_max is not None else delay
    type_text_human(
        text,
        HumanTypingConfig(
            base_delay=(dmin + dmax) / 2,
            delay_min=dmin,
            delay_max=dmax,
            typo_rate=typo_rate,
            human=True,
        ),
    )
