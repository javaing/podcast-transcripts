#!/usr/bin/env python3
"""Build static HTML pages for GitHub Pages."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from glossary import apply_corrections, load_glossary  # noqa: E402


def para(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in parts)


def build_episode_page(episode_dir: Path, out_dir: Path) -> Path:
    meta = json.loads((episode_dir / "metadata.json").read_text(encoding="utf-8"))
    glossary = load_glossary()
    zh = apply_corrections(
        (episode_dir / "transcript_zh-TW.txt").read_text(encoding="utf-8"),
        glossary["corrections"],
    )
    en = (episode_dir / "transcript_en.txt").read_text(encoding="utf-8")
    slug = episode_dir.name

    page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(meta['title_en'])} · 中文逐字稿</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#0f1115; --card:#171a21; --text:#e8eaed; --muted:#9aa0a6; --accent:#7aa2ff; --border:#2a2f3a; }}
    @media (prefers-color-scheme: light) {{ :root {{ --bg:#f6f7fb; --card:#fff; --text:#1f2328; --muted:#656d76; --accent:#0969da; --border:#d0d7de; }} }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.8; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
    .meta {{ color:var(--muted); margin-bottom:1.5rem; }}
    .links a {{ color:var(--accent); margin-right:1rem; }}
    article {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:1.5rem; }}
    h1 {{ font-size:1.6rem; line-height:1.3; }}
    h2 {{ margin-top:2rem; font-size:1.2rem; }}
    .note {{ font-size:.9rem; color:var(--muted); border-left:3px solid var(--border); padding-left:.9rem; margin:1rem 0 1.5rem; }}
    details {{ margin-top:2rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <p><a href="../index.html">← 返回文集首頁</a></p>
    <h1>{html.escape(meta['title_en'])}</h1>
    <p class="meta">{html.escape(meta['show'])} · {html.escape(meta['guest'])} · {html.escape(meta['published'])} · 約 {int(meta['duration_sec'] // 60)} 分鐘</p>
    <p class="links">
      <a href="{meta['spotify_url']}" target="_blank" rel="noopener">Spotify 原始連結</a>
      <a href="{meta['source_url']}" target="_blank" rel="noopener">節目頁</a>
    </p>
    <p class="note">此逐字稿由 AI 自動轉錄與翻譯產生。節目名、平台名、人名等專有名詞保留原文；其餘內容為機器翻譯，建議搭配原文連結閱讀。</p>
    <article>
      <h2>中文全文</h2>
      {para(zh)}
    </article>
    <details>
      <summary>展開英文原文（備查）</summary>
      <article>{para(en)}</article>
    </details>
  </div>
</body>
</html>"""

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    episodes_out = ROOT / "episodes"
    transcripts = ROOT / "transcripts"
    for episode_dir in sorted(transcripts.iterdir()):
        if episode_dir.is_dir() and (episode_dir / "transcript_zh-TW.txt").exists():
            path = build_episode_page(episode_dir, episodes_out)
            print(path)


if __name__ == "__main__":
    main()
