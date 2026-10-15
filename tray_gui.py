#!/usr/bin/env python3
"""GUI + system tray for Auto Typer and Humanize."""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import pyautogui
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

from hotkey_service import HotkeyService
from human_type import type_text
from humanize import humanize_clipboard
from humanize_engine import DEFAULT_SYSTEM_PROMPT
from prose_rules import ASSESSMENT_PROSE_RULES, HUMANIZE_STRENGTHS
from stackoverflow.style_prompt import compose_with_style, list_profiles
from model_catalog import (
    PROVIDERS,
    combobox_values,
    default_display,
    fetch_all_remote,
    model_id_from_ui,
    provider_for_model,
)
from settings import AppSettings, load_settings, save_settings

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


def _asset_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / name


def _use_brand_taskbar_id() -> None:
    """Stop Windows from pinning this window to python.exe's icon."""
    if sys.platform != "win32":
        return
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AutoTyper")


def _make_tray_image() -> Image.Image:
    png = _asset_path("icon.png")
    if png.is_file():
        img = Image.open(png).convert("RGBA")
        return img.resize((64, 64), Image.Resampling.LANCZOS)
    img = Image.new("RGB", (64, 64), color=(22, 24, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("segoeui.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.text((18, 12), "T", fill=(255, 255, 255), font=font)
    return img


class TrayApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._typing = False
        self._tray: pystray.Icon | None = None
        self._tray_thread: threading.Thread | None = None

        _use_brand_taskbar_id()
        self.root = tk.Tk()
        self.root.title("Auto Typer")
        self.root.minsize(560, 620)
        self._apply_window_icon()
        self.root.after(50, self._apply_window_icon)
        self._all_model_displays: list[str] = []
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

        self._build_vars()
        self._build_ui()
        self._hotkeys = HotkeyService(self._current_settings, self._log, root=self.root)
        self._hotkeys.start()
        self.root.after(300, self._apply_hotkeys)

        self.root.after(200, self._drain_log_queue)
        if self.settings.start_minimized:
            self.root.after(100, self._hide_to_tray)

    def _apply_window_icon(self) -> None:
        ico = _asset_path("icon.ico")
        png = _asset_path("icon.png")
        if ico.is_file():
            try:
                self.root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
            self._set_win32_icons(ico)
        if not png.is_file():
            return
        image = Image.open(png).convert("RGBA")
        self._window_icons = [
            ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS))
            for size in (16, 32, 48)
        ]
        self.root.iconphoto(True, *self._window_icons)

    def _set_win32_icons(self, ico: Path) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_void_p,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        image_icon = 1
        load_from_file = 0x10
        wm_seticon = 0x80
        hwnd = self.root.winfo_id()
        handles: list[int] = []
        for size, kind in ((16, 0), (32, 1), (48, 1)):
            handle = user32.LoadImageW(None, str(ico), image_icon, size, size, load_from_file)
            if not handle:
                continue
            user32.SendMessageW(hwnd, wm_seticon, kind, handle)
            handles.append(handle)
        self._icon_handles = handles

    def _build_vars(self) -> None:
        s = self.settings
        self.delay_min_var = tk.StringVar(value=str(s.delay_min))
        self.delay_max_var = tk.StringVar(value=str(s.delay_max))
        self.hotkey_wait_var = tk.StringVar(value=str(s.hotkey_wait))
        self.typo_var = tk.StringVar(value=str(s.typo_rate))
        self.human_var = tk.BooleanVar(value=s.human_typing)
        self.hotkeys_enabled_var = tk.BooleanVar(value=s.hotkeys_enabled)
        self.type_hk_var = tk.BooleanVar(value=s.type_hotkey)
        self.humanize_hk_var = tk.BooleanVar(value=s.humanize_hotkey)
        self.provider_var = tk.StringVar(value=s.provider)
        stored_model = s.model.strip() or (
            s.ollama_model.strip() if s.provider == "ollama" else ""
        )
        self.model_var = tk.StringVar(value=default_display(s.provider, stored_model))
        self.api_key_var = tk.StringVar(value=s.openai_api_key)
        self.anthropic_key_var = tk.StringVar(value=s.anthropic_api_key)
        self.google_key_var = tk.StringVar(value=s.google_api_key)
        self.groq_key_var = tk.StringVar(value=s.groq_api_key)
        self.openrouter_key_var = tk.StringVar(value=s.openrouter_api_key)
        self.mistral_key_var = tk.StringVar(value=s.mistral_api_key)
        self.together_key_var = tk.StringVar(value=s.together_api_key)
        self.base_url_var = tk.StringVar(value=s.openai_base_url)
        self.ollama_host_var = tk.StringVar(value=s.ollama_host)
        self.show_all_models_var = tk.BooleanVar(value=s.show_all_models)
        self.search_var = tk.StringVar(value="")
        self.so_style_var = tk.StringVar(value=s.so_style_user_id or "none")
        self.ollama_model_var = tk.StringVar(value=s.ollama_model)
        self.humanize_strength_var = tk.StringVar(
            value=s.humanize_strength if s.humanize_strength in HUMANIZE_STRENGTHS else "standard"
        )
        self.start_min_var = tk.BooleanVar(value=s.start_minimized)
        self.close_tray_var = tk.BooleanVar(value=s.close_to_tray)
        self.manual_wait_var = tk.StringVar(value="3")

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        typing_tab = ttk.Frame(nb)
        human_tab = ttk.Frame(nb)
        prompt_tab = ttk.Frame(nb)
        hk_tab = ttk.Frame(nb)
        log_tab = ttk.Frame(nb)
        nb.add(typing_tab, text="Typing")
        nb.add(human_tab, text="Humanize")
        nb.add(prompt_tab, text="Prompt")
        nb.add(hk_tab, text="Hotkeys")
        nb.add(log_tab, text="Log")

        self._build_typing_tab(typing_tab)
        self._build_human_tab(human_tab)
        self._build_prompt_tab(prompt_tab)
        self._build_hotkey_tab(hk_tab)
        self._build_log_tab(log_tab)

        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(bar, text="Save settings", command=self._save_settings).pack(side=tk.LEFT)
        ttk.Button(bar, text="Apply hotkeys", command=self._apply_hotkeys).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Hide to tray", command=self._hide_to_tray).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Quit", command=self._quit).pack(side=tk.RIGHT)

    def _row(self, parent: ttk.Frame, label: str, widget: tk.Widget, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=3)
        parent.columnconfigure(1, weight=1)

    def _build_typing_tab(self, tab: ttk.Frame) -> None:
        frm = ttk.LabelFrame(tab, text="Manual type from box")
        frm.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.text = scrolledtext.ScrolledText(frm, height=10, wrap=tk.WORD)
        self.text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        opts = ttk.Frame(frm)
        opts.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(opts, text="Countdown:").pack(side=tk.LEFT)
        ttk.Entry(opts, textvariable=self.manual_wait_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Button(opts, text="Type now", command=self._manual_type).pack(side=tk.LEFT, padx=8)

        params = ttk.LabelFrame(tab, text="Typing parameters (hotkey + manual)")
        params.pack(fill=tk.X, padx=4, pady=4)
        self._row(params, "Delay min (sec/key):", ttk.Entry(params, textvariable=self.delay_min_var), 0)
        self._row(params, "Delay max (sec/key):", ttk.Entry(params, textvariable=self.delay_max_var), 1)
        self._row(params, "Hotkey wait (sec):", ttk.Entry(params, textvariable=self.hotkey_wait_var), 2)
        self._row(params, "Typo rate (0–1):", ttk.Entry(params, textvariable=self.typo_var), 3)
        ttk.Checkbutton(params, text="Human-like typing", variable=self.human_var).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=4, pady=3
        )

    def _build_human_tab(self, tab: ttk.Frame) -> None:
        outer = ttk.Frame(tab)
        outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        frm = ttk.Frame(canvas)
        frm.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frm, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.provider_combo = ttk.Combobox(
            frm,
            textvariable=self.provider_var,
            values=PROVIDERS,
            state="readonly",
        )
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)
        self._row(frm, "API provider:", self.provider_combo, 0)
        ttk.Checkbutton(
            frm,
            text="Show all vendors in model list (OpenAI, Claude, Gemini, Groq, …)",
            variable=self.show_all_models_var,
            command=self._refresh_model_list,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=4, pady=2)

        model_row = ttk.Frame(frm)
        model_row.columnconfigure(0, weight=1)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, width=52)
        self.model_combo.grid(row=0, column=0, sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        ttk.Button(model_row, text="Refresh all", command=self._fetch_models_remote).grid(
            row=0, column=1, padx=(6, 0)
        )
        self._row(frm, "Selected model:", model_row, 2)

        ttk.Label(frm, text="Search:").grid(row=3, column=0, sticky="w", padx=4)
        search_entry = ttk.Entry(frm, textvariable=self.search_var)
        search_entry.grid(row=3, column=1, sticky="ew", padx=4, pady=3)
        self.search_var.trace_add("write", lambda *_: self._fill_model_listbox())

        list_frame = ttk.LabelFrame(frm, text="All models (click to select)")
        list_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=4, pady=6)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.model_listbox = tk.Listbox(list_frame, height=10, exportselection=False)
        lb_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.model_listbox.yview)
        self.model_listbox.configure(yscrollcommand=lb_scroll.set)
        self.model_listbox.grid(row=0, column=0, sticky="nsew")
        lb_scroll.grid(row=0, column=1, sticky="ns")
        self.model_listbox.bind("<<ListboxSelect>>", self._on_listbox_model)

        keys = ttk.LabelFrame(frm, text="API keys (use the key for the vendor you pick)")
        keys.grid(row=5, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self._row(keys, "OpenAI:", ttk.Entry(keys, textvariable=self.api_key_var, show="*"), 0)
        self._row(keys, "Anthropic (Claude):", ttk.Entry(keys, textvariable=self.anthropic_key_var, show="*"), 1)
        self._row(keys, "Google (Gemini):", ttk.Entry(keys, textvariable=self.google_key_var, show="*"), 2)
        self._row(keys, "Groq:", ttk.Entry(keys, textvariable=self.groq_key_var, show="*"), 3)
        self._row(keys, "OpenRouter:", ttk.Entry(keys, textvariable=self.openrouter_key_var, show="*"), 4)
        self._row(keys, "Mistral:", ttk.Entry(keys, textvariable=self.mistral_key_var, show="*"), 5)
        self._row(keys, "Together AI:", ttk.Entry(keys, textvariable=self.together_key_var, show="*"), 6)
        self._row(keys, "OpenAI base URL:", ttk.Entry(keys, textvariable=self.base_url_var), 7)
        self._row(keys, "Ollama host:", ttk.Entry(keys, textvariable=self.ollama_host_var), 8)

        strength_combo = ttk.Combobox(
            frm,
            textvariable=self.humanize_strength_var,
            values=HUMANIZE_STRENGTHS,
            state="readonly",
            width=24,
        )
        self._row(frm, "Rewrite strength:", strength_combo, 6)
        ttk.Label(
            frm,
            text="Strong = more rewrite (Ctrl+Alt+J uses this). Save settings after changing.",
            wraplength=480,
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        ttk.Button(frm, text="Humanize clipboard now", command=self._humanize_now).grid(
            row=8, column=0, columnspan=2, pady=12
        )
        frm.columnconfigure(1, weight=1)
        self._refresh_model_list()

    def _build_prompt_tab(self, tab: ttk.Frame) -> None:
        top = ttk.Frame(tab)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        so_row = ttk.LabelFrame(top, text="Stack Overflow style (100 profiles)")
        so_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(
            so_row,
            text="Pick a profile learned from public SO answers (CC BY-SA). Run fetch once if list is empty.",
            wraplength=500,
        ).pack(anchor="w", padx=6, pady=2)
        so_inner = ttk.Frame(so_row)
        so_inner.pack(fill=tk.X, padx=6, pady=4)
        self.so_style_combo = ttk.Combobox(so_inner, textvariable=self.so_style_var, width=55, state="readonly")
        self.so_style_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(so_inner, text="Refresh profiles", command=self._refresh_so_profiles).pack(side=tk.LEFT, padx=4)
        ttk.Button(so_inner, text="Build SO data (100 users)", command=self._run_so_pipeline).pack(
            side=tk.LEFT, padx=4
        )
        self._refresh_so_profiles()

        ttk.Label(
            tab,
            text="Base system prompt (merged with SO profile when selected). User message = text to rewrite.",
            wraplength=520,
        ).pack(anchor="w", padx=8, pady=(4, 4))

        self.prompt_text = scrolledtext.ScrolledText(tab, height=14, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        initial = self.settings.humanize_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self.prompt_text.insert("1.0", initial)

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btn_row, text="Reset to default prompt", command=self._reset_prompt).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Load saved prompt", command=self._load_saved_prompt).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Insert prose rules", command=self._insert_prose_rules).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Preview full prompt", command=self._preview_full_prompt).pack(side=tk.LEFT, padx=6)

    def _so_profile_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = [("none", "None — no SO style")]
        for p in list_profiles():
            uid = str(p.get("user_id"))
            label = p.get("label") or uid
            choices.append((uid, label))
        return choices

    def _refresh_so_profiles(self) -> None:
        choices = self._so_profile_choices()
        self._so_id_by_label = {label: uid for uid, label in choices}
        labels = [label for _, label in choices]
        self.so_style_combo["values"] = labels
        current = self.so_style_var.get()
        if current.isdigit():
            for uid, label in choices:
                if uid == current:
                    self.so_style_var.set(label)
                    return
        if self.so_style_var.get() not in labels and labels:
            self.so_style_var.set(labels[0])

    def _selected_so_user_id(self) -> str:
        val = self.so_style_var.get()
        if hasattr(self, "_so_id_by_label") and val in self._so_id_by_label:
            return self._so_id_by_label[val]
        if val.isdigit():
            return val
        return "none"

    def _run_so_pipeline(self) -> None:
        def work() -> None:
            try:
                from stackoverflow.fetch import run_fetch
                from stackoverflow.prepare import run_prepare
                from stackoverflow.profile import run_profile

                self._log("SO pipeline started (may take 30–60+ min for 100 users)…")
                run_fetch(user_count=100, max_answers_per_user=80, log=self._log)
                prep = run_prepare()
                self._log(f"Prepare: {prep}")
                prof = run_profile()
                self._log(f"Profiles: {prof}")
                self.root.after(0, self._refresh_so_profiles)
                self._log("SO pipeline finished.")
            except Exception as exc:  # noqa: BLE001
                self._log(f"SO pipeline error: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def _preview_full_prompt(self) -> None:
        base = self._prompt_from_ui() or DEFAULT_SYSTEM_PROMPT
        sid = self._selected_so_user_id()
        try:
            full = compose_with_style(base, sid if sid != "none" else None)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Preview", f"Could not build prompt: {exc}")
            return
        if not full.strip():
            full = "(Prompt is empty.)"

        win = tk.Toplevel(self.root)
        win.title("Full prompt preview")
        win.geometry("720x520")
        win.minsize(480, 320)
        win.transient(self.root)

        hdr = ttk.Frame(win, padding=(8, 8, 8, 0))
        hdr.pack(fill=tk.X)
        profile = sid if sid != "none" else "none"
        ttk.Label(hdr, text=f"SO profile: {profile}  |  {len(full)} characters").pack(anchor="w")

        body = ttk.Frame(win, padding=8)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        txt = scrolledtext.ScrolledText(
            body,
            wrap=tk.WORD,
            height=22,
            width=88,
            font=("Segoe UI", 10),
        )
        txt.grid(row=0, column=0, sticky="nsew")
        txt.insert("1.0", full)
        txt.configure(state=tk.DISABLED)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))
        win.lift()
        win.focus_force()

    def _prompt_from_ui(self) -> str:
        return self.prompt_text.get("1.0", tk.END).strip()

    def _reset_prompt(self) -> None:
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT)
        self._log("Prompt reset to default.")

    def _load_saved_prompt(self) -> None:
        text = self.settings.humanize_prompt.strip() or DEFAULT_SYSTEM_PROMPT
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", text)
        self._log("Prompt loaded from saved settings.")

    def _insert_prose_rules(self) -> None:
        body = self.prompt_text.get("1.0", tk.END)
        if "assessment answers that ALREADY" in body:
            self._log("Assessment prose rules already in prompt.")
            return
        self.prompt_text.insert(tk.END, "\n\n" + ASSESSMENT_PROSE_RULES)
        self._log("Assessment prose rules appended (for Q1/Q2-style answers only).")

    def _on_provider_changed(self, _event: object = None) -> None:
        if self.show_all_models_var.get():
            self._refresh_model_list()
            return
        prov = self.provider_var.get().strip() or "openai"
        mid = model_id_from_ui(self.model_var.get())
        self.model_var.set(default_display(prov, mid))
        self._refresh_model_list()

    def _on_model_selected(self, _event: object = None) -> None:
        prov = provider_for_model(self.model_var.get(), self.provider_var.get())
        self.provider_var.set(prov)

    def _on_listbox_model(self, _event: object = None) -> None:
        sel = self.model_listbox.curselection()
        if not sel:
            return
        value = self.model_listbox.get(sel[0])
        self.model_var.set(value)
        self.provider_var.set(provider_for_model(value, self.provider_var.get()))

    def _refresh_model_list(self) -> None:
        prov = None if self.show_all_models_var.get() else self.provider_var.get().strip() or "openai"
        self._all_model_displays = combobox_values(prov)
        self.model_combo["values"] = self._all_model_displays
        self._fill_model_listbox()

    def _fill_model_listbox(self) -> None:
        query = self.search_var.get().strip().lower()
        self.model_listbox.delete(0, tk.END)
        for line in self._all_model_displays:
            if not query or query in line.lower():
                self.model_listbox.insert(tk.END, line)

    def _fetch_models_remote(self) -> None:
        def work() -> None:
            try:
                extra = fetch_all_remote(
                    openai_key=self.api_key_var.get().strip(),
                    openai_base=self.base_url_var.get().strip() or None,
                    groq_key=self.groq_key_var.get().strip(),
                    openrouter_key=self.openrouter_key_var.get().strip(),
                    ollama_host=self.ollama_host_var.get().strip(),
                )
            except Exception as exc:  # noqa: BLE001
                self._log(f"Refresh failed: {exc}")
                return
            prov = None if self.show_all_models_var.get() else self.provider_var.get().strip()
            values = combobox_values(prov, extra)
            self.root.after(0, lambda: self._set_model_values(values))
            self._log(f"Model list updated: {len(values)} models (all vendors).")

        threading.Thread(target=work, daemon=True).start()

    def _set_model_values(self, values: list[str]) -> None:
        self._all_model_displays = values
        self.model_combo["values"] = values
        self._fill_model_listbox()

    def _build_hotkey_tab(self, tab: ttk.Frame) -> None:
        frm = ttk.LabelFrame(tab, text="Global hotkeys (run in tray)")
        frm.pack(fill=tk.X, padx=4, pady=4)
        ttk.Checkbutton(
            frm,
            text="Enable hotkeys",
            variable=self.hotkeys_enabled_var,
            command=self._apply_hotkeys,
        ).pack(anchor="w", padx=8, pady=4)
        ttk.Checkbutton(
            frm,
            text="Ctrl+T / Ctrl+Alt+T — type clipboard",
            variable=self.type_hk_var,
            command=self._apply_hotkeys,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(
            frm,
            text="Ctrl+Alt+H / Ctrl+Alt+J / Ctrl+Shift+H — humanize clipboard",
            variable=self.humanize_hk_var,
            command=self._apply_hotkeys,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Label(
            frm,
            text="Workflow: Ctrl+C → humanize (see Log, e.g. Ctrl+Alt+J) → click field → Ctrl+T or Ctrl+Alt+T. "
            "If humanize fails, set API key on Humanize tab and Save. Log shows Hotkey: humanize when the key fires.",
            wraplength=460,
        ).pack(anchor="w", padx=8, pady=8)

        tray = ttk.LabelFrame(tab, text="Tray")
        tray.pack(fill=tk.X, padx=4, pady=8)
        ttk.Checkbutton(tray, text="Start minimized to tray", variable=self.start_min_var).pack(
            anchor="w", padx=8, pady=2
        )
        ttk.Checkbutton(tray, text="Close window → tray (not exit)", variable=self.close_tray_var).pack(
            anchor="w", padx=8, pady=2
        )

    def _build_log_tab(self, tab: ttk.Frame) -> None:
        self.log_text = scrolledtext.ScrolledText(tab, height=16, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.root.after(200, self._drain_log_queue)

    def _parse_settings(self) -> AppSettings | None:
        try:
            delay_min = float(self.delay_min_var.get())
            delay_max = float(self.delay_max_var.get())
            s = AppSettings(
                delay=(delay_min + delay_max) / 2,
                delay_min=delay_min,
                delay_max=delay_max,
                hotkey_wait=float(self.hotkey_wait_var.get()),
                human_typing=self.human_var.get(),
                typo_rate=float(self.typo_var.get()),
                hotkeys_enabled=self.hotkeys_enabled_var.get(),
                type_hotkey=self.type_hk_var.get(),
                humanize_hotkey=self.humanize_hk_var.get(),
                provider=provider_for_model(
                    self.model_var.get(), self.provider_var.get().strip() or "openai"
                ),
                model=self.model_var.get().strip(),
                openai_api_key=self.api_key_var.get().strip(),
                openai_base_url=self.base_url_var.get().strip(),
                anthropic_api_key=self.anthropic_key_var.get().strip(),
                google_api_key=self.google_key_var.get().strip(),
                groq_api_key=self.groq_key_var.get().strip(),
                openrouter_api_key=self.openrouter_key_var.get().strip(),
                mistral_api_key=self.mistral_key_var.get().strip(),
                together_api_key=self.together_key_var.get().strip(),
                show_all_models=self.show_all_models_var.get(),
                humanize_prompt=self._prompt_from_ui(),
                humanize_strength=self.humanize_strength_var.get().strip() or "standard",
                so_style_user_id=self._selected_so_user_id(),
                ollama_host=self.ollama_host_var.get().strip(),
                ollama_model=(
                    model_id_from_ui(self.model_var.get())
                    if self.provider_var.get().strip() == "ollama"
                    else self.ollama_model_var.get().strip()
                ),
                start_minimized=self.start_min_var.get(),
                close_to_tray=self.close_tray_var.get(),
            )
        except ValueError:
            messagebox.showerror("Auto Typer", "Check numeric fields (delay, wait, typo rate).")
            return None
        if (
            s.typo_rate < 0
            or s.typo_rate > 1
            or s.delay_min < 0
            or s.delay_max < 0
            or s.hotkey_wait < 0
        ):
            messagebox.showerror("Auto Typer", "Delay, wait, and typo rate must be valid.")
            return None
        if s.delay_min > s.delay_max:
            messagebox.showerror("Auto Typer", "Delay min must be ≤ delay max.")
            return None
        return s

    def _current_settings(self) -> AppSettings:
        s = self._parse_settings()
        return s if s else self.settings

    def _save_settings(self) -> None:
        s = self._parse_settings()
        if s is None:
            return
        self.settings = s
        save_settings(s)
        s.apply_env()
        self._log("Settings saved.")
        self._apply_hotkeys()

    def _apply_hotkeys(self) -> None:
        s = self._parse_settings()
        if s:
            self.settings = s
            s.apply_env()
        self._hotkeys.refresh()
        self._log("Hotkeys refreshed.")

    def _manual_type(self) -> None:
        if self._typing:
            return
        body = self.text.get("1.0", tk.END)
        if not body.strip():
            messagebox.showwarning("Auto Typer", "Enter text first.")
            return
        s = self._parse_settings()
        if s is None:
            return
        try:
            wait = float(self.manual_wait_var.get())
        except ValueError:
            messagebox.showerror("Auto Typer", "Countdown must be a number.")
            return

        self._typing = True

        def worker() -> None:
            try:
                for i in range(int(wait), 0, -1):
                    self.root.after(0, lambda n=i: self.root.title(f"Auto Typer — {n}s…"))
                    threading.Event().wait(1)
                rest = wait - int(wait)
                if rest > 0:
                    threading.Event().wait(rest)
                self._log("Manual typing…")
                type_text(
                    body,
                    s.delay,
                    human=s.human_typing,
                    typo_rate=s.typo_rate,
                    delay_min=s.delay_min,
                    delay_max=s.delay_max,
                )
                self._log("Manual typing done.")
            except pyautogui.FailSafeException:
                self.root.after(0, lambda: messagebox.showinfo("Auto Typer", "Stopped (failsafe)."))
            finally:
                self._typing = False
                self.root.after(0, lambda: self.root.title("Auto Typer"))

        threading.Thread(target=worker, daemon=True).start()

    def _humanize_now(self) -> None:
        s = self._parse_settings()
        if s is None:
            return
        s.apply_env()

        def worker() -> None:
            try:
                self._log("Humanizing clipboard…")
                result = humanize_clipboard(
                    provider=s.effective_provider(),  # type: ignore[arg-type]
                    model=s.effective_model(),
                    system_prompt=s.effective_prompt(),
                    temperature=s.humanize_temperature(),
                )
                self._log(f"Done — {len(result)} chars on clipboard.")
            except Exception as exc:  # noqa: BLE001
                self._log(f"Humanize error: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _start_tray(self) -> None:
        if self._tray is not None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Open", self._show_from_tray, default=True),
            pystray.MenuItem("Save settings", lambda *_: self.root.after(0, self._save_settings)),
            pystray.MenuItem("Quit", lambda *_: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon("AutoTyper", _make_tray_image(), "Auto Typer", menu)

        def run_icon() -> None:
            assert self._tray is not None
            self._tray.run()

        self._tray_thread = threading.Thread(target=run_icon, daemon=True)
        self._tray_thread.start()

    def _hide_to_tray(self) -> None:
        self._start_tray()
        self.root.withdraw()
        self._log("Running in tray.")

    def _show_from_tray(self, *_args: object) -> None:
        self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        self.root.deiconify()
        self._apply_window_icon()
        self.root.lift()
        self.root.focus_force()

    def _on_close_window(self) -> None:
        if self.close_tray_var.get():
            self._hide_to_tray()
        else:
            self._quit()

    def _quit(self) -> None:
        self._hotkeys.stop()
        if self._tray is not None:
            self._tray.stop()
        self.root.quit()
        self.root.destroy()

    def _log_ollama_status(self) -> None:
        s = self._current_settings()
        if s.effective_provider() != "ollama":
            return
        host = s.ollama_host.rstrip("/") or "http://127.0.0.1:11434"
        model = s.effective_model() or "llama3.2"

        def work() -> None:
            from ollama_service import ensure_ollama_cpu

            ok, msg = ensure_ollama_cpu(host, model, force_restart=False)
            self._log(msg if ok else f"Ollama: {msg}")

        threading.Thread(target=work, daemon=True).start()

    def run(self) -> None:
        self._start_tray()
        self._log("Auto Typer ready. Close window to keep tray running.")
        self.root.after(400, self._log_ollama_status)
        self.root.mainloop()


def _is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def require_admin() -> None:
    """Stop unless this process is elevated. Hotkeys need that on Windows."""
    if _is_admin():
        return
    ctypes.windll.user32.MessageBoxW(
        None,
        "Auto Typer must be run as Administrator.\n\n"
        "Right-click AutoTyper.exe and choose Run as administrator.",
        "Auto Typer",
        0x10,
    )
    raise SystemExit(1)


def main() -> None:
    require_admin()
    TrayApp().run()


if __name__ == "__main__":
    main()
