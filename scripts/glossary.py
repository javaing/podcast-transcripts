"""Shared glossary helpers for podcast transcript translation."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = ROOT / "glossary.json"


def load_glossary() -> dict:
    data = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    protected = sorted(set(data.get("protected_terms", [])), key=len, reverse=True)
    corrections = data.get("corrections", {})
    # Longer keys first to avoid partial replacement issues.
    correction_items = sorted(corrections.items(), key=lambda kv: len(kv[0]), reverse=True)
    return {
        "protected_terms": protected,
        "corrections": dict(correction_items),
    }


def protect_terms(text: str, terms: list[str]) -> tuple[str, dict[str, str]]:
    """Replace protected terms with placeholders before machine translation."""
    mapping: dict[str, str] = {}
    protected = text
    for term in terms:
        if not term or term not in protected:
            continue
        token = f"⟦{term}⟧"
        mapping[token] = term
        protected = protected.replace(term, token)
    return protected, mapping


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    restored = text
    # Longer tokens first in case one term is a substring of another.
    for token, term in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        restored = restored.replace(token, term)
    return restored


def fix_leaked_placeholders(text: str, terms: list[str]) -> str:
    """Repair numeric KEEP placeholders corrupted by machine translation."""
    import re

    def repl_numeric(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if 0 <= idx < len(terms):
            return terms[idx]
        return match.group(0)

    text = re.sub(r"\[\[KEEP_(\d+)\]\]", repl_numeric, text)
    text = re.sub(r"\[KEEP_(\d+)\]", repl_numeric, text)
    text = re.sub(r"⟦([^⟧]+)⟧", lambda m: m.group(1), text)
    return text


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    fixed = text
    for wrong, right in corrections.items():
        fixed = fixed.replace(wrong, right)
    return fixed


def to_traditional(text: str) -> str:
    try:
        import opencc

        return opencc.OpenCC("s2t").convert(text)
    except ImportError:
        return text


def normalize_transcript(text: str) -> str:
    glossary = load_glossary()
    text = fix_leaked_placeholders(text, glossary["protected_terms"])
    text = apply_corrections(text, glossary["corrections"])
    return to_traditional(text)
