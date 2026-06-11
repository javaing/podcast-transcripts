"""Resolve podcast episode URLs to RSS audio and metadata."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

ITUNES_NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}

SHOW_FEEDS = {
    "waitingtobesigned": "https://anchor.fm/s/7c35eb94/podcast/rss",
    "kaloh": "https://api.substack.com/feed/podcast/357385/s/72330.rss",
}

SHOW_HOSTS = {
    "waitingtobesigned": "Will & Trinity",
    "kaloh": "Kaloh",
}

ROOT = Path(__file__).resolve().parent.parent


def slugify(text: str, max_len: int = 48) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].strip("-")


def extract_episode_key(url: str) -> str | None:
    patterns = [
        r"/episodes/[^/]+-([a-z0-9]+)(?:/|$)",
        r"open\.spotify\.com/episode/([A-Za-z0-9]+)",
        r"episode/([A-Za-z0-9]+)",
    ]
    for pat in patterns:
        match = re.search(pat, url, re.I)
        if match:
            return match.group(1)
    return None


def extract_show_key(url: str) -> str | None:
    match = re.search(r"/pod(?:cast)?/(?:profile|show)/([^/]+)", url, re.I)
    return match.group(1).lower() if match else None


def fetch_rss_items(feed_url: str) -> tuple[str, list[dict]]:
    req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    channel = root.find("channel")
    show = channel.findtext("title", "Unknown Show") if channel is not None else "Unknown Show"
    items: list[dict] = []
    for item in root.findall(".//item"):
        enclosure = item.find("enclosure")
        duration_el = item.find("itunes:duration", ITUNES_NS)
        duration_sec = 0
        if duration_el is not None and duration_el.text:
            parts = duration_el.text.strip().split(":")
            try:
                nums = [int(p) for p in parts]
                if len(nums) == 3:
                    duration_sec = nums[0] * 3600 + nums[1] * 60 + nums[2]
                elif len(nums) == 2:
                    duration_sec = nums[0] * 60 + nums[1]
                else:
                    duration_sec = nums[0]
            except ValueError:
                duration_sec = 0
        pub_raw = item.findtext("pubDate", "")
        try:
            published = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d") if pub_raw else ""
        except (TypeError, ValueError, OverflowError):
            published = ""
        items.append(
            {
                "title": item.findtext("title", "").strip(),
                "link": item.findtext("link", "").strip(),
                "audio_url": enclosure.get("url", "") if enclosure is not None else "",
                "published": published,
                "duration_sec": duration_sec,
                "description": re.sub(r"<[^>]+>", " ", item.findtext("description", "") or "").strip(),
            }
        )
    return show, items


def parse_guest(title: str) -> str:
    paren = re.search(r"\(([^)]+)\)", title)
    if paren:
        return paren.group(1).strip()
    match = re.search(r"Interview with\s+(.+)$", title, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"with\s+(.+)$", title, re.I)
    return match.group(1).strip() if match else ""


def spotify_oembed(url: str) -> str | None:
    try:
        oembed = (
            "https://open.spotify.com/oembed?url="
            + urllib.parse.quote(url, safe="")
        )
        with urllib.request.urlopen(oembed, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        iframe = data.get("iframe_url", "")
        match = re.search(r"/embed/episode/([^?]+)", iframe)
        if match:
            return f"https://open.spotify.com/episode/{match.group(1)}"
    except Exception:
        return None
    return None


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _title_match_score(hint: str, title: str) -> int:
    hint_n = _normalize_title(hint)
    title_n = _normalize_title(title)
    if hint_n == title_n:
        return 10_000
    if hint_n in title_n or title_n in hint_n:
        return 5_000 + min(len(hint_n), len(title_n))
    hint_words = {w for w in hint_n.split() if len(w) > 3}
    title_words = set(title_n.split())
    return len(hint_words & title_words)


def _match_rss_item(items: list[dict], episode_key: str | None, title_hint: str | None) -> dict | None:
    if episode_key:
        for item in items:
            if episode_key in item["link"]:
                return item
    if not title_hint:
        return None

    best_score = 0
    best_item: dict | None = None
    for item in items:
        score = _title_match_score(title_hint, item["title"])
        if score > best_score:
            best_score = score
            best_item = item

    if best_item is None:
        return None
    hint_words = {w for w in _normalize_title(title_hint).split() if len(w) > 3}
    min_overlap = max(4, len(hint_words) * 2 // 3)
    if best_score >= 5_000 or best_score >= min_overlap:
        return best_item
    return None


def _resolve_from_feeds(
    episode_key: str | None,
    title_hint: str | None,
    preferred_show_key: str | None = None,
) -> tuple[str, str, list[dict], dict]:
    feed_order = list(SHOW_FEEDS.items())
    if preferred_show_key:
        feed_order.sort(key=lambda kv: 0 if kv[0] == preferred_show_key else 1)

    best: tuple[int, str, str, list[dict], dict] | None = None
    for key, rss in feed_order:
        candidate_show, candidate_items = fetch_rss_items(rss)
        match = _match_rss_item(candidate_items, episode_key, title_hint)
        if not match:
            continue
        score = _title_match_score(title_hint or "", match["title"]) if title_hint else 1
        if episode_key and episode_key in match["link"]:
            score += 20_000
        if best is None or score > best[0]:
            best = (score, key, candidate_show, candidate_items, match)

    if best is None:
        raise ValueError(
            f"Episode not found in RSS for key: {episode_key or title_hint}"
        )
    _, show_key, show_name, items, match = best
    return show_key, show_name, items, match


def resolve_episode(url: str) -> dict:
    episode_key = extract_episode_key(url)
    show_key = extract_show_key(url)

    title_hint = None
    if not show_key and "open.spotify.com/episode/" in url:
        try:
            oembed = (
                "https://open.spotify.com/oembed?url="
                + urllib.parse.quote(url, safe="")
            )
            with urllib.request.urlopen(oembed, timeout=15) as resp:
                title_hint = json.loads(resp.read().decode()).get("title")
        except Exception:
            title_hint = None

    if show_key and show_key in SHOW_FEEDS:
        show_name, items = fetch_rss_items(SHOW_FEEDS[show_key])
        match = _match_rss_item(items, episode_key, title_hint)
        if match is None:
            show_key, show_name, items, match = _resolve_from_feeds(
                episode_key, title_hint, preferred_show_key=show_key
            )
    elif title_hint or episode_key:
        show_key, show_name, items, match = _resolve_from_feeds(episode_key, title_hint)
    else:
        raise ValueError(f"Cannot detect show from URL: {url}")

    title = match["title"]
    guest = parse_guest(title)
    slug = slugify(title)
    source_url = match["link"] or url
    spotify_url = spotify_oembed(source_url) or url

    return {
        "slug": slug,
        "title_en": title,
        "show": show_name,
        "hosts": SHOW_HOSTS.get(show_key or "", "Unknown"),
        "guest": guest or title,
        "spotify_url": spotify_url,
        "source_url": source_url,
        "input_url": url,
        "rss_audio_url": match["audio_url"],
        "published": match["published"],
        "duration_sec": match["duration_sec"],
        "description": match["description"],
    }
