"""Speaker-aware dialogue formatting for podcast transcripts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import torch
import torchaudio
from sklearn.cluster import AgglomerativeClustering

_W2V_MODEL = None
_W2V_BUNDLE = torchaudio.pipelines.WAV2VEC2_BASE


def _get_w2v_model():
    global _W2V_MODEL
    if _W2V_MODEL is None:
        _W2V_MODEL = _W2V_BUNDLE.get_model()
        _W2V_MODEL.eval()
    return _W2V_MODEL


def load_audio(audio_path: Path, sr: int = 16000) -> tuple[np.ndarray, int]:
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-ar",
            str(sr),
            "-ac",
            "1",
            "-f",
            "f32le",
            "-",
        ],
        stderr=subprocess.DEVNULL,
    )
    return np.frombuffer(raw, dtype=np.float32), sr


def load_segments(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slice_segment_audio(
    wav: np.ndarray,
    sr: int,
    start: float,
    end: float,
    min_samples: int = 8000,
) -> np.ndarray | None:
    s = max(0, int(start * sr))
    e = min(len(wav), int(end * sr))
    if e - s < min_samples:
        mid = (s + e) // 2
        half = min_samples // 2
        s = max(0, mid - half)
        e = min(len(wav), mid + half)
    if e - s < min_samples // 2:
        return None
    return wav[s:e]


def _embed_clip(model, clip: np.ndarray) -> np.ndarray:
    tensor = torch.tensor(clip, dtype=torch.float32).unsqueeze(0)
    with torch.inference_mode():
        features, _ = model.extract_features(tensor)
    return features[-1].mean(dim=1).squeeze().cpu().numpy()


def assign_speakers(
    audio_path: Path,
    segments: list[dict],
    *,
    max_speakers: int = 3,
) -> list[dict]:
    """Assign a speaker cluster id to each whisper segment."""
    print("Diarizing speakers...")
    wav, sr = load_audio(audio_path)
    model = _get_w2v_model()

    embeddings: list[np.ndarray] = []
    valid_indices: list[int] = []
    total = len(segments)
    for i, seg in enumerate(segments):
        clip = _slice_segment_audio(wav, sr, seg["start"], seg["end"])
        if clip is None:
            continue
        embeddings.append(_embed_clip(model, clip))
        valid_indices.append(i)
        if (i + 1) % 100 == 0:
            print(f"  embedded {i + 1}/{total} segments")

    if not embeddings:
        return [{**seg, "speaker": 0} for seg in segments]

    matrix = np.vstack(embeddings)
    best_labels = None
    best_score = -1.0
    for n in range(2, min(max_speakers, len(embeddings)) + 1):
        clustering = AgglomerativeClustering(n_clusters=n, metric="cosine", linkage="average")
        labels = clustering.fit_predict(matrix)
        counts = np.bincount(labels)
        balance = counts.min() / counts.max()
        if balance > best_score:
            best_score = balance
            best_labels = labels

    if best_labels is None:
        best_labels = np.zeros(len(embeddings), dtype=int)

    labeled = [{**seg, "speaker": -1} for seg in segments]
    for idx, speaker in zip(valid_indices, best_labels):
        labeled[idx]["speaker"] = int(speaker)

    prev = labeled[valid_indices[0]]["speaker"] if valid_indices else 0
    for seg in labeled:
        if seg["speaker"] == -1:
            seg["speaker"] = prev
        else:
            prev = seg["speaker"]
    prev = labeled[-1]["speaker"]
    for seg in reversed(labeled):
        if seg["speaker"] == -1:
            seg["speaker"] = prev
        else:
            prev = seg["speaker"]

    print(f"  detected up to {len(set(s['speaker'] for s in labeled))} speakers")
    return labeled


def group_turns(segments: list[dict]) -> list[dict]:
    """Merge consecutive segments from the same speaker into dialogue turns."""
    turns: list[dict] = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        speaker = int(seg.get("speaker", 0))
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["text"] = turns[-1]["text"] + " " + text
            turns[-1]["end"] = seg["end"]
        else:
            turns.append(
                {
                    "speaker": speaker,
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": text,
                }
            )
    return turns


def format_turns_text(turns: list[dict]) -> str:
    """Join turns with blank lines between speaker changes."""
    parts = [t["text"].strip() for t in turns if t.get("text", "").strip()]
    return "\n\n".join(parts)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_turns_markdown(turns: list[dict], speaker_names: dict[int, str] | None = None) -> str:
    blocks: list[str] = []
    for turn in turns:
        text = turn["text"].strip()
        if not text:
            continue
        ts = format_timestamp(turn["start"])
        label = ""
        if speaker_names and turn["speaker"] in speaker_names:
            label = f"**{speaker_names[turn['speaker']]}** "
        blocks.append(f"**[{ts}]** {label}{text}")
    return "\n\n".join(blocks)


def speaker_name_map(meta: dict) -> dict[int, str]:
    guest = meta.get("guest", "Guest")
    hosts = meta.get("hosts", "Host")
    return {0: hosts, 1: guest, 2: hosts}
