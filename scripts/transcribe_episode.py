"""Whisper transcription + glossary-aware translation for one episode."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import whisper
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound

from dialogue import assign_speakers, format_turns_markdown, format_turns_text, group_turns
from glossary import (
    apply_corrections,
    fix_leaked_placeholders,
    load_glossary,
    protect_terms,
    restore_terms,
)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def chunk_text(text: str, max_len: int = 4500) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        if end < len(text):
            split_at = text.rfind(". ", start, end)
            if split_at == -1 or split_at <= start + 500:
                split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def _translate_chunk(translator: GoogleTranslator, text: str) -> str:
    text = text.strip()
    if not text:
        return ""

    for attempt in range(3):
        try:
            return translator.translate(text)
        except TranslationNotFound:
            if len(text) > 200:
                mid = len(text) // 2
                split_at = text.rfind(" ", max(0, mid - 120), min(len(text), mid + 120))
                if split_at <= 0:
                    split_at = mid
                left = _translate_chunk(translator, text[:split_at])
                right = _translate_chunk(translator, text[split_at:].strip())
                return f"{left} {right}".strip()
            return text
        except Exception:
            if attempt == 2:
                raise
            print(f"    retry after error ({type(translator).__name__})", flush=True)
            time.sleep(2 * (attempt + 1))
    return text


def translate_to_zh_tw(text: str) -> str:
    glossary = load_glossary()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return ""

    translator = GoogleTranslator(source="en", target="zh-TW")
    translated_paragraphs: list[str] = []
    total_chunks = 0
    for i, para in enumerate(paragraphs, 1):
        if i == 1 or i % 25 == 0 or i == len(paragraphs):
            print(f"  translating paragraph {i}/{len(paragraphs)}", flush=True)
        protected, mapping = protect_terms(para, glossary["protected_terms"])
        parts = chunk_text(protected)
        total_chunks += len(parts)
        translated_parts: list[str] = []
        for part in parts:
            translated_parts.append(_translate_chunk(translator, part))
            time.sleep(0.15)
        zh_para = restore_terms(" ".join(translated_parts), mapping)
        zh_para = fix_leaked_placeholders(zh_para, glossary["protected_terms"])
        translated_paragraphs.append(apply_corrections(zh_para, glossary["corrections"]))

    print(f"  translated {len(paragraphs)} paragraphs ({total_chunks} API chunks)", flush=True)
    return "\n\n".join(translated_paragraphs)


def build_markdown(meta: dict, zh: str, turns: list[dict], en_with_ts: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""---
title: "{meta['title_en']}"
show: "{meta['show']}"
guest: "{meta['guest']}"
hosts: "{meta['hosts']}"
published: "{meta['published']}"
spotify: "{meta['spotify_url']}"
source: "{meta['source_url']}"
language: zh-TW
generated_at: "{now}"
---

# {meta['title_en']}

> **節目**：{meta['show']}  
> **來賓**：{meta['guest']}  
> **主持**：{meta['hosts']}  
> **發布日期**：{meta['published']}  
> **原始連結**：[Spotify]({meta['spotify_url']}) · [節目頁]({meta['source_url']})

## 中文全文

{zh}

---

## 英文逐字稿（含時間戳，說話者換行）

{en_with_ts}
"""


def transcribe_episode(episode_dir: Path, meta: dict, model_name: str = "base") -> dict:
    audio = episode_dir / "episode.mp3"
    if not audio.exists():
        raise FileNotFoundError(f"Missing audio file: {audio}")

    print(f"Loading Whisper model ({model_name})...")
    model = whisper.load_model(model_name)

    print("Transcribing...")
    result = model.transcribe(
        str(audio),
        language="en",
        task="transcribe",
        verbose=False,
        fp16=False,
    )

    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    ]
    labeled_segments = assign_speakers(audio, segments)
    turns = group_turns(labeled_segments)
    full_en = format_turns_text(turns)

    (episode_dir / "transcript_en.txt").write_text(full_en, encoding="utf-8")
    (episode_dir / "transcript_en_segments.json").write_text(
        json.dumps(labeled_segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (episode_dir / "transcript_en_turns.json").write_text(
        json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"English transcript: {len(full_en)} chars, {len(turns)} dialogue turns")

    print("Translating to Traditional Chinese...")
    full_zh = translate_to_zh_tw(full_en)
    (episode_dir / "transcript_zh-TW.txt").write_text(full_zh, encoding="utf-8")
    en_with_ts = format_turns_markdown(turns)
    (episode_dir / "transcript_zh-TW.md").write_text(
        build_markdown(meta, full_zh, turns, en_with_ts), encoding="utf-8"
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    duration_sec = labeled_segments[-1]["end"] if labeled_segments else meta.get("duration_sec", 0)
    out_meta = {**meta, "generated_at": now, "duration_sec": duration_sec}
    (episode_dir / "metadata.json").write_text(
        json.dumps(out_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Done: {episode_dir}")
    return out_meta
