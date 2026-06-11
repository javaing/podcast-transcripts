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
    with urllib.request.urlopen(feed_url, timeout=30) as resp:
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


def resolve_episode(url: str) -> dict:
    episode_key = extract_episode_key(url)
    show_key = extract_show_key(url)
    if not show_key:
        raise ValueError(f"Cannot detect show from URL: {url}")
    feed_url = SHOW_FEEDS.get(show_key)
    if not feed_url:
        raise ValueError(
            f"No RSS feed configured for show '{show_key}'. Add it to SHOW_FEEDS."
        )

    show_name, items = fetch_rss_items(feed_url)
    match = None
    if episode_key:
        for item in items:
            if episode_key in item["link"]:
                match = item
                break
    if match is None:
        raise ValueError(f"Episode not found in RSS for key: {episode_key}")

    title = match["title"]
    guest = parse_guest(title)
    slug = slugify(title)
    source_url = match["link"] or url
    spotify_url = spotify_oembed(source_url) or url

    return {
        "slug": slug,
        "title_en": title,
        "show": show_name,
        "hosts": "Will & Trinity",
        "guest": guest or title,
        "spotify_url": spotify_url,
        "source_url": source_url,
        "input_url": url,
        "rss_audio_url": match["audio_url"],
        "published": match["published"],
        "duration_sec": match["duration_sec"],
        "description": match["description"],
    }
