"""The signed stance-data labeling guide in eval/gold/stancedata/ matches its draft, and the
files Arsh signed with it are unchanged."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIGNED_GUIDE = ROOT / "eval" / "gold" / "stancedata" / "LABELING_GUIDE.md"
DRAFT_GUIDE = ROOT / "eval" / "stancedata" / "LABELING_GUIDE.md"

# Pinned when Arsh signed guide v0.3 on 2026-10-14; the glossaries are unchanged since he signed
# them with v0.2 on 2026-10-12 (commit 0f298d6).
SIGNED_SHA256 = {
    "eval/stancedata/LABELING_GUIDE.md": (
        "40b8618456d264dd5f97377f9f94ceef50a4a05cd6c1d8ecb8f63e8a497c09a2"
    ),
    "eval/train/glossary.py": "952496c486d00df67c8d8cb63c98e8bc0278086ec401d28e5eb6dc36dda28cf8",
    "eval/heldout/glossary.py": "c61327dd0b1e309892f0ec6f025cf6f35d0d4d8fb3f10761db42e4ba8a1f479c",
}


def test_signed_guide_is_the_draft_below_its_header() -> None:
    signed = SIGNED_GUIDE.read_text(encoding="utf-8")
    draft = DRAFT_GUIDE.read_text(encoding="utf-8")
    assert signed.startswith("# Labeling guide for generated stance data\n\nSIGNED by Arsh")
    assert signed.partition("\nSYNTHETIC.")[2] == draft.partition("\nSYNTHETIC.")[2]


def test_signed_files_are_unchanged() -> None:
    for path, digest in SIGNED_SHA256.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == digest, f"{path} changed after Arsh signed it; it needs a new signature"
