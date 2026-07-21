import json
import re
from datetime import datetime
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import Event

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

BASE_URL = "https://visitnorthyorkshire.com"
EVENTS_URL = f"{BASE_URL}/events"


def scrape_visitnorthyorkshire() -> List[Event]:
    events = []
    print("  Fetching Visit North Yorkshire...")

    try:
        resp = requests.get(EVENTS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        event_cards = soup.select("div.event-card, article.event, div.listing-item, div.event-item")
        if not event_cards:
            event_cards = soup.select("a[href*='/events/']")

        seen_urls = set()
        for card in event_cards:
            event = _parse_event_card(card)
            if not event or not event.url or event.url in seen_urls:
                continue
            seen_urls.add(event.url)
            events.append(_enrich_event_from_detail(event))

        if not events:
            events = _extract_events_from_json(soup)
            events = [_enrich_event_from_detail(event) for event in events]

        if not events:
            events = _fallback_scrape(soup)
            events = [_enrich_event_from_detail(event) for event in events]

    except Exception as e:
        print(f"    Error fetching Visit North Yorkshire: {e}")

    print(f"    Found {len(events)} events from Visit North Yorkshire")
    return events


def _parse_event_card(card) -> Optional[Event]:
    title_elem = card.select_one("h2, h3, h4, .event-title, .listing-title")
    if not title_elem:
        if card.name == "a":
            title_elem = card
        else:
            return None

    title = title_elem.get_text(" ", strip=True)
    if not title or len(title) < 3:
        return None

    url = ""
    if card.name == "a":
        url = card.get("href", "")
    else:
        link = card.select_one("a[href*='/events/']")
        if link:
            url = link.get("href", "")

    url = _absolute_url(url)
    if _is_category_link(url):
        return None

    date_text = ""
    date_elem = card.select_one("time, .date, .event-date, .listing-date")
    if date_elem:
        date_text = date_elem.get("datetime", date_elem.get_text(" ", strip=True))

    location = ""
    location_elem = card.select_one(".location, .venue, .place")
    if location_elem:
        location = location_elem.get_text(" ", strip=True)

    description = ""
    desc_elem = card.select_one("p, .description, .excerpt")
    if desc_elem:
        description = desc_elem.get_text(" ", strip=True)

    start_date, end_date, all_day = _parse_date_range(date_text)

    return Event(
        title=title,
        url=url or EVENTS_URL,
        source="Visit North Yorkshire",
        date=start_date,
        end_date=end_date,
        location=location or None,
        description=description[:800] if description else None,
        all_day=all_day,
    )


def _enrich_event_from_detail(event: Event) -> Event:
    if not event.url or _is_category_link(event.url):
        return event

    try:
        response = requests.get(event.url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        structured = _extract_event_json_ld(soup)
        if structured:
            event.title = structured.get("title") or event.title
            event.date = structured.get("date") or event.date
            event.end_date = structured.get("end_date") or event.end_date
            event.location = structured.get("location") or event.location
            event.description = structured.get("description") or event.description
            event.category = structured.get("category") or event.category
            event.image_url = structured.get("image_url") or event.image_url
            if structured.get("all_day") is not None:
                event.all_day = structured["all_day"]

        if not event.date:
            page_text = soup.get_text(" ", strip=True)
            start_date, end_date, all_day = _extract_dates_from_page_text(page_text)
            if start_date:
                event.date = start_date
                event.end_date = end_date
                event.all_day = all_day

        if not event.description:
            meta_description = soup.select_one("meta[name='description'], meta[property='og:description']")
            if meta_description:
                event.description = meta_description.get("content", "").strip()[:800] or None

        if not event.location:
            location_elem = soup.select_one("[class*='location'], [class*='venue'], address")
            if location_elem:
                event.location = location_elem.get_text(" ", strip=True)[:250] or None

    except Exception as exc:
        print(f"    Detail page warning for {event.url}: {exc}")

    return event


def _extract_event_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in _walk_json_objects(data):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if not any(value and "event" in str(value).lower() for value in types):
                continue

            start_raw = item.get("startDate") or item.get("start_date")
            end_raw = item.get("endDate") or item.get("end_date")
            start_date = _parse_single_date(start_raw)
            end_date = _parse_single_date(end_raw)
            all_day = _looks_all_day(start_raw) and (not end_raw or _looks_all_day(end_raw))

            location = _location_from_json(item.get("location"))
            image = item.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")

            description = BeautifulSoup(str(item.get("description") or ""), "html.parser").get_text(" ", strip=True)
            category = item.get("eventType") or item.get("category")

            return {
                "title": str(item.get("name") or "").strip() or None,
                "date": start_date,
                "end_date": end_date,
                "location": location,
                "description": description[:800] or None,
                "category": str(category).strip() if category else None,
                "image_url": str(image).strip() if image else None,
                "all_day": all_day,
            }
    return None


def _walk_json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_objects(child)


def _extract_dates_from_page_text(text: str) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    patterns = [
        r"Dates?\s*:\s*([^|]{5,120}?)(?=\s+(?:Times?|Location|Venue|Price|Contact|Website)\s*:|$)",
        r"Date\s+and\s+time\s*:\s*([^|]{5,120}?)(?=\s+(?:Location|Venue|Price|Contact|Website)\s*:|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            start, end, all_day = _parse_date_range(match.group(1))
            if start:
                return start, end, all_day
    return None, None, False


def _parse_date_range(value) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    if not value:
        return None, None, False

    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"\bSept\b", "Sep", text, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:-|–|—|to)\s+", text, maxsplit=1, flags=re.IGNORECASE)
    start = _parse_single_date(parts[0])
    end = _parse_single_date(parts[1]) if len(parts) > 1 else None
    all_day = _looks_all_day(parts[0]) and (len(parts) == 1 or _looks_all_day(parts[1]))
    return start, end, all_day


def _parse_single_date(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = dateparser.parse(str(value), dayfirst=True, fuzzy=True)
        return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _looks_all_day(value) -> bool:
    if not value:
        return False
    text = str(value)
    return not bool(re.search(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(?:am|pm)\b", text, flags=re.IGNORECASE))


def _location_from_json(location) -> Optional[str]:
    if isinstance(location, str):
        return location.strip() or None
    if not isinstance(location, dict):
        return None

    parts = []
    name = location.get("name")
    if name:
        parts.append(str(name).strip())

    address = location.get("address")
    if isinstance(address, str):
        parts.append(address.strip())
    elif isinstance(address, dict):
        for key in ["streetAddress", "addressLocality", "addressRegion", "postalCode"]:
            if address.get(key):
                parts.append(str(address[key]).strip())

    deduped = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return ", ".join(deduped) or None


def _extract_events_from_json(soup: BeautifulSoup) -> List[Event]:
    events = []
    scripts = soup.find_all("script", type="application/json")

    for script in scripts:
        try:
            data = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue

        for item in _walk_json_objects(data):
            if not isinstance(item, dict) or not (item.get("title") or item.get("name")):
                continue
            event = _json_to_event(item)
            if event:
                events.append(event)
    return events


def _json_to_event(data: dict) -> Optional[Event]:
    title = data.get("title") or data.get("name") or ""
    if not title:
        return None

    url = _absolute_url(data.get("url") or data.get("link") or "")
    start_raw = data.get("date") or data.get("start_date") or data.get("startDate") or data.get("eventDate")
    end_raw = data.get("end_date") or data.get("endDate")
    date = _parse_single_date(start_raw)
    end_date = _parse_single_date(end_raw)
    location = _location_from_json(data.get("location") or data.get("venue"))

    return Event(
        title=str(title).strip(),
        url=url or EVENTS_URL,
        source="Visit North Yorkshire",
        date=date,
        end_date=end_date,
        location=location,
        description=str(data.get("description") or "").strip()[:800] or None,
        category=str(data.get("category") or "").strip() or None,
        all_day=_looks_all_day(start_raw) and (not end_raw or _looks_all_day(end_raw)),
    )


CATEGORY_PATTERNS = [
    "food-drink-events", "science-nature-events", "heritage-events",
    "garden-events", "talks", "literature-events", "easter-events",
    "halloween-events", "bonfire-night", "christmas-events",
    "kids-family-events", "artisans-farmers-markets", "festivals",
    "learning-workshops", "exhibitions", "country-shows",
    "sport-active-events", "entertainment", "live-music", "comedy",
    "theatre", "film-events", "dance-events", "exhibtions",
    "film", "dance", "markets", "family-events", "sporting-and-active-events",
]


def _absolute_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return f"{BASE_URL}{url}" if url.startswith("/") else f"{BASE_URL}/{url}"


def _is_category_link(url: str) -> bool:
    url_lower = (url or "").lower().rstrip("/")
    if not url_lower or url_lower.endswith("/events"):
        return True
    return any(pattern in url_lower for pattern in CATEGORY_PATTERNS)


def _fallback_scrape(soup: BeautifulSoup) -> List[Event]:
    events = []
    links = soup.find_all("a", href=re.compile(r"/events/"))
    junk_titles = {"view event", "view events", "see all events", "see all"}
    seen = set()

    for link in links:
        title = link.get_text(" ", strip=True)
        if not title or len(title) < 5 or title.lower() in junk_titles:
            continue

        url = _absolute_url(link.get("href", ""))
        if _is_category_link(url) or url in seen:
            continue
        if not re.search(r"/events/\d+", url) and not re.search(r"/events/[a-z0-9-]{10,}", url):
            continue

        seen.add(url)
        events.append(Event(title=title, url=url, source="Visit North Yorkshire"))

    return events
