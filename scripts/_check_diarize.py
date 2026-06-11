"""Quick diarization sanity check (dev only)."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dialogue import assign_speakers, group_turns

ep = Path(__file__).resolve().parent.parent / "transcripts" / "following-the-line-interview-with-ccddbb-claudio"
segs = json.loads((ep / "transcript_en_segments.json").read_text(encoding="utf-8"))
print(f"total segments: {len(segs)}")
labeled = assign_speakers(ep / "episode.mp3", segs)
print("speaker counts:", dict(Counter(s["speaker"] for s in labeled)))
turns = group_turns(labeled)
print(f"turns: {len(turns)}")
for t in turns[:6]:
    print(f"  sp{t['speaker']}: {t['text'][:90]}...")
