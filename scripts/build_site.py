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

SHOWS_PATH = ROOT / "shows.json"


def load_shows_config() -> dict:
    data = json.loads(SHOWS_PATH.read_text(encoding="utf-8"))
    lookup: dict[str, dict] = {}
    for name, cfg in data.get("shows", {}).items():
        entry = {**cfg, "name": name}
        lookup[name] = entry
        for alias in cfg.get("aliases", []):
            lookup[alias] = entry
    return lookup


def match_show(show_name: str, lookup: dict[str, dict]) -> dict | None:
    return lookup.get(show_name.strip())


def icon_src(icon_path: str, depth: int = 0) -> str:
    prefix = "../" * depth
    return f"{prefix}{icon_path}"


def show_icon_html(show_cfg: dict, depth: int = 0) -> str:
    return (
        f'<img class="show-icon" src="{icon_src(show_cfg["icon"], depth)}" '
        f'alt="{html.escape(show_cfg["name"])}" width="52" height="52" loading="lazy" />'
    )


def show_styles_css() -> str:
    lookup = load_shows_config()
    blocks: list[str] = []
    seen: set[str] = set()
    for cfg in lookup.values():
        cls = cfg.get("card_class", "")
        if not cls or cls in seen:
            continue
        seen.add(cls)
        accent = cfg.get("accent", "#7aa2ff")
        accent2 = cfg.get("accent2", accent)
        page_cls = cfg.get("page_class", cls.replace("card", "page"))
        blocks.append(
            f"""
    .{cls} {{
      border-left: 4px solid {accent};
      background: linear-gradient(135deg, color-mix(in srgb, var(--card) 92%, {accent2} 8%), var(--card));
    }}
    .{page_cls} .note {{ border-left-color: {accent}; }}
    .show-name--{cls.replace('card--', '')} {{ color: {accent}; font-weight: 600; }}"""
        )
    return "".join(blocks)


