"""Whisper transcription + glossary-aware translation for one episode."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import whisper
from deep_translator import GoogleTranslator

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


def translate_to_zh_tw(text: str) -> str:
    glossary = load_glossary()
    protected, mapping = protect_terms(text, glossary["protected_terms"])
    translator = GoogleTranslator(source="en", target="zh-TW")
    parts = chunk_text(protected)
    translated: list[str] = []
    for i, part in enumerate(parts, 1):
        print(f"  translating chunk {i}/{len(parts)} ({len(part)} chars)")
        for attempt in range(3):
            try:
                translated.append(translator.translate(part))
                break
            except Exception as exc:
                if attempt == 2:
                    raise
                print(f"    retry after error: {exc}")
                time.sleep(2 * (attempt + 1))
    zh = restore_terms("\n\n".join(translated), mapping)
    zh = fix_leaked_placeholders(zh, glossary["protected_terms"])
    return apply_corrections(zh, glossary["corrections"])


def build_markdown(meta: dict, zh: str, segments: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    en_with_ts = "\n\n".join(
        f"**[{format_timestamp(seg['start'])}]** {seg['text']}"
        for seg in segments
        if seg.get("text", "").strip()
    )
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

## 英文逐字稿（含時間戳）

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
    full_en = result.get("text", "").strip()

    (episode_dir / "transcript_en.txt").write_text(full_en, encoding="utf-8")
    (episode_dir / "transcript_en_segments.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"English transcript: {len(full_en)} chars, {len(segments)} segments")

    print("Translating to Traditional Chinese...")
    full_zh = translate_to_zh_tw(full_en)
    (episode_dir / "transcript_zh-TW.txt").write_text(full_zh, encoding="utf-8")
    (episode_dir / "transcript_zh-TW.md").write_text(
        build_markdown(meta, full_zh, segments), encoding="utf-8"
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    duration_sec = segments[-1]["end"] if segments else meta.get("duration_sec", 0)
    out_meta = {**meta, "generated_at": now, "duration_sec": duration_sec}
    (episode_dir / "metadata.json").write_text(
        json.dumps(out_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Done: {episode_dir}")
    return out_meta
