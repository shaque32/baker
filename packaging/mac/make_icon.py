"""Draw the Mac app's icon set from the app's mark, for `iconutil -c icns`.

    python packaging/mac/make_icon.py <folder ending in .iconset>

The mark is the one the Windows installer's icon uses (packaging/windows/art/make_art.py), drawn
at every size macOS asks for. The installer runs this on the Mac with Mabillon's own Python
(Pillow is a Mabillon dependency); nothing is downloaded.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "windows" / "art" / "make_art.py"
SIZES = (16, 32, 128, 256, 512)


def main(out: Path) -> None:
    spec = importlib.util.spec_from_file_location("make_art", ART)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {ART}")
    art = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(art)
    out.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        art.mark(size, bg=None).save(out / f"icon_{size}x{size}.png")
        art.mark(size * 2, bg=None).save(out / f"icon_{size}x{size}@2x.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
