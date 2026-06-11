#!/usr/bin/env python3
"""Fix an existing translated episode using glossary corrections."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from glossary import apply_corrections, load_glossary  # noqa: E402


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def build_md(meta: dict, zh: str, segments: list[dict]) -> str:
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


def main(episode_dir: Path) -> None:
    glossary = load_glossary()
    zh_path = episode_dir / "transcript_zh-TW.txt"
    zh_raw = zh_path.read_text(encoding="utf-8")
    zh_fixed = apply_corrections(zh_raw, glossary["corrections"])
    zh_path.write_text(zh_fixed, encoding="utf-8")

    segments = json.loads((episode_dir / "transcript_en_segments.json").read_text(encoding="utf-8"))
    meta = json.loads((episode_dir / "metadata.json").read_text(encoding="utf-8"))
    (episode_dir / "transcript_zh-TW.md").write_text(build_md(meta, zh_fixed, segments), encoding="utf-8")
    print(f"Fixed: {episode_dir}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "transcripts" / "wtbs-mcllama"
    main(target)
