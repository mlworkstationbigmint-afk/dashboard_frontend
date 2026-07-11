"""Groq-backed auto-fill for analyst-call sections.

Admin uploads a pitch deck (.pptx); we extract its text and ask an LLM (Groq's free,
OpenAI-compatible API) to draft the headline summary (a short paragraph) plus a one-liner
for each section. The API key lives in st.secrets['groq']['api_key'] (git-ignored) — it is
NEVER hardcoded here, because this is a public repo.

    [groq]
    api_key = "gsk_..."
    # model = "llama-3.3-70b-versatile"   # optional override

Get a free key at https://console.groq.com (Create API Key).
"""
import io
import json

import streamlit as st

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_MAX_DECK_CHARS = 20000   # cap so a huge deck can't blow the request size


def _cfg() -> dict:
    try:
        return dict(st.secrets.get("groq", {}) or {})
    except Exception:
        return {}


def ai_ready() -> bool:
    """True when a Groq API key is configured (enables the auto-fill button)."""
    return bool(_cfg().get("api_key"))


def extract_pptx_text(data: bytes, filename: str = "") -> str:
    """Pull the readable text (titles, bodies, tables, speaker notes) from a .pptx.

    Raises on legacy .ppt (python-pptx only reads the modern XML format) or an empty deck.
    """
    if filename.lower().endswith(".ppt") and not filename.lower().endswith(".pptx"):
        raise ValueError("Legacy .ppt isn't supported — please re-save the deck as .pptx.")
    try:
        from pptx import Presentation
    except ImportError as e:
        raise RuntimeError("python-pptx isn't installed — add it to requirements.txt.") from e

    prs = Presentation(io.BytesIO(data))
    chunks = []
    for i, slide in enumerate(prs.slides, 1):
        parts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        parts.append(t)
            if getattr(shape, "has_table", False):
                try:
                    for row in shape.table.rows:
                        cells = [c.text.strip() for c in row.cells if c.text.strip()]
                        if cells:
                            parts.append(" | ".join(cells))
                except Exception:
                    pass
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                note = slide.notes_slide.notes_text_frame.text.strip()
                if note:
                    parts.append(f"(notes) {note}")
        except Exception:
            pass
        if parts:
            chunks.append(f"--- Slide {i} ---\n" + "\n".join(parts))

    text = "\n\n".join(chunks).strip()
    if not text:
        raise ValueError("No readable text found in the deck.")
    return text


def fill_analyst_sections(deck_text: str, sections: list) -> dict:
    """Ask the LLM to draft {"summary": <paragraph>, <section>: <one-liner>, ...} as JSON.

    `summary` is a short paragraph; every section value is a single concise sentence.
    Returns only the known keys (summary + the given sections), all stripped strings.
    """
    import requests

    cfg = _cfg()
    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError("No Groq API key configured (st.secrets['groq']['api_key']).")
    model = cfg.get("model", _DEFAULT_MODEL)

    deck_text = (deck_text or "")[:_MAX_DECK_CHARS]
    section_lines = "\n".join(f'- "{s}": ONE concise sentence (<= 25 words).' for s in sections)
    system = ("You are a steel-market analyst assistant. You read analyst-call pitch decks and "
              "write concise briefings. You always reply with a single valid JSON object and nothing else.")
    user = (
        "Read the analyst-call pitch-deck text below and produce a briefing for a dashboard card.\n\n"
        "Return a JSON object with these keys:\n"
        '- "summary": a short headline paragraph of 2-4 sentences capturing the overall market '
        "view (prices, demand, direction).\n"
        f"{section_lines}\n\n"
        "Rules: base every line ONLY on the deck's content; do not invent numbers. If a section "
        "has no relevant content in the deck, return an empty string for it. Keep each section "
        "value to a single line of plain text (no bullet characters, no labels).\n\n"
        "=== DECK TEXT ===\n" + deck_text
    )

    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(_ENDPOINT, headers={"Content-Type": "application/json",
                                             "Authorization": f"Bearer {api_key}"},
                         json=body, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Groq response: {json.dumps(data)[:300]}") from e

    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model did not return valid JSON: {text[:300]}") from e

    result = {"summary": str(out.get("summary", "")).strip()}
    for s in sections:
        result[s] = str(out.get(s, "")).strip()
    return result
