#!/usr/bin/env python3
"""One-command podcast URL -> Chinese transcript -> GitHub Pages."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_site import build_episode_page, build_index, load_shows_config  # noqa: E402
from fix_episode import main as fix_episode  # noqa: E402
from resolve_episode import resolve_episode  # noqa: E402
from transcribe_episode import transcribe_episode  # noqa: E402


def download_audio(url: str, dest: Path) -> None:
    print(f"Downloading audio to {dest}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; podcast-transcripts/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    print(f"Downloaded {dest.stat().st_size // 1024 // 1024} MB")


def git_push(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("No git changes to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
    subprocess.run(["git", "push"], cwd=root, check=True)
    print("Pushed to GitHub.")


def process_url(
    url: str,
    *,
    model: str = "base",
    push: bool = False,
    skip_transcribe: bool = False,
) -> Path:
    meta = resolve_episode(url)
    episode_dir = ROOT / "transcripts" / meta["slug"]
    episode_dir.mkdir(parents=True, exist_ok=True)

    print(f"Episode: {meta['title_en']}")
    print(f"Slug: {meta['slug']}")
    print(f"Published: {meta['published']} · ~{meta['duration_sec'] // 60} min")

    audio = episode_dir / "episode.mp3"
    if not audio.exists():
        download_audio(meta["rss_audio_url"], audio)
    else:
        print(f"Audio already exists: {audio}")

    (episode_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not skip_transcribe:
        transcribe_episode(episode_dir, meta, model_name=model)

    fix_episode(episode_dir)
    show_lookup = load_shows_config()
    build_episode_page(episode_dir, ROOT / "episodes", show_lookup)
    build_index(ROOT, show_lookup)

    if push:
        git_push(
            ROOT,
            f"Add transcript: {meta['title_en']}",
        )

    print(f"\nLocal page: {ROOT / 'episodes' / (meta['slug'] + '.html')}")
    return episode_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a podcast episode URL.")
    parser.add_argument("url", help="Spotify / creators.spotify episode URL")
    parser.add_argument("--model", default="base", help="Whisper model (default: base)")
    parser.add_argument("--push", action="store_true", help="Git commit and push")
    parser.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Only resolve/download/build if transcript already exists",
    )
    args = parser.parse_args()
    process_url(args.url, model=args.model, push=args.push, skip_transcribe=args.skip_transcribe)


if __name__ == "__main__":
    main()
