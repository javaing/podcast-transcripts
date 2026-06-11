#!/usr/bin/env python3
"""Reformat an existing episode with speaker-aware line breaks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import build_episode_page, build_index
from dialogue import (
    assign_speakers,
    format_turns_markdown,
    format_turns_text,
    group_turns,
    load_segments,
    speaker_name_map,
)
from transcribe_episode import translate_to_zh_tw


def reformat_episode(episode_dir: Path, *, labeled: bool = False) -> None:
    meta = json.loads((episode_dir / "metadata.json").read_text(encoding="utf-8"))
    segments = load_segments(episode_dir / "transcript_en_segments.json")
    audio = episode_dir / "episode.mp3"
    if not audio.exists():
        raise FileNotFoundError(f"Missing audio: {audio}")

    labeled_segments = assign_speakers(audio, segments)
    (episode_dir / "transcript_en_segments.json").write_text(
        json.dumps(labeled_segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    turns = group_turns(labeled_segments)
    (episode_dir / "transcript_en_turns.json").write_text(
        json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    en_text = format_turns_text(turns)
    (episode_dir / "transcript_en.txt").write_text(en_text, encoding="utf-8")

    print("Translating dialogue turns...")
    zh_text = translate_to_zh_tw(en_text)
    (episode_dir / "transcript_zh-TW.txt").write_text(zh_text, encoding="utf-8")

    names = speaker_name_map(meta) if labeled else None
    en_md = format_turns_markdown(turns, names)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = f"""---
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

{zh_text}

---

## 英文逐字稿（含時間戳，說話者換行）

{en_md}
"""
    (episode_dir / "transcript_zh-TW.md").write_text(md, encoding="utf-8")
    meta["generated_at"] = now
    meta["dialogue_formatted"] = True
    (episode_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Reformatted: {episode_dir} ({len(turns)} turns)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_dir", nargs="?", help="Path to transcripts/<slug>")
    parser.add_argument("--all", action="store_true", help="Reformat all episodes")
    parser.add_argument("--labeled", action="store_true", help="Include host/guest labels in EN md")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    targets: list[Path] = []
    if args.all:
        targets = sorted((ROOT / "transcripts").iterdir())
        targets = [p for p in targets if p.is_dir() and (p / "transcript_en_segments.json").exists()]
    elif args.episode_dir:
        targets = [Path(args.episode_dir)]
    else:
        parser.error("Provide episode_dir or --all")

    for episode_dir in targets:
        reformat_episode(episode_dir, labeled=args.labeled)

    build_index(ROOT)
    for episode_dir in targets:
        if (episode_dir / "transcript_zh-TW.txt").exists():
            build_episode_page(episode_dir, ROOT / "episodes")

    if args.push:
        from process_url import git_push

        git_push(ROOT, "Reformat transcripts with speaker line breaks.")


if __name__ == "__main__":
    main()
