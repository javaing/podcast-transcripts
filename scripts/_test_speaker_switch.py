"""Test consecutive-embedding speaker switch detection."""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dialogue import _embed_clip, _get_w2v_model, _slice_segment_audio, group_turns, load_audio, load_segments


def assign_by_adjacent_distance(segments, wav, sr, percentile=55):
    model = _get_w2v_model()
    embeddings = []
    valid = []
    for i, seg in enumerate(segments):
        clip = _slice_segment_audio(wav, sr, seg["start"], seg["end"])
        if clip is None:
            continue
        embeddings.append(_embed_clip(model, clip))
        valid.append(i)

    if len(embeddings) < 2:
        return [{**s, "speaker": 0} for s in segments]

    embs = np.vstack(embeddings)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    embs_n = embs / np.clip(norms, 1e-8, None)

    distances = []
    for i in range(1, len(embs_n)):
        d = 1.0 - float(np.dot(embs_n[i - 1], embs_n[i]))
        distances.append(d)

    threshold = float(np.percentile(distances, percentile))
    speakers_seq = [0]
    current = 0
    switches = 0
    for d in distances:
        if d >= threshold:
            current = 1 - current
            switches += 1
        speakers_seq.append(current)

    labeled = [{**s, "speaker": 0} for s in segments]
    for idx, spk in zip(valid, speakers_seq):
        labeled[idx]["speaker"] = spk

    return labeled, threshold, switches


ep = Path(__file__).resolve().parent.parent / "transcripts" / "following-the-line-interview-with-ccddbb-claudio"
segs = load_segments(ep / "transcript_en_segments.json")
wav, sr = load_audio(ep / "episode.mp3")

for pct in [45, 50, 55, 60, 65, 70]:
    labeled, thr, sw = assign_by_adjacent_distance(segs, wav, sr, percentile=pct)
    turns = group_turns(labeled)
    counts = Counter(s["speaker"] for s in labeled)
    print(f"pct={pct} thr={thr:.4f} switches={sw} turns={len(turns)} speakers={dict(counts)}")
