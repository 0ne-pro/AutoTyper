# Auto Typer

A Windows desktop tool that does two things:

1. **Types text for you** into whatever window has focus (Notepad, browser, chat, etc.), with human-like timing: variable speed, pauses at punctuation, and occasional typos that it backspaces and corrects.
2. **Humanizes text** by rewriting the wording with an LLM so it reads like a person wrote it. It supports a local model (Ollama, free) or cloud providers, and can imitate the style of public Stack Overflow answerers.

The two combine into one workflow: copy text, press **Ctrl+Shift+H** to rewrite it, then press **Ctrl+T** to type it out.

## How it works

```
Clipboard --Ctrl+Shift+H--> humanize_engine --> Clipboard
                             (Ollama / OpenAI / Claude / Gemini / ...)
                             prompt = base rules + strength + optional SO style profile

Clipboard --Ctrl+T--> human_type --> pyautogui keystrokes into focused window
```

- **Typing** ([human_type.py](human_type.py)): sends keystrokes with pyautogui. In human mode each key waits a random delay in `delay_min`-`delay_max`, with longer pauses at spaces, punctuation and newlines, plus QWERTY-neighbor typos (rate `typo_rate`) that get backspaced. Robot mode uses a fixed delay and no typos.
- **Humanizing** ([humanize_engine.py](humanize_engine.py)): sends the text plus a system prompt to the chosen provider and strips any "Here's the rewrite" preamble from the reply. If a cloud provider is selected but has no API key, it falls back to Ollama. Ollama is started on CPU by [ollama_service.py](ollama_service.py) to avoid CUDA crashes on some Windows GPUs.
- **Prompts** ([prose_rules.py](prose_rules.py)): fidelity and style rules (keep the input's shape and facts, avoid AI cliches, sentence length limits, contractions) with selectable strengths.
- **Stack Overflow style profiles** ([stackoverflow/](stackoverflow/)): a pipeline that fetches public answers (CC BY-SA) from top answerers, cleans them, and builds a style card per user (sentence length, hedging, typical openers). The chosen card is appended to the humanize prompt. No model training is involved.
- **Hotkeys** ([hotkey_service.py](hotkey_service.py), [win_hotkeys.py](win_hotkeys.py)): global hotkeys via Windows `RegisterHotKey`, with the `keyboard` library as a fallback. Driven by saved settings.
- **GUI + tray** ([tray_gui.py](tray_gui.py), launched by [gui.py](gui.py)): Tkinter control panel plus a pystray tray icon.
- **Settings** ([settings.py](settings.py)): stored in `%LOCALAPPDATA%\AutoTyper\settings.json`. API keys entered in the GUI are pushed into environment variables at runtime.

## Project layout

| Path | Purpose |
|------|---------|
| `gui.py`, `tray_gui.py` | Main GUI and system tray |
| `ollama_service.py` | Starts Ollama in CPU mode when needed (called automatically) |
| `type_text.py` | CLI typer |
| `hotkey.py` | Standalone Ctrl+T listener (`--humanize-hotkey` adds humanize) |
| `humanize.py`, `humanize_hotkey.py` | CLI humanizer and standalone Ctrl+Shift+H listener |
| `human_type.py` | Human-like typing engine |
| `humanize_engine.py` | LLM calls for all providers |
| `model_catalog.py` | Model lists per vendor, plus live fetch (OpenAI, OpenRouter, Ollama) |
| `prose_rules.py` | Prompt rules and strengths |
| `hotkey_service.py`, `win_hotkeys.py` | Global hotkey handling |
| `settings.py` | Persistent settings |
| `assets/` | Window and tray icon (mark only) |
| `stackoverflow/` | Fetch, clean and profile Stack Overflow answers |
| `data/so/` | `styles/` (profiles, committed), `raw/` and `processed/` (cached, gitignored) |
| `answer.txt` | Sample text to humanize |

## Setup

Requires Windows and Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

**Local humanize (free):** install [Ollama](https://ollama.com), run `ollama pull llama3.2`, and keep it running. It is used automatically when no cloud key is set.

**Cloud providers:** put keys in `.env` or in the GUI's Humanize tab. Supported: OpenAI, Anthropic (Claude), Google Gemini, Groq, OpenRouter, Mistral, Together, Ollama.

| `.env` | Meaning |
|--------|---------|
| `HUMANIZE_PROVIDER` | Default `ollama` |
| `OLLAMA_HOST` / `OLLAMA_MODEL` | Default `http://127.0.0.1:11434` / `llama3.2` |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | OpenAI or compatible endpoint |
| `ANTHROPIC_API_KEY` | Claude |
| `HUMANIZE_MODEL` | Model id for the chosen cloud provider |
| `STACKEXCHANGE_KEY` | Optional, raises Stack Exchange API quota |

## Quick start

With the virtual environment active:

```powershell
python gui.py
```

Humanize checks that Ollama is running and starts it in CPU mode if needed. To start it by hand: `python ollama_service.py --force`.

## GUI and tray

Opens the control panel and a tray icon (letter T). With **Close window to tray** checked, closing the window keeps the app running in the tray.

| Tab | What you control |
|-----|------------------|
| **Typing** | Manual type box, delay min/max (default 0.10-0.15 s), hotkey wait (default 2 s), typo rate, human-like on/off |
| **Humanize** | One searchable list of models across all vendors, **Refresh all**, API keys |
| **Prompt** | Base prompt, prose rules and strength, Stack Overflow profile, preview, **Build SO data** |
| **Hotkeys** | Enable Ctrl+T and Ctrl+Shift+H while in the tray, **Apply hotkeys** |
| **Log** | Hotkey and action messages |

**Save settings** persists changes. **Apply hotkeys** reloads bindings.

## Hotkeys

| Key | Action |
|-----|--------|
| **Ctrl+T** (or Ctrl+Alt+T) | Type the clipboard contents into the focused window |
| **Ctrl+Shift+H** (also Ctrl+Alt+H, Ctrl+Alt+J, Ctrl+Alt+Shift+H) | Humanize the clipboard in place |
| **Ctrl+Shift+Q** | Quit the standalone listeners |

Typical use: select text, **Ctrl+C**, **Ctrl+Shift+H**, click the target field, **Ctrl+T**.

If hotkeys do nothing, run `gui.py` as Administrator, try **Ctrl+Alt+H** when another app owns Ctrl+Shift+H, check the **Log** tab, and click **Apply hotkeys**.

## Command line

```powershell
python type_text.py "Hello, world!"
Get-Content notes.txt | python type_text.py
python hotkey.py                              # Ctrl+T listener
python hotkey.py --humanize-hotkey            # plus humanize hotkey
python humanize.py answer.txt -o answer_human.txt
python humanize.py --clipboard
python humanize_hotkey.py                     # Ctrl+Shift+H listener
```

`type_text.py` options:

- `-w 5` wait 5 seconds before typing (default 3)
- `--instant` skip the countdown
- `-d 0.12` fixed delay in robot mode
- `--robot` fixed delay, no typos
- `--typo-rate 0.03` typo frequency (default 0.025)

Human-like typing is on by default.

## Stack Overflow style profiles

**GUI:** Prompt tab -> **Build SO data (100 users)** (first run takes about 30-60 minutes) -> pick a profile -> **Save settings**.

**CLI:**

```powershell
python -m stackoverflow.pipeline --quick                         # 5 users, 15 answers
python -m stackoverflow.pipeline --users 100 --max-answers 80
python -m stackoverflow.pipeline --user-ids-file data\so\user_ids.txt
```

The pipeline runs three stages: **fetch** (top answerers for a tag, default `python`, saved to `data/so/raw/`), **prepare** (strip HTML, keep code blocks, filter by score and length, saved to `data/so/processed/`), **profile** (style cards in `data/so/styles/`, indexed by `index.json`). Stages can be skipped with `--skip-fetch`, `--skip-prepare`, `--skip-profile`.

## Safety

Move the mouse to any **corner of the screen** to stop typing immediately (PyAutoGUI failsafe).
