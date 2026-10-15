"""Global hotkeys driven by AppSettings."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable

import keyboard
import pyperclip

from human_type import type_text
from humanize import humanize_clipboard
from settings import AppSettings

LogFn = Callable[[str], None]
SettingsFn = Callable[[], AppSettings]

TYPE_HOTKEYS = ("ctrl+t", "ctrl+alt+t")

HUMANIZE_HOTKEYS = (
    "ctrl+alt+h",
    "ctrl+alt+j",
    "ctrl+shift+h",
    "ctrl+alt+shift+h",
)


def _is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


class HotkeyService:
    def __init__(self, get_settings: SettingsFn, log: LogFn, root=None) -> None:
        self._get_settings = get_settings
        self._log = log
        self._root = root
        self._lock = threading.Lock()
        self._busy = False
        self._registered = False
        self._hooks_added = False
        self._win_hotkeys = None
        self._use_win = sys.platform == "win32" and root is not None

    def _clear_hotkeys(self) -> None:
        try:
            keyboard.unhook_all_hotkeys()
        except AttributeError:
            try:
                keyboard.unhook_all()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        if self._use_win and self._win_hotkeys is not None:
            self._win_hotkeys.clear()
        self._hooks_added = False

    def start(self) -> None:
        if self._registered:
            self.refresh()
            return
        if self._use_win:
            from win_hotkeys import WinHotkeys

            self._win_hotkeys = WinHotkeys(self._root)
            self._log("Hotkey backend: Windows RegisterHotKey (no admin required).")
        elif _is_admin():
            self._log("Hotkey backend: keyboard hook (Administrator).")
        else:
            self._log(
                "Hotkey backend: keyboard hook. If keys fail, run as Administrator "
                "or use Windows GUI build."
            )
        self.refresh()
        self._registered = True

    def refresh(self) -> None:
        self._clear_hotkeys()
        settings = self._get_settings()
        settings.apply_env()
        if not settings.hotkeys_enabled:
            self._log("Hotkeys disabled.")
            return

        if self._use_win and self._win_hotkeys is not None:
            type_ok, humanize_ok = self._register_win_hotkeys(settings)
            need_type_kb = settings.type_hotkey and not type_ok
            need_hum_kb = settings.humanize_hotkey and not humanize_ok
            if need_type_kb or need_hum_kb:
                parts: list[str] = []
                if need_type_kb:
                    parts.append("type")
                if need_hum_kb:
                    parts.append("humanize")
                self._log("Keyboard hook fallback for: " + ", ".join(parts))
                self._register_keyboard_hotkeys(
                    settings,
                    enable_type=need_type_kb,
                    enable_humanize=need_hum_kb,
                )
        else:
            self._register_keyboard_hotkeys(settings)

    def _register_win_hotkeys(self, settings: AppSettings) -> tuple[bool, bool]:
        from win_hotkeys import (
            ID_HUMANIZE_ALT,
            ID_HUMANIZE_ALT2,
            ID_HUMANIZE_J,
            ID_HUMANIZE_SHIFT,
            ID_TYPE,
            ID_TYPE_ALT,
            MOD_ALT,
            MOD_CONTROL,
            MOD_SHIFT,
            VK_H,
            VK_J,
            VK_T,
            hotkey_error_text,
        )

        wh = self._win_hotkeys
        assert wh is not None
        specs: list[tuple[int, int, int, Callable[[], None], str]] = []
        if settings.type_hotkey:
            specs.extend(
                [
                    (ID_TYPE, MOD_CONTROL, VK_T, self._on_type, "Ctrl+T"),
                    (ID_TYPE_ALT, MOD_CONTROL | MOD_ALT, VK_T, self._on_type, "Ctrl+Alt+T"),
                ]
            )
        if settings.humanize_hotkey:
            specs.extend(
                [
                    (
                        ID_HUMANIZE_ALT,
                        MOD_CONTROL | MOD_ALT,
                        VK_H,
                        self._on_humanize,
                        "Ctrl+Alt+H",
                    ),
                    (
                        ID_HUMANIZE_SHIFT,
                        MOD_CONTROL | MOD_SHIFT,
                        VK_H,
                        self._on_humanize,
                        "Ctrl+Shift+H",
                    ),
                    (
                        ID_HUMANIZE_ALT2,
                        MOD_CONTROL | MOD_ALT | MOD_SHIFT,
                        VK_H,
                        self._on_humanize,
                        "Ctrl+Alt+Shift+H",
                    ),
                    (
                        ID_HUMANIZE_J,
                        MOD_CONTROL | MOD_ALT,
                        VK_J,
                        self._on_humanize,
                        "Ctrl+Alt+J",
                    ),
                ]
            )

        if not specs:
            return False, False

        results = wh.apply([(a, b, c, d) for a, b, c, d, _label in specs])
        by_id = {hotkey_id: (ok, err) for hotkey_id, ok, err in results}
        active: list[str] = []
        type_ok = False
        humanize_ok = False
        for hotkey_id, _mod, _vk, _cb, label in specs:
            ok, err = by_id.get(hotkey_id, (False, 0))
            if ok:
                active.append(label)
                if hotkey_id in (ID_TYPE, ID_TYPE_ALT):
                    type_ok = True
                else:
                    humanize_ok = True
            else:
                self._log(f"Could not register {label}: {hotkey_error_text(err)}.")

        if settings.type_hotkey and not type_ok:
            self._log("No type hotkey registered — close other Auto Typer copies or pick a free combo.")
        if settings.humanize_hotkey and not humanize_ok:
            self._log("No humanize hotkey registered — try closing apps that use Ctrl+Alt+H.")

        wh.start()
        self._hooks_added = bool(active)
        self._log("Active: " + (", ".join(active) if active else "none"))
        return type_ok, humanize_ok

    def _register_keyboard_hotkeys(
        self,
        settings: AppSettings,
        *,
        enable_type: bool = True,
        enable_humanize: bool = True,
    ) -> None:
        added = False
        if enable_type and settings.type_hotkey:
            for combo in TYPE_HOTKEYS:
                keyboard.add_hotkey(combo, self._on_type, suppress=True)
            added = True
        if enable_humanize and settings.humanize_hotkey:
            for combo in HUMANIZE_HOTKEYS:
                keyboard.add_hotkey(combo, self._on_humanize, suppress=True)
            added = True
        if added:
            self._hooks_added = True

    def stop(self) -> None:
        self._clear_hotkeys()
        if self._use_win and self._win_hotkeys is not None:
            self._win_hotkeys.stop()
        self._registered = False

    def _try_begin(self) -> bool:
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            return True

    def _end(self) -> None:
        with self._lock:
            self._busy = False

    def _on_type(self) -> None:
        self._log("Hotkey: type")
        if not self._try_begin():
            self._log("Busy — ignored Ctrl+T.")
            return

        def work() -> None:
            try:
                settings = self._get_settings()
                text = pyperclip.paste()
                if not text or not text.strip():
                    self._log("Clipboard empty (Ctrl+C first).")
                    return
                wait = settings.hotkey_wait
                if wait > 0:
                    time.sleep(wait)
                human = settings.human_typing
                self._log(f"Typing {len(text)} chars…")
                type_text(
                    text,
                    settings.delay,
                    human=human,
                    typo_rate=settings.typo_rate,
                    delay_min=settings.delay_min,
                    delay_max=settings.delay_max,
                )
                self._log("Typing done.")
            except Exception as exc:  # noqa: BLE001
                self._log(f"Type error: {exc}")
            finally:
                self._end()

        threading.Thread(target=work, daemon=True).start()

    def _on_humanize(self) -> None:
        self._log("Hotkey: humanize")
        if not self._try_begin():
            self._log("Busy — ignored humanize hotkey.")
            return

        def work() -> None:
            try:
                settings = self._get_settings()
                settings.apply_env()
                text = pyperclip.paste()
                if not text or not text.strip():
                    self._log("Clipboard empty — Ctrl+C first.")
                    return
                prov = settings.effective_provider()
                model = settings.effective_model() or "default"
                self._log(f"Humanizing {len(text)} chars via {prov} ({model})…")
                if prov == "ollama":
                    self._log("Checking Ollama (CPU)…")
                result = humanize_clipboard(
                    provider=settings.effective_provider(),  # type: ignore[arg-type]
                    model=settings.effective_model(),
                    system_prompt=settings.effective_prompt(),
                    temperature=settings.humanize_temperature(),
                )
                self._log(f"Humanize done ({len(result)} chars on clipboard).")
            except Exception as exc:  # noqa: BLE001
                self._log(f"Humanize error: {exc}")
            finally:
                self._end()

        threading.Thread(target=work, daemon=True).start()
