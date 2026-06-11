"""Speaker-aware dialogue formatting for podcast transcripts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import torch
import torchaudio

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


def _segment_embeddings(
    audio_path: Path,
    segments: list[dict],
) -> tuple[list[int], np.ndarray]:
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
            print(f"  embedded {i + 1}/{total} segments", flush=True)

    if not embeddings:
        return [], np.empty((0, 0))

    matrix = np.vstack(embeddings)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.clip(norms, 1e-8, None)
    return valid_indices, matrix


def _labels_from_adjacent_distance(matrix: np.ndarray, percentile: float = 78.0) -> np.ndarray:
    """Toggle speaker when consecutive segment embeddings diverge."""
    if len(matrix) < 2:
        return np.zeros(len(matrix), dtype=int)

    distances = [1.0 - float(np.dot(matrix[i - 1], matrix[i])) for i in range(1, len(matrix))]
    threshold = float(np.percentile(distances, percentile))

    labels = [0]
    current = 0
    for d in distances:
        if d >= threshold:
            current = 1 - current
        labels.append(current)
    return np.array(labels, dtype=int)


def _fill_missing_speakers(labeled: list[dict], valid_indices: list[int]) -> None:
    if not valid_indices:
        for seg in labeled:
            seg["speaker"] = 0
        return

    prev = labeled[valid_indices[0]]["speaker"]
    for seg in labeled:
        if seg["speaker"] == -1:
            seg["speaker"] = prev
        else:
            prev = seg["speaker"]
    prev = labeled[valid_indices[-1]]["speaker"]
    for seg in reversed(labeled):
        if seg["speaker"] == -1:
            seg["speaker"] = prev
        else:
            prev = seg["speaker"]


def assign_speakers(
    audio_path: Path,
    segments: list[dict],
    *,
    switch_percentile: float = 78.0,
) -> list[dict]:
    """Assign a speaker id to each whisper segment."""
    print("Diarizing speakers...", flush=True)
    valid_indices, matrix = _segment_embeddings(audio_path, segments)
    labeled = [{**seg, "speaker": -1} for seg in segments]

    if matrix.size == 0:
        return [{**seg, "speaker": 0} for seg in segments]

    best_labels = _labels_from_adjacent_distance(matrix, switch_percentile)

    for idx, speaker in zip(valid_indices, best_labels):
        labeled[idx]["speaker"] = int(speaker)
    _fill_missing_speakers(labeled, valid_indices)

    speakers = sorted({s["speaker"] for s in labeled})
    turns = group_turns(labeled)
    print(
        f"  method=adjacent-distance, speakers={len(speakers)}, turns={len(turns)}",
        flush=True,
    )
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
