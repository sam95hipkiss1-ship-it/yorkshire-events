"""Enrich missing event locations from approved event detail pages.

Only explicit venue/address fields are accepted. The collector does not infer a
location from an event title, source name or page URL.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from . import Event
from .security import clean_location, validate_destination

HEADERS = {
    "User-Agent": "ImFromYorkshireEventsBot/1.4 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 12)
MAX_PAGES = 120
MAX_TOTAL_SECONDS = 150
WORKERS = 8
MAX_LOCATION = 240

LOCATION_LABEL = r"(?:venue\s+location|event\s+location|venue|location|where|address|place)"
LABEL_PATTERN = re.compile(rf"^{LOCATION_LABEL}\s*:?$", re.IGNORECASE)
INLINE_PATTERN = re.compile(
    rf"{LOCATION_LABEL}\s*(?::|–|—|-)\s*(.{{4,240}}?)"
    r"(?=\s+(?:date|dates|time|times|tickets?|price|cost|book|category|"
    r"organiser|organizer|contact|accessibility|opening)\b|$)",
    re.IGNORECASE,
)
INLINE_UNPUNCTUATED_PATTERN = re.compile(
    rf"{LOCATION_LABEL}\s+(.{{4,240}}?)"
    r"(?=\s+(?:date|dates|time|times|tickets?|price|cost|book|category|"
    r"organiser|organizer|contact|accessibility|opening)\b|$)",
    re.IGNORECASE,
)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
STOP_VALUES = {
    "venue", "venue location", "event location", "location", "where", "address", "place",
    "view map", "map", "directions", "get directions", "find us", "more information",
}


def enrich_missing_locations(events: Iterable[Event]) -> List[Event]:
    result = list(events)
    targets: Dict[str, List[Event]] = {}

    for event in result:
        if clean_location(event.location):
            continue
        if validate_destination(str(event.url or ""), str(event.source or "")):
            continue
        url = str(event.url or "").split("#", 1)[0].strip()
        if not url or url in targets:
            if url:
                targets[url].append(event)
            continue
        targets[url] = [event]
        if len(targets) >= MAX_PAGES:
            break

    if not targets:
        print("Location enrichment: no missing approved locations", flush=True)
        return result

    started = time.monotonic()
    found = 0
    checked = 0
    print(f"Location enrichment: checking {len(targets)} approved detail pages", flush=True)

    with ThreadPoolExecutor(max_workers=min(WORKERS, len(targets))) as executor:
        futures = {executor.submit(_fetch_location, url): url for url in targets}
        for future in as_completed(futures):
            if time.monotonic() - started >= MAX_TOTAL_SECONDS:
                break
            url = futures[future]
            checked += 1
            try:
                location = future.result()
            except Exception:
                location = None
            if not location:
                continue
            found += 1
            for event in targets[url]:
                event.location = location
            print(f"  Location enriched: {urlparse(url).netloc} -> {location}", flush=True)

    print(
        f"Location enrichment complete: {found} locations found from {checked} pages",
        flush=True,
    )
    return result


def _fetch_location(url: str) -> Optional[str]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xml" not in content_type:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "lxml")

    location = _jsonld_location(soup)
    if location:
        return location

    location = _meta_location(soup)
    if location:
        return location

    scope = soup.select_one("main, article, [role='main'], .event, .event-detail, .event-content") or soup

    location = _structured_html_location(scope)
    if location:
        return location

    location = _labelled_location(scope)
    if location:
        return location

    return _inline_location(scope)


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _jsonld_location(soup: BeautifulSoup) -> Optional[str]:
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.IGNORECASE)):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_json(payload):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(value and "event" in str(value).lower() for value in types):
                continue
            location = _location_from_json(node.get("location"))
            location = _normalise_location(location)
            if location:
                return location
    return None


def _location_from_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(part for part in (_location_from_json(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""

    parts: List[str] = []
    name = value.get("name")
    if name:
        parts.append(str(name))
    address = value.get("address")
    if isinstance(address, str):
        parts.append(address)
    elif isinstance(address, dict):
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            if address.get(key):
                parts.append(str(address[key]))
    return ", ".join(dict.fromkeys(_clean(part) for part in parts if _clean(part)))


def _meta_location(soup: BeautifulSoup) -> Optional[str]:
    selectors = (
        "meta[itemprop='location']",
        "meta[itemprop='address']",
        "meta[name='event_location']",
        "meta[name='event-location']",
        "meta[name='venue']",
        "meta[property='event:location']",
        "meta[property='place:location']",
        "meta[name='geo.placename']",
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            location = _normalise_location(element.get("content", ""))
            if location:
                return location
    return None


def _structured_html_location(scope: Tag) -> Optional[str]:
    selectors = (
        "address",
        "[itemprop='location']",
        "[itemprop='address']",
        "[data-location]",
        "[data-venue]",
        "[id*='event-location']",
        "[id*='venue-location']",
        "[id*='event-venue']",
        "[class*='event-location']",
        "[class*='venue-location']",
        "[class*='event-venue']",
        "[class*='location']",
        "[class*='venue']",
        "[class*='address']",
    )
    for selector in selectors:
        for element in scope.select(selector):
            raw = element.get("data-location") or element.get("data-venue") or element.get_text(" ", strip=True)
            location = _normalise_location(raw)
            if location:
                return location
    return None


def _labelled_location(scope: Tag) -> Optional[str]:
    for label in scope.select("dt, th, label, strong, b, h2, h3, h4, p, span, div"):
        label_text = _clean(label.get_text(" ", strip=True))
        if not LABEL_PATTERN.fullmatch(label_text):
            continue

        candidates: List[Optional[Tag]] = []
        if label.name == "dt":
            candidates.append(label.find_next_sibling("dd"))
        elif label.name == "th":
            candidates.append(label.find_next_sibling("td"))
        candidates.append(label.find_next_sibling())

        parent = label.parent if isinstance(label.parent, Tag) else None
        if parent:
            siblings = [child for child in parent.children if isinstance(child, Tag)]
            try:
                index = siblings.index(label)
                if index + 1 < len(siblings):
                    candidates.append(siblings[index + 1])
            except ValueError:
                pass

        for candidate in candidates:
            if not candidate:
                continue
            location = _normalise_location(candidate.get_text(" ", strip=True))
            if location:
                return location
    return None


def _inline_location(scope: Tag) -> Optional[str]:
    text = _clean(scope.get_text(" ", strip=True))
    for pattern in (INLINE_PATTERN, INLINE_UNPUNCTUATED_PATTERN):
        match = pattern.search(text)
        if match:
            location = _normalise_location(match.group(1))
            if location:
                return location

    # Postcodes are used only when they occur immediately after an explicit
    # location label, preventing a footer or company address from being used.
    for match in POSTCODE_RE.finditer(text):
        start = max(0, match.start() - 180)
        context = text[start:match.end()]
        label_match = re.search(
            rf"{LOCATION_LABEL}\s*(?::|–|—|-)?\s+(.+)$",
            context,
            re.IGNORECASE,
        )
        if label_match:
            location = _normalise_location(label_match.group(1))
            if location:
                return location
    return None


def _normalise_location(value: object) -> Optional[str]:
    text = _clean(value)
    text = re.sub(
        rf"^{LOCATION_LABEL}\s*(?::|–|—|-)?\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip(" ,-–—|:")
    if not text or len(text) < 4 or len(text) > MAX_LOCATION:
        return None
    if text.lower() in STOP_VALUES or LABEL_PATTERN.fullmatch(text):
        return None
    if re.fullmatch(r"(?:view|open|see|get)\s+(?:the\s+)?map", text, re.IGNORECASE):
        return None
    return clean_location(text)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
