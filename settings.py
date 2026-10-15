"""Persistent app settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


def _config_path() -> Path:
    # Portable mode: a portable.txt next to the app keeps settings in the app folder.
    if (APP_DIR / "portable.txt").is_file():
        return APP_DIR / "settings.json"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    folder = Path(base) / "AutoTyper"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


@dataclass
class AppSettings:
    # Typing (hotkey + manual)
    delay: float = 0.12  # robot/fixed mode; human mode uses delay_min–delay_max
    delay_min: float = 0.10
    delay_max: float = 0.15
    hotkey_wait: float = 2.0
    human_typing: bool = True
    typo_rate: float = 0.025

    # Hotkeys
    hotkeys_enabled: bool = True
    type_hotkey: bool = True
    humanize_hotkey: bool = True

    # Humanize / LLM (default: free local Ollama — no API key)
    provider: str = "ollama"
    model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    mistral_api_key: str = ""
    together_api_key: str = ""
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    show_all_models: bool = True
    humanize_prompt: str = ""
    humanize_strength: str = "standard"
    so_style_user_id: str = ""

    # Window / tray
    start_minimized: bool = False
    close_to_tray: bool = True

    def apply_env(self) -> None:
        """Push GUI settings into environment for humanize_engine."""
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.openai_base_url:
            os.environ["OPENAI_BASE_URL"] = self.openai_base_url
        if self.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.google_api_key:
            os.environ["GOOGLE_API_KEY"] = self.google_api_key
        if self.groq_api_key:
            os.environ["GROQ_API_KEY"] = self.groq_api_key
        if self.openrouter_api_key:
            os.environ["OPENROUTER_API_KEY"] = self.openrouter_api_key
        if self.mistral_api_key:
            os.environ["MISTRAL_API_KEY"] = self.mistral_api_key
        if self.together_api_key:
            os.environ["TOGETHER_API_KEY"] = self.together_api_key
        prov = self.effective_provider()
        os.environ["HUMANIZE_PROVIDER"] = prov
        mid = self.effective_model()
        if mid:
            os.environ["HUMANIZE_MODEL"] = mid
        os.environ["OLLAMA_HOST"] = self.ollama_host
        if prov == "ollama":
            os.environ["OLLAMA_MODEL"] = mid or self.ollama_model.strip() or "llama3.2"
        os.environ["HUMANIZE_SYSTEM_PROMPT"] = self.effective_prompt()

    def effective_prompt(self) -> str:
        from humanize_engine import resolve_system_prompt
        from prose_rules import ensure_prose_rules
        from stackoverflow.style_prompt import compose_with_style

        base = self.humanize_prompt.strip() or resolve_system_prompt(None)
        sid = self.so_style_user_id.strip()
        if sid and sid.lower() not in ("none", "0", ""):
            merged = compose_with_style(base, sid)
        else:
            merged = base
        from prose_rules import ensure_strength

        merged = ensure_strength(merged, self.humanize_strength)
        return ensure_prose_rules(merged)

    def humanize_temperature(self) -> float:
        from prose_rules import STRENGTH_TEMPERATURE, ensure_strength_label

        return STRENGTH_TEMPERATURE.get(ensure_strength_label(self.humanize_strength), 0.7)

    def resolved_model_id(self) -> str:
        from model_catalog import model_id_from_ui

        raw = self.model.strip()
        if not raw and self.provider == "ollama":
            raw = self.ollama_model.strip()
        if not raw:
            return ""
        return model_id_from_ui(raw)

    def _api_key_for_provider(self, provider: str) -> str:
        keys = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
            "mistral": self.mistral_api_key,
            "together": self.together_api_key,
        }
        return keys.get(provider, "").strip()

    def provider_has_credentials(self, provider: str) -> bool:
        if provider == "ollama":
            return bool(self.ollama_host.strip())
        return bool(self._api_key_for_provider(provider))

    def effective_provider(self) -> str:
        from model_catalog import provider_for_model

        if self.model.strip():
            prov = provider_for_model(self.model, self.provider)
        else:
            prov = self.provider.strip().lower() or "ollama"
        if prov == "ollama":
            return "ollama"
        if self.provider_has_credentials(prov):
            return prov
        return "ollama"

    def effective_model(self) -> str | None:
        prov = self.effective_provider()
        if prov == "ollama":
            mid = self.resolved_model_id()
            return mid or self.ollama_model.strip() or "llama3.2"
        mid = self.resolved_model_id()
        return mid or None


def load_settings() -> AppSettings:
    path = _config_path()
    if not path.is_file():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = {f.name for f in AppSettings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in allowed}
        settings = AppSettings(**filtered)
        if "delay_min" not in filtered and "delay_max" not in filtered:
            settings.delay_min = 0.10
            settings.delay_max = 0.15
            settings.delay = 0.12
        if (
            settings.provider.strip().lower() == "openai"
            and not settings.openai_api_key.strip()
            and not settings.model.strip()
        ):
            settings.provider = "ollama"
        return settings
    except (json.JSONDecodeError, TypeError, ValueError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    path = _config_path()
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
