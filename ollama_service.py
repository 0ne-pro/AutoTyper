"""Ensure Ollama listens on CPU (avoids CUDA/PTX crashes on some Windows GPUs)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _ollama_exe() -> Path | None:
    bundled = Path(__file__).resolve().parent / "ollama" / "ollama.exe"
    if bundled.is_file():
        return bundled
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if local.is_file():
        return local
    return None


def _chat_ok(host: str, model: str, timeout: float = 90.0) -> bool:
    host = host.rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "user", "content": "ping"}],
        "options": {"num_predict": 8, "num_gpu": 0},
    }
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool((body.get("message") or {}).get("content"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return False


def _server_up(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/", timeout=3) as resp:
            return resp.status == 200
    except OSError:
        return False


def _stop_ollama_processes() -> None:
    if sys.platform != "win32":
        return
    for pattern in ("ollama.exe", "ollama app.exe"):
        subprocess.run(
            ["taskkill", "/F", "/IM", pattern],
            capture_output=True,
            check=False,
        )
    time.sleep(3)


def _start_ollama_serve_cpu() -> bool:
    exe = _ollama_exe()
    if exe is None:
        return False
    env = os.environ.copy()
    env["OLLAMA_NUM_GPU"] = "0"
    env["CUDA_VISIBLE_DEVICES"] = "-1"
    env["OLLAMA_VULKAN"] = "0"
    env["HIP_VISIBLE_DEVICES"] = "-1"
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.Popen(
        [str(exe), "serve"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    return True


def ensure_ollama_cpu(
    host: str = "http://127.0.0.1:11434",
    model: str = "llama3.2",
    *,
    force_restart: bool = False,
) -> tuple[bool, str]:
    """
    Return (ok, message). Restarts Ollama in CPU mode if inference fails or force_restart.
    """
    exe = _ollama_exe()
    if exe is None:
        return False, "Ollama not installed (ollama.com)."

    if not force_restart and _server_up(host) and _chat_ok(host, model):
        return True, "Ollama OK (CPU/GPU inference test passed)."

    _stop_ollama_processes()
    if not _start_ollama_serve_cpu():
        return False, "Could not start Ollama serve."

    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(2)
        if not _server_up(host):
            continue
        if _chat_ok(host, model, timeout=45.0):
            return True, "Ollama restarted in CPU mode (OLLAMA_NUM_GPU=0)."
    return False, "Ollama started but chat test still failing — try reboot or ollama pull " + model


def main() -> int:
    force = "--force" in sys.argv
    ok, msg = ensure_ollama_cpu(force_restart=force)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
