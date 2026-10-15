"""Stack Exchange API client (rate-limited)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://api.stackexchange.com/2.3"
SITE = "stackoverflow"


class StackExchangeClient:
    def __init__(self, key: str | None = None, pause_sec: float = 0.35) -> None:
        self.key = key or os.getenv("STACKEXCHANGE_KEY", "").strip() or None
        self.pause_sec = pause_sec
        self._last = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.pause_sec:
            time.sleep(self.pause_sec - elapsed)

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        params.setdefault("site", SITE)
        if self.key:
            params["key"] = self.key
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{BASE}{path}?{qs}"
        last_exc: Exception | None = None
        for attempt in range(5):
            self._wait()
            req = urllib.request.Request(url, headers={"User-Agent": "AutoTyper/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if "error_message" in data:
                    raise RuntimeError(data["error_message"])
                return data
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in (502, 503, 429) and attempt < 4:
                    time.sleep(2 ** attempt)
                    last_exc = exc
                    continue
                raise RuntimeError(f"Stack Exchange API error {exc.code}: {body[:500]}") from exc
            except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    last_exc = exc
                    continue
                raise RuntimeError(f"Stack Exchange API network error: {exc}") from exc
            finally:
                self._last = time.monotonic()
        raise RuntimeError(f"Stack Exchange API failed after retries: {last_exc}")
