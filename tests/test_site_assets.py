"""The site's pages link styles.css and main.js with a ?v= that matches the file's content."""

import hashlib
import re
from pathlib import Path

LINK = re.compile(r'(?:href|src)="/?(styles\.css|main\.js)(?:\?v=([0-9a-f]+))?"')

SITE = Path(__file__).resolve().parent.parent / "site"


def _short_hash(name: str) -> str:
    return hashlib.sha256((SITE / name).read_bytes()).hexdigest()[:8]


def test_asset_links_carry_current_version() -> None:
    expected = {name: _short_hash(name) for name in ("styles.css", "main.js")}
    found = 0
    for page in SITE.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        for name, version in LINK.findall(text):
            found += 1
            want = expected[name]
            assert version == want, f"{page.name}: {name}?v={version or '(none)'}, want ?v={want}"
    assert found >= 6