def para(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts and text.strip():
        parts = [text.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in parts)


def build_episode_page(episode_dir: Path, out_dir: Path, show_lookup: dict[str, dict]) -> Path:
    meta = json.loads((episode_dir / "metadata.json").read_text(encoding="utf-8"))
    glossary = load_glossary()
    zh = apply_corrections(
        (episode_dir / "transcript_zh-TW.txt").read_text(encoding="utf-8"),
        glossary["corrections"],
    )
    en = (episode_dir / "transcript_en.txt").read_text(encoding="utf-8")
    slug = episode_dir.name
    show_cfg = match_show(meta.get("show", ""), show_lookup)
    page_class = show_cfg.get("page_class", "") if show_cfg else ""
    show_key = show_cfg.get("card_class", "").replace("card--", "") if show_cfg else ""

    show_label = html.escape(meta["show"])
    if show_cfg:
        show_label = f'<span class="show-name show-name--{show_key}">{html.escape(meta["show"])}</span>'

    title_block = f"""<div class="title-row">
      {show_icon_html(show_cfg, 1) if show_cfg else ""}
      <div>
        <h1>{html.escape(meta['title_en'])}</h1>
        <p class="meta">{show_label} · {html.escape(meta['guest'])} · {html.escape(meta['published'])} · 約 {int(meta['duration_sec'] // 60)} 分鐘</p>
      </div>
    </div>"""

    page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(meta['title_en'])} · 中文逐字稿</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg:#0f1115; --card:#171a21; --text:#e8eaed; --muted:#9aa0a6; --accent:#7aa2ff; --border:#2a2f3a;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{ --bg:#f6f7fb; --card:#fff; --text:#1f2328; --muted:#656d76; --accent:#0969da; --border:#d0d7de; }}
    }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.8; }}
    .wrap {{ max-width:820px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
    .title-row {{ display:flex; gap:1rem; align-items:flex-start; margin-bottom:1.5rem; }}
    .show-icon {{ width:52px; height:52px; border-radius:10px; flex-shrink:0; box-shadow:0 2px 10px rgba(0,0,0,.18); }}
    .meta {{ color:var(--muted); margin:0; }}
    .links a {{ color:var(--accent); margin-right:1rem; }}
    article {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:1.5rem; }}
    h1 {{ font-size:1.6rem; line-height:1.3; margin:0 0 .35rem; }}
    h2 {{ margin-top:2rem; font-size:1.2rem; }}
    .note {{ font-size:.9rem; color:var(--muted); border-left:3px solid var(--border); padding-left:.9rem; margin:1rem 0 1.5rem; }}
    details {{ margin-top:2rem; }}
    {show_styles_css()}
  </style>
</head>
<body class="{page_class}">
  <div class="wrap">
    <p><a href="../index.html">← 返回文集首頁</a></p>
    {title_block}
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


INDEX_STYLE = """
    :root {
      color-scheme: light dark;
      --bg: #0f1115;
      --card: #171a21;
      --text: #e8eaed;
      --muted: #9aa0a6;
      --accent: #7aa2ff;
      --border: #2a2f3a;
    }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f6f7fb;
        --card: #ffffff;
        --text: #1f2328;
        --muted: #656d76;
        --accent: #0969da;
        --border: #d0d7de;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.7;
    }
    .wrap { max-width: 820px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
    .hero {
      display: flex;
      gap: 1rem;
      align-items: center;
      margin-bottom: 0.5rem;
      flex-wrap: wrap;
    }
    .hero-icons { display: flex; gap: 0.5rem; align-items: center; }
    .hero-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
    }
    h1 { font-size: 1.8rem; margin: 0; }
    .subtitle { color: var(--muted); margin-bottom: 2rem; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1rem;
    }
    .card-head {
      display: flex;
      gap: 0.9rem;
      align-items: flex-start;
      margin-bottom: 0.75rem;
    }
    .show-icon {
      width: 48px;
      height: 48px;
      border-radius: 10px;
      flex-shrink: 0;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
    }
    .card h2 { margin: 0 0 0.35rem; font-size: 1.15rem; line-height: 1.35; }
    .meta { color: var(--muted); font-size: 0.92rem; margin: 0 0 0.75rem; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .links { display: flex; gap: 1rem; flex-wrap: wrap; font-size: 0.95rem; }
    footer { margin-top: 2rem; color: var(--muted); font-size: 0.85rem; }
"""


def load_all_episodes(root: Path) -> list[dict]:
    episodes: list[dict] = []
    transcripts = root / "transcripts"
    for episode_dir in transcripts.iterdir():
        meta_path = episode_dir / "metadata.json"
        if episode_dir.is_dir() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["slug"] = episode_dir.name
            episodes.append(meta)
    episodes.sort(key=lambda m: m.get("published", ""), reverse=True)
    return episodes


def hero_icons_html(episodes: list[dict], show_lookup: dict[str, dict]) -> str:
    seen: set[str] = set()
    icons: list[str] = []
    for meta in episodes:
        cfg = match_show(meta.get("show", ""), show_lookup)
        if not cfg or cfg["name"] in seen:
            continue
        seen.add(cfg["name"])
        icons.append(
            f'<img class="hero-icon" src="{cfg["icon"]}" alt="{html.escape(cfg["name"])}" width="48" height="48" />'
        )
    return "\n      ".join(icons)


def build_index(root: Path, show_lookup: dict[str, dict]) -> Path:
    episodes = load_all_episodes(root)
    cards = []
    for meta in episodes:
        slug = meta["slug"]
        minutes = int(meta.get("duration_sec", 0) // 60) or "?"
        guest = html.escape(meta.get("guest", ""))
        show_cfg = match_show(meta.get("show", ""), show_lookup)
        show_key = show_cfg.get("card_class", "").replace("card--", "") if show_cfg else ""
        show_label = html.escape(meta["show"])
        if show_cfg:
            show_label = f'<span class="show-name show-name--{show_key}">{html.escape(meta["show"])}</span>'
        card_class = f"card {show_cfg['card_class']}" if show_cfg else "card"
        head_icon = f"\n        {show_icon_html(show_cfg, 0)}" if show_cfg else ""
        cards.append(
            f"""    <article class="{card_class}">
      <div class="card-head">{head_icon}
        <div>
          <h2>{html.escape(meta['title_en'])}</h2>
          <p class="meta">{show_label} · {guest} · {html.escape(meta.get('published', ''))} · 約 {minutes} 分鐘</p>
        </div>
      </div>
      <div class="links">
        <a href="episodes/{slug}.html">閱讀中文逐字稿</a>
        <a href="{meta['spotify_url']}" target="_blank" rel="noopener">Spotify 原始連結</a>
        <a href="{meta['source_url']}" target="_blank" rel="noopener">節目頁</a>
      </div>
    </article>"""
        )

    page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Podcast 中文逐字稿文集</title>
  <style>{INDEX_STYLE}{show_styles_css()}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="hero-icons">
      {hero_icons_html(episodes, show_lookup)}
      </div>
      <h1>Podcast 中文逐字稿</h1>
    </div>
    <p class="subtitle">英文 podcast 轉錄與翻譯，保留原始連結。節目名、平台名、人名等專有名詞不翻譯。</p>

{chr(10).join(cards)}

    <footer>
      本站內容由 AI 語音轉錄與翻譯產生，僅供個人學習參考。版權屬於原節目製作人。
    </footer>
  </div>
</body>
</html>"""

    out = root / "index.html"
    out.write_text(page, encoding="utf-8")
    print(out)
    return out


def main() -> None:
    show_lookup = load_shows_config()
    episodes_out = ROOT / "episodes"
    transcripts = ROOT / "transcripts"
    for episode_dir in sorted(transcripts.iterdir()):
        if episode_dir.is_dir() and (episode_dir / "transcript_zh-TW.txt").exists():
            path = build_episode_page(episode_dir, episodes_out, show_lookup)
            print(path)
    build_index(ROOT, show_lookup)


if __name__ == "__main__":
    main()
