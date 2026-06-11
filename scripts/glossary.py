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
    for idx, term in enumerate(terms):
        if not term or term not in protected:
            continue
        token = f"[[KEEP_{idx}]]"
        mapping[token] = term
        protected = protected.replace(term, token)
    return protected, mapping


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for token, term in mapping.items():
        restored = restored.replace(token, term)
    return restored


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    fixed = text
    for wrong, right in corrections.items():
        fixed = fixed.replace(wrong, right)
    return fixed


def normalize_transcript(text: str) -> str:
    glossary = load_glossary()
    return apply_corrections(text, glossary["corrections"])
