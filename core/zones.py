"""A phone's time zone as Mabillon can use it, from the text an extraction gives.

devices.timezone keeps the source's own words. They come in three shapes:
- an IANA name, such as America/New_York (the synthetic cases, some exports);
- a Cellebrite UFDR's '(UTC-05:00)  New_York  (America)': city and region of an IANA name;
- a Windows display name, such as '(UTC-05:00) Eastern Time (US & Canada)' (Cellebrite Excel).

resolve_zone() turns the second and third into the IANA name, but only when the zone it names
has the offset the text states (in winter or in summer): a name and an offset that disagree are
not guessed at. Anything else comes back as given, so the callers that cannot read it still
say so with the source's own words, as before.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_OFFSET = r"\((?:UTC|GMT)(?:(?P<sign>[+-])(?P<h>\d{1,2}):(?P<m>\d{2}))?\)"
# '(UTC-05:00)  New_York  (America)', '(UTC+05:30) Kolkata (Asia)'
_CITY_REGION = re.compile(rf"^{_OFFSET}\s+(?P<city>[A-Za-z_/\-]+)\s+\((?P<region>[A-Za-z_/]+)\)$")
_DISPLAY = re.compile(rf"^{_OFFSET}\s*(?P<name>.+)$")
# Windows display names (CLDR windowsZones, territory 001), only those checked here; the
# offset in front is checked against the zone too.
_WINDOWS = {
    "eastern time (us & canada)": "America/New_York",
    "central time (us & canada)": "America/Chicago",
    "mountain time (us & canada)": "America/Denver",
    "arizona": "America/Phoenix",
    "pacific time (us & canada)": "America/Los_Angeles",
    "alaska": "America/Anchorage",
    "hawaii": "Pacific/Honolulu",
    "coordinated universal time": "UTC",
}


def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _offset(m: re.Match[str]) -> timedelta:
    if m.group("sign") is None:
        return timedelta(0)
    off = timedelta(hours=int(m.group("h")), minutes=int(m.group("m")))
    return -off if m.group("sign") == "-" else off


def _has_offset(zone: ZoneInfo, off: timedelta) -> bool:
    """The zone is at this offset in winter or in summer (either hemisphere)."""
    return any(datetime(2026, mo, 1, 12, tzinfo=zone).utcoffset() == off for mo in (1, 7))


@lru_cache(maxsize=256)
def resolve_zone(raw: str | None) -> str | None:
    """The IANA name for a phone's time zone text, or the text as given when it names none."""
    if raw is None:
        return None
    text = " ".join(raw.split())
    if "/" in text and _zone(text) is not None:
        return text
    m = _CITY_REGION.match(text)
    if m:
        name = f"{m.group('region')}/{m.group('city')}"
        z = _zone(name)
        if z is not None and _has_offset(z, _offset(m)):
            return name
    m = _DISPLAY.match(text)
    if m:
        name = _WINDOWS.get(m.group("name").strip().casefold())
        z = _zone(name) if name else None
        if z is not None and _has_offset(z, _offset(m)):
            return name
    return raw
