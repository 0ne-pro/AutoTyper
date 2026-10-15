"""Rewrite text via OpenAI, Claude, Gemini, Groq, OpenRouter, Mistral, Together, Ollama."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

Provider = Literal[
    "openai",
    "anthropic",
    "google",
    "groq",
    "openrouter",
    "mistral",
    "together",
    "ollama",
]

_ALL_PROVIDERS = frozenset(
    {"openai", "anthropic", "google", "groq", "openrouter", "mistral", "together", "ollama"}
)

from prose_rules import DEFAULT_SYSTEM_PROMPT, ensure_prose_rules


_PREAMBLE_RE = re.compile(
    r"^\s*(?:(?:certainly|sure|absolutely|of course|okay|ok|here(?:'|’)s|here is|here are)\b[^\n]*?:\s*\n+"
    r"|(?:rewritten(?: text| version)?|rewrite|humanized(?: text| version)?)\s*:\s*)",
    re.IGNORECASE,
)
_POSTAMBLE_RE = re.compile(
    r"\n+\s*(?:let me know|i hope this|feel free to|hope this helps)[^\n]*\s*$", re.IGNORECASE
)
_SPACE_CHARS = dict.fromkeys(
    map(
        ord,
        "               　",
    ),
    " ",
)
_INVISIBLE_CHARS = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_PUNCT_CHARS = {
    ord("‘"): "'",
    ord("’"): "'",
    ord("“"): '"',
    ord("”"): '"',
    ord("…"): "...",
    ord("−"): "-",
}


def _clean_prose(chunk: str) -> str:
    chunk = chunk.translate(_SPACE_CHARS).translate(_INVISIBLE_CHARS).translate(_PUNCT_CHARS)
    chunk = re.sub(r"\s*—\s*", ", ", chunk)  # em dash
    chunk = re.sub(r"(?<=\d)\s*–\s*(?=\d)", "-", chunk)  # numeric range
    chunk = re.sub(r"\s*–\s*", " - ", chunk)  # other en dashes
    chunk = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), chunk)
    return chunk


def _strip_rewrite_preamble(text: str) -> str:
    """Remove chat-style wrappers and AI-typical unicode; leave fenced code untouched."""
    out = text.strip()
    fenced = re.fullmatch(r"```[\w+-]*\n(.*?)\n?```", out, re.DOTALL)
    if fenced and "```" not in fenced.group(1):
        out = fenced.group(1).strip()
    out = _PREAMBLE_RE.sub("", out, count=1)
    out = _POSTAMBLE_RE.sub("", out)
    if len(out) > 1 and out[0] == out[-1] and out[0] in "\"'" and out.count(out[0]) == 2:
        out = out[1:-1]
    parts = out.split("```")
    for i in range(0, len(parts), 2):  # even indexes are outside code fences
        parts[i] = _clean_prose(parts[i])
    return "```".join(parts).strip()


def _format_user_message(text: str) -> str:
    return (
        "Rewrite the SOURCE text per the system instructions. "
        "Keep the same format (no new Q&A, headings, or code).\n\n"
        f"--- SOURCE ---\n{text}\n--- END SOURCE ---"
    )


def resolve_system_prompt(override: str | None = None) -> str:
    if override is not None and override.strip():
        return ensure_prose_rules(override.strip())
    from_env = os.getenv("HUMANIZE_SYSTEM_PROMPT", "").strip()
    if from_env:
        return ensure_prose_rules(from_env)
    return DEFAULT_SYSTEM_PROMPT


_OPENAI_COMPAT: dict[str, tuple[str, str | None]] = {
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1"),
    "together": ("TOGETHER_API_KEY", "https://api.together.xyz/v1"),
}


def _provider() -> Provider:
    name = os.getenv("HUMANIZE_PROVIDER", "ollama").strip().lower()
    if name in _ALL_PROVIDERS:
        return name  # type: ignore[return-value]
    raise ValueError(f"Unknown HUMANIZE_PROVIDER: {name!r}")


def _cloud_provider_missing_key(provider: Provider) -> bool:
    if provider == "ollama":
        return False
    if provider == "anthropic":
        return not os.getenv("ANTHROPIC_API_KEY", "").strip()
    if provider == "google":
        return not (
            os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
        )
    if provider in _OPENAI_COMPAT:
        key_name, _ = _OPENAI_COMPAT[provider]
        return not os.getenv(key_name, "").strip()
    return False


def _model(provider: Provider, override: str | None) -> str:
    if override:
        return override
    defaults: dict[str, str] = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "google": "gemini-2.0-flash",
        "groq": "llama-3.3-70b-versatile",
        "openrouter": "openai/gpt-4o-mini",
        "mistral": "mistral-small-latest",
        "together": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "ollama": "llama3.2",
    }
    env = os.getenv("HUMANIZE_MODEL") or os.getenv("OLLAMA_MODEL")
    if env:
        return env
    return defaults.get(provider, "gpt-4o-mini")


def _ollama_connection_error(message: str) -> bool:
    lower = message.lower()
    return "ollama" in lower and (
        "10054" in lower
        or "10061" in lower
        or "not running" in lower
        or "could not reach" in lower
        or "forcibly closed" in lower
        or "closed the connection" in lower
    )


def _ensure_ollama_ready(model_name: str, *, force_restart: bool) -> None:
    from ollama_service import ensure_ollama_cpu

    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ok, msg = ensure_ollama_cpu(host, model_name, force_restart=force_restart)
    if not ok:
        raise RuntimeError(msg)


def humanize(
    text: str,
    *,
    provider: Provider | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> str:
    text = text.strip()
    if not text:
        return ""

    requested = provider or _provider()
    prov = requested
    if _cloud_provider_missing_key(prov):
        prov = "ollama"
    model_name = _model(prov, model if prov == requested else None)
    prompt = resolve_system_prompt(system_prompt)
    temp = 0.7 if temperature is None else temperature

    if prov == "ollama":
        _ensure_ollama_ready(model_name, force_restart=False)
        try:
            raw = _humanize_ollama(text, model_name, prompt, temp)
        except RuntimeError as exc:
            if not _ollama_connection_error(str(exc)):
                raise
            _ensure_ollama_ready(model_name, force_restart=True)
            raw = _humanize_ollama(text, model_name, prompt, temp)
    elif prov == "anthropic":
        raw = _humanize_anthropic(text, model_name, prompt, temp)
    elif prov == "google":
        raw = _humanize_google(text, model_name, prompt, temp)
    elif prov in _OPENAI_COMPAT:
        raw = _humanize_openai_compat(text, model_name, prov, prompt, temp)
    else:
        raise ValueError(f"Unsupported provider: {prov}")
    return _finish_humanize(raw)


def _finish_humanize(raw: str) -> str:
    out = _strip_rewrite_preamble(raw)
    if not out:
        raise RuntimeError("Model returned empty response")
    return out


def _humanize_openai_compat(
    text: str, model: str, provider: str, prompt: str, temperature: float
) -> str:
    key_name, default_base = _OPENAI_COMPAT[provider]
    api_key = os.getenv(key_name)
    if not api_key:
        raise RuntimeError(f"{key_name} is not set.")

    base_url = os.getenv("OPENAI_BASE_URL") if provider == "openai" else default_base
    if provider == "openai" and os.getenv("OPENAI_BASE_URL"):
        base_url = os.getenv("OPENAI_BASE_URL")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install openai: pip install openai") from exc

    headers = {}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/local/auto-typer"
        headers["X-Title"] = "Auto Typer Humanize"

    client = OpenAI(api_key=api_key, base_url=base_url or None, default_headers=headers or None)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": _format_user_message(text)},
        ],
        temperature=temperature,
    )
    out = response.choices[0].message.content
    if not out:
        raise RuntimeError("Model returned empty response")
    return out.strip()


def _humanize_anthropic(text: str, model: str, prompt: str, temperature: float) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("Install anthropic: pip install anthropic") from exc

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=prompt,
        messages=[{"role": "user", "content": _format_user_message(text)}],
        temperature=temperature,
    )
    parts: list[str] = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    out = "".join(parts)
    if not out:
        raise RuntimeError("Model returned empty response")
    return out.strip()


def _humanize_google(text: str, model: str, prompt: str, temperature: float) -> str:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) is not set.")
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("Install google-generativeai: pip install google-generativeai") from exc

    genai.configure(api_key=api_key)
    gemini = genai.GenerativeModel(model_name=model, system_instruction=prompt)
    response = gemini.generate_content(
        _format_user_message(text),
        generation_config={"temperature": temperature},
    )
    out = response.text
    if not out:
        raise RuntimeError("Model returned empty response")
    return out.strip()


def _humanize_ollama(text: str, model: str, prompt: str, temperature: float) -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": _format_user_message(text)},
        ],
        "options": {
            "temperature": temperature,
            "num_predict": 8192,
            "num_gpu": 0,
        },
    }
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw).get("error", raw)
        except json.JSONDecodeError:
            detail = raw
        detail = str(detail).strip()[:600]
        if "CUDA" in detail or "PTX" in detail:
            detail += (
                " Try: update your NVIDIA driver, or set user env OLLAMA_NUM_GPU=0 "
                "and fully quit/reopen Ollama (or reboot), then retry."
            )
        raise RuntimeError(f"Ollama error: {detail}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        winerr = getattr(reason, "winerror", None)
        text = str(reason)
        if winerr == 10054 or "10054" in text:
            msg = (
                "Ollama closed the connection while generating (usually the model "
                "process crashed — often GPU/CUDA on Windows). Quit Ollama completely, "
                "start again with CPU mode (run `python ollama_service.py --force` or set "
                "OLLAMA_NUM_GPU=0 and run `ollama serve`), then retry humanize."
            )
        elif winerr == 10061 or "10061" in text:
            msg = (
                f"Ollama is not running at {host}. Open the Ollama app from the Start menu "
                "or run `python ollama_service.py --force`, then retry."
            )
        else:
            msg = (
                f"Could not reach Ollama at {host} ({reason}). Keep Ollama running; "
                f"if needed: ollama pull {model}."
            )
        raise RuntimeError(msg) from exc

    message = body.get("message") or {}
    out = message.get("content", "")
    if not out:
        raise RuntimeError("Ollama returned empty response")
    return out.strip()
