#!/usr/bin/env python3
"""Transcribe podcast episode and translate to Traditional Chinese."""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import sys

import whisper
from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from glossary import apply_corrections, load_glossary, protect_terms, restore_terms

WORKDIR = Path(__file__).resolve().parent
AUDIO = WORKDIR / "episode.mp3"
META = {
    "title_en": "Turning Pokemon Cards into fx(hash) Grails - Interview with McLlama",
    "show": "Waiting To Be Signed",
    "hosts": "Will & Trinity",
    "guest": "McLlama (@PompousLL)",
    "spotify_url": "https://open.spotify.com/episode/19APff7PEWHjSz0APBH5Sb",
    "source_url": "https://podcasters.spotify.com/pod/show/waitingtobesigned/episodes/Turning-Pokemon-Cards-into-fxhash-Grails---Interview-with-McLlama-e3ki02q",
    "rss_audio_url": "https://anchor.fm/s/7c35eb94/podcast/play/121224730/https%3A%2F%2Fd3ctxlq1ktw2nl.cloudfront.net%2Fstaging%2F2026-5-9%2Fc90a5e0d-0d69-b52f-0e56-f9293aaec360.mp3",
    "published": "2026-06-09",
}


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
    return apply_corrections(zh, glossary["corrections"])


def build_segment_lines(segments: list[dict], lang: str) -> str:
    lines = []
    for seg in segments:
        ts = format_timestamp(seg["start"])
        text = seg["text"].strip()
        if text:
            lines.append(f"**[{ts}]** {text}")
    return "\n\n".join(lines)


def main() -> None:
    print("Loading Whisper model (base)...")
    model = whisper.load_model("base")

    print("Transcribing...")
    result = model.transcribe(
        str(AUDIO),
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

    (WORKDIR / "transcript_en.txt").write_text(full_en, encoding="utf-8")
    (WORKDIR / "transcript_en_segments.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"English transcript: {len(full_en)} chars, {len(segments)} segments")

    print("Translating to Traditional Chinese...")
    full_zh = translate_to_zh_tw(full_en)
    (WORKDIR / "transcript_zh-TW.txt").write_text(full_zh, encoding="utf-8")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    en_with_ts = build_segment_lines(segments, "en")
    md = f"""---
title: "{META['title_en']}"
show: "{META['show']}"
guest: "{META['guest']}"
hosts: "{META['hosts']}"
published: "{META['published']}"
spotify: "{META['spotify_url']}"
source: "{META['source_url']}"
language: zh-TW
generated_at: "{now}"
---

# {META['title_en']}

> **節目**：{META['show']}  
> **來賓**：{META['guest']}  
> **主持**：{META['hosts']}  
> **發布日期**：{META['published']}  
> **原始連結**：[Spotify]({META['spotify_url']}) · [節目頁]({META['source_url']})

## 中文全文

{full_zh}

---

## 英文逐字稿（含時間戳）

{en_with_ts}
"""

    (WORKDIR / "transcript_zh-TW.md").write_text(md, encoding="utf-8")
    (WORKDIR / "metadata.json").write_text(
        json.dumps({**META, "generated_at": now, "duration_sec": segments[-1]["end"] if segments else 0}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Done.")
    print(f"Outputs in {WORKDIR}")


if __name__ == "__main__":
    main()
