"""Additional public Yorkshire event source adapters.

These sources expose public event listing/detail pages. Collection respects each
site's robots.txt through the shared regional adapter and passes all results
through the existing security, date, location and moderation pipeline.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Dict

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import Event
from .regional_sources import scrape_source

HEADERS = {
    "User-Agent": "ImFromYorkshireEventsBot/1.5 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 12)
MAX_TOTAL_SECONDS = 245

SOURCES: Sequence[Dict[str, object]] = (
    {
        "name": "English Heritage Yorkshire",
        "entry_urls": (
            "https://www.english-heritage.org.uk/visit/region/yorkshire/yorkshire-events/",
        ),
        "link_contains": ("/visit/whats-on/",),
        "exclude_exact": (
            "https://www.english-heritage.org.uk/visit/whats-on",
        ),
        "max_details": 40,
    },
    {
        "name": "Our Favourite Places",
        "entry_urls": (
            "https://www.ourfaveplaces.co.uk/whats-on/",
        ),
        "link_contains": ("/whats-on/",),
        "exclude_exact": (
            "https://www.ourfaveplaces.co.uk/whats-on",
        ),
        "max_details": 48,
    },
    {
        "name": "Forestry England Yorkshire",
        "entry_urls": (
            "https://www.forestryengland.uk/dalby-forest/venue/events-dalby-forest",
            "https://www.forestryengland.uk/guisborough-forest/venue/events-guisborough",
            "https://www.forestryengland.uk/gisburn-forest-and-stocks/venue/events-gisburn-forest",
        ),
        "link_contains": ("/forest-event/",),
        "max_details": 40,
    },
    {
        "name": "What's On in Yorkshire",
        "entry_urls": tuple(
            ["https://whatsoninyorkshire.co.uk/events/"]
            + [f"https://whatsoninyorkshire.co.uk/events/page/{page}/" for page in range(2, 8)]
        ),
        "link_contains": ("/events/",),
        "exclude_exact": (
            "https://whatsoninyorkshire.co.uk/events",
        ),
        "max_details": 60,
    },
)


def scrape_expansion_sources() -> List[Event]:
    events: List[Event] = []
    started = time.monotonic()
    print(f"\n[Expansion source adapters] {len(SOURCES) + 1} configured", flush=True)

    for index, config in enumerate(SOURCES, 1):
        if time.monotonic() - started >= MAX_TOTAL_SECONDS:
            print("  Expansion-source runtime cap reached; remaining sources deferred.", flush=True)
            break
        source_started = time.monotonic()
        try:
            source_events = scrape_source(config)
        except Exception as exc:
            print(f"  [{index}/{len(SOURCES) + 1}] {config['name']}: failed safely ({exc})", flush=True)
            continue
        events.extend(source_events)
        print(
            f"  [{index}/{len(SOURCES) + 1}] {config['name']}: {len(source_events)} events "
            f"in {time.monotonic() - source_started:.1f}s",
            flush=True,
        )

    if time.monotonic() - started < MAX_TOTAL_SECONDS:
        source_started = time.monotonic()
        try:
            diggerland = _scrape_diggerland_yorkshire()
        except Exception as exc:
            print(f"  [{len(SOURCES) + 1}/{len(SOURCES) + 1}] Diggerland: failed safely ({exc})", flush=True)
            diggerland = []
        events.extend(diggerland)
        print(
            f"  [{len(SOURCES) + 1}/{len(SOURCES) + 1}] Diggerland: {len(diggerland)} events "
            f"in {time.monotonic() - source_started:.1f}s",
            flush=True,
        )

    return _dedupe(events)


def _scrape_diggerland_yorkshire() -> List[Event]:
    """Read only Diggerland outside events that are explicitly in Yorkshire."""
    url = "https://www.diggerland.com/events/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(response.text, "lxml")
    events: List[Event] = []
    postcode_re = re.compile(r"\b(?:YO|LS|WF|BD|HD|HX|S|DN|HU|HG|TS|DL)\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", re.I)
    date_re = re.compile(
        r"(?P<date>(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+\d{4})",
        re.I,
    )

    for item in soup.select("main li, article li, .entry-content li, li"):
        text = re.sub(r"\s+", " ", item.get_text(" ", strip=True)).strip()
        if not text or not postcode_re.search(text):
            continue
        date_match = date_re.search(text)
        if not date_match:
            continue
        try:
            start = dateparser.parse(date_match.group("date"), dayfirst=True, fuzzy=True)
        except (ValueError, TypeError, OverflowError):
            continue
        if not start:
            continue

        before = text[:date_match.start()].strip(" -–—,:;")
        after = text[date_match.end():].strip(" -–—,:;")
        title = before or "Diggerland Yorkshire event"
        location = after or None
        if location and len(location) > 240:
            location = location[:240]

        events.append(Event(
            title=title[:220],
            url=url,
            source="Diggerland",
            date=start.replace(hour=0, minute=0, second=0, microsecond=0),
            end_date=start.replace(hour=0, minute=0, second=0, microsecond=0),
            location=location,
            description="Diggerland is attending this Yorkshire event with its outside-event attractions.",
            category="Family Days Out",
            all_day=True,
        ))

    return _dedupe(events)


def _dedupe(events: Iterable[Event]) -> List[Event]:
    seen = set()
    result = []
    for event in events:
        key = (
            (event.url or "").split("#", 1)[0].rstrip("/").lower(),
            event.date.isoformat() if isinstance(event.date, datetime) else "",
            (event.title or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result
