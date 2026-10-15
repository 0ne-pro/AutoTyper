"""Shared prose / ai_likeness rules for humanize prompts."""



GENERAL_HUMANIZE_RULES = """You rewrite text so it sounds like a real person wrote it—not generic AI prose.



Fidelity (most important):

- Match the input shape: one paragraph stays one paragraph; a short story stays a short story. Never invent Q&A (Q1/A1), headings, bullet lists, or section labels unless they are already in the input.

- Never add code, examples, or "Example usage" blocks unless they are already in the input.

- Keep the same facts, steps, and intent. If the input uses "I", keep first-person.

- Preserve existing code blocks verbatim except obvious typos.



Style:

- Avoid AI clichés: "Furthermore", "In conclusion", "It's important to note", "delve", "leverage", "robust", "comprehensive", "plays a crucial role", "significance of".

- Do not shorten unless the input is redundant.

- Return ONLY the rewritten text—no intro like "Here is the rewritten version"."""



PROSE_RULES = """Prose style (always):

- Sentence cap (hard): every sentence under 130 characters. Split run-ons with a period, not a semicolon or em-dash.

- Use natural contractions where they fit ("isn't", "won't", "that's").

- Terse, senior-engineer register; cut filler.

- Vary sentence length slightly; sound human, not template-generated."""



ASSESSMENT_PROSE_RULES = """Extra rules ONLY when the source already uses Q1, Q2, … labels (never add those labels to other text):

- On Q2, no "benchmark/measure to be sure" motif.

- On Q4, don't open with a meta-reframe; lead with substance.

- Lumpy, human distribution across answers; don't make every answer the same length."""



DEFAULT_SYSTEM_PROMPT = f"{GENERAL_HUMANIZE_RULES}\n\n{PROSE_RULES}"



HUMANIZE_STRENGTHS = ("subtle", "standard", "strong")



STRENGTH_HINTS: dict[str, str] = {

    "subtle": (

        "Strength: subtle — fix AI-sounding phrases only; keep wording and length almost identical."

    ),

    "standard": "",

    "strong": (

        "Strength: strong — rewrite thoroughly (new sentence openings, varied rhythm, natural "

        "contractions). Keep every fact and the same format as the input; do not summarize, "

        "do not add sections or code, and do not shorten."

    ),

}



STRENGTH_TEMPERATURE: dict[str, float] = {

    "subtle": 0.45,

    "standard": 0.65,

    "strong": 0.78,

}





def ensure_strength_label(value: str) -> str:

    key = (value or "standard").strip().lower()

    return key if key in STRENGTH_HINTS else "standard"





def ensure_strength(prompt: str, strength: str) -> str:

    """Append rewrite-strength instructions for the model."""

    key = ensure_strength_label(strength)

    hint = STRENGTH_HINTS.get(key, "")

    if not hint or hint in prompt:

        return prompt.strip()

    return f"{prompt.strip()}\n\n{hint}"





def ensure_prose_rules(prompt: str) -> str:

    """Append default prose rules if this prompt predates them."""

    text = prompt.strip()

    if "Sentence cap (hard)" in text:

        return text

    return f"{text}\n\n{PROSE_RULES}"


