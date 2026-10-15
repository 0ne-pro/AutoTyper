"""Model lists (all vendors) and live fetch for humanize providers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

SEP = " — "

VENDOR: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "mistral": "Mistral",
    "together": "Together AI",
    "ollama": "Ollama (local)",
}

# provider -> (label, model_id)
CURATED: dict[str, list[tuple[str, str]]] = {
    "openai": [
        ("GPT-4o", "gpt-4o"),
        ("GPT-4o mini", "gpt-4o-mini"),
        ("GPT-4.1", "gpt-4.1"),
        ("GPT-4.1 mini", "gpt-4.1-mini"),
        ("GPT-4.1 nano", "gpt-4.1-nano"),
        ("GPT-5", "gpt-5"),
        ("GPT-5 mini", "gpt-5-mini"),
        ("GPT-5 nano", "gpt-5-nano"),
        ("GPT-5.2", "gpt-5.2"),
        ("o4-mini", "o4-mini"),
        ("o3", "o3"),
        ("o3-mini", "o3-mini"),
        ("o1", "o1"),
        ("o1-mini", "o1-mini"),
        ("GPT-3.5 Turbo", "gpt-3.5-turbo"),
    ],
    "anthropic": [
        ("Claude Opus 4", "claude-opus-4-20250514"),
        ("Claude Opus 4.1", "claude-opus-4-20250514"),
        ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
        ("Claude 3.7 Sonnet", "claude-3-7-sonnet-20250219"),
        ("Claude 3.5 Sonnet", "claude-3-5-sonnet-latest"),
        ("Claude 3.5 Haiku", "claude-3-5-haiku-latest"),
        ("Claude 3 Opus", "claude-3-opus-latest"),
        ("Claude 3 Haiku", "claude-3-haiku-latest"),
    ],
    "google": [
        ("Gemini 2.0 Flash", "gemini-2.0-flash"),
        ("Gemini 2.0 Flash Lite", "gemini-2.0-flash-lite"),
        ("Gemini 1.5 Pro", "gemini-1.5-pro"),
        ("Gemini 1.5 Flash", "gemini-1.5-flash"),
        ("Gemini 1.5 Flash 8B", "gemini-1.5-flash-8b"),
    ],
    "groq": [
        ("Llama 3.3 70B", "llama-3.3-70b-versatile"),
        ("Llama 3.1 70B", "llama-3.1-70b-versatile"),
        ("Llama 3.1 8B", "llama-3.1-8b-instant"),
        ("Mixtral 8x7B", "mixtral-8x7b-32768"),
        ("Gemma 2 9B", "gemma2-9b-it"),
    ],
    "mistral": [
        ("Mistral Large", "mistral-large-latest"),
        ("Mistral Small", "mistral-small-latest"),
        ("Codestral", "codestral-latest"),
        ("Open Mistral 7B", "open-mistral-7b"),
    ],
    "together": [
        ("Llama 3.1 70B Turbo", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
        ("Qwen 2.5 72B Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"),
    ],
    "openrouter": [
        ("Claude 3.5 Sonnet (OR)", "anthropic/claude-3.5-sonnet"),
        ("Claude 3 Opus (OR)", "anthropic/claude-3-opus"),
        ("GPT-4o (OR)", "openai/gpt-4o"),
        ("Gemini Pro 1.5 (OR)", "google/gemini-pro-1.5"),
        ("Gemini 2.0 Flash (OR)", "google/gemini-2.0-flash-001"),
        ("Llama 3.1 70B (OR)", "meta-llama/llama-3.1-70b-instruct"),
        ("DeepSeek Chat (OR)", "deepseek/deepseek-chat"),
        ("Mistral Large (OR)", "mistralai/mistral-large"),
    ],
    "ollama": [
        ("Llama 3.2", "llama3.2"),
        ("Llama 3.1 8B", "llama3.1:8b"),
        ("Mistral", "mistral"),
        ("Gemma 2", "gemma2"),
        ("Qwen 2.5", "qwen2.5"),
    ],
}

PROVIDERS: tuple[str, ...] = tuple(CURATED.keys())


@dataclass(frozen=True)
class CatalogEntry:
    provider: str
    label: str
    model_id: str

    @property
    def vendor(self) -> str:
        return VENDOR.get(self.provider, self.provider)

    def display(self) -> str:
        return f"[{self.vendor}] {self.label}{SEP}{self.model_id}"


def _build_registry() -> dict[str, CatalogEntry]:
    reg: dict[str, CatalogEntry] = {}
    for provider, rows in CURATED.items():
        for label, mid in rows:
            reg[mid] = CatalogEntry(provider=provider, label=label, model_id=mid)
    return reg


REGISTRY: dict[str, CatalogEntry] = _build_registry()


@dataclass
class ModelChoice:
    label: str
    model_id: str
    provider: str = "openai"

    def to_entry(self) -> CatalogEntry:
        return CatalogEntry(
            provider=self.provider,
            label=self.label,
            model_id=self.model_id,
        )


def _strip_vendor_prefix(value: str) -> str:
    value = value.strip()
    m = re.match(r"^\[[^\]]+\]\s*(.+)$", value)
    if m:
        return m.group(1).strip()
    return value


def model_id_from_ui(value: str) -> str:
    value = _strip_vendor_prefix(value)
    if SEP in value:
        return value.split(SEP, 1)[1].strip()
    return value.strip()


def entry_from_display(value: str) -> CatalogEntry | None:
    mid = model_id_from_ui(value)
    if mid in REGISTRY:
        return REGISTRY[mid]
    prov = value.strip()
    return None


def provider_for_model(value: str, fallback: str = "openai") -> str:
    ent = entry_from_display(value)
    if ent:
        return ent.provider
    m = re.match(r"^\[([^\]]+)\]", value.strip())
    if m:
        tag = m.group(1).lower()
        for prov, name in VENDOR.items():
            if name.lower() == tag or tag in name.lower() or prov in tag:
                return prov
    mid = model_id_from_ui(value).lower()
    if "/" in mid:
        return "openrouter"
    if mid.startswith("claude"):
        return "anthropic"
    if mid.startswith("gemini"):
        return "google"
    if mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3") or mid.startswith("o4"):
        return "openai"
    return fallback.strip().lower() or "openai"


def catalog_for_provider(provider: str) -> list[CatalogEntry]:
    key = provider.strip().lower()
    rows = CURATED.get(key, [])
    return [CatalogEntry(provider=key, label=a, model_id=b) for a, b in rows]


def all_catalog_entries(extra: list[CatalogEntry] | None = None) -> list[CatalogEntry]:
    items: list[CatalogEntry] = []
    seen: set[str] = set()
    for prov in PROVIDERS:
        for e in catalog_for_provider(prov):
            if e.model_id not in seen:
                items.append(e)
                seen.add(e.model_id)
    if extra:
        for e in extra:
            if e.model_id not in seen:
                items.append(e)
                seen.add(e.model_id)
    items.sort(key=lambda e: (e.vendor.lower(), e.label.lower()))
    return items


def combobox_values(provider: str | None, extra: list[CatalogEntry] | None = None) -> list[str]:
    if provider is None or provider == "all":
        return [e.display() for e in all_catalog_entries(extra)]
    items = catalog_for_provider(provider)
    if extra:
        seen = {e.model_id for e in items}
        for e in extra:
            if e.model_id not in seen:
                items.append(e)
    return [e.display() for e in items]


def default_display(provider: str, model_id: str) -> str:
    mid = model_id.strip()
    if mid in REGISTRY:
        return REGISTRY[mid].display()
    if not mid:
        items = catalog_for_provider(provider)
        return items[0].display() if items else ""
    vendor = VENDOR.get(provider, provider)
    return f"[{vendor}] Custom{SEP}{mid}"


def fetch_openai_models(
    api_key: str, base_url: str | None = None, provider: str = "openai"
) -> list[CatalogEntry]:
    if not api_key:
        return []
    try:
        from openai import OpenAI
    except ImportError:
        return []

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    skip = re.compile(r"dall-e|whisper|tts|embedding|audio|realtime|transcribe|moderation|vision", re.I)
    out: list[CatalogEntry] = []
    for m in client.models.list().data:
        mid = m.id
        if skip.search(mid):
            continue
        out.append(CatalogEntry(provider=provider, label=mid, model_id=mid))
    return out


def fetch_openrouter_models() -> list[CatalogEntry]:
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []

    out: list[CatalogEntry] = []
    for item in body.get("data") or []:
        mid = item.get("id")
        name = item.get("name") or mid
        if mid:
            out.append(CatalogEntry(provider="openrouter", label=str(name), model_id=str(mid)))
    return out


def fetch_ollama_models(host: str) -> list[CatalogEntry]:
    base = host.rstrip("/")
    req = urllib.request.Request(f"{base}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []

    out: list[CatalogEntry] = []
    for item in body.get("models") or []:
        name = item.get("name") or item.get("model")
        if name:
            out.append(CatalogEntry(provider="ollama", label=str(name), model_id=str(name)))
    return out


def fetch_all_remote(
    *,
    openai_key: str = "",
    openai_base: str | None = None,
    groq_key: str = "",
    openrouter_key: str = "",
    ollama_host: str = "",
) -> list[CatalogEntry]:
    extra: list[CatalogEntry] = []
    extra.extend(fetch_openrouter_models())
    if openai_key:
        extra.extend(fetch_openai_models(openai_key, openai_base, "openai"))
    if groq_key:
        extra.extend(
            fetch_openai_models(groq_key, "https://api.groq.com/openai/v1", "groq")
        )
    if openrouter_key:
        extra.extend(
            fetch_openai_models(openrouter_key, "https://openrouter.ai/api/v1", "openrouter")
        )
    if ollama_host:
        extra.extend(fetch_ollama_models(ollama_host))
    return extra
