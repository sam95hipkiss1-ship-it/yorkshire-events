import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser as dateparser
import re
import json

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
        resp = requests.get(EVENTS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        event_cards = soup.select("div.event-card, article.event, div.listing-item, div.event-item")

        if not event_cards:
            event_cards = soup.select("a[href*='/events/']")

        for card in event_cards:
            event = _parse_event_card(card)
            if event:
                events.append(event)

        if not events:
            events = _extract_events_from_json(soup)

        if not events:
            events = _fallback_scrape(soup)

    except Exception as e:
        print(f"    Error fetching Visit North Yorkshire: {e}")

    print(f"    Found {len(events)} events from Visit North Yorkshire")
    return events


def _parse_event_card(card) -> Event:
    title_elem = card.select_one("h2, h3, h4, .event-title, .listing-title")
    if not title_elem:
        if card.name == "a":
            title_elem = card
        else:
            return None

    title = title_elem.get_text(strip=True)
    if not title or len(title) < 3:
        return None

    url = ""
    if card.name == "a":
        url = card.get("href", "")
    else:
        link = card.select_one("a[href*='/events/']")
        if link:
            url = link.get("href", "")

    if url and not url.startswith("http"):
        url = f"{BASE_URL}{url}" if url.startswith("/") else f"{BASE_URL}/{url}"

    if _is_category_link(url):
        return None

    date_text = ""
    date_elem = card.select_one("time, .date, .event-date, .listing-date")
    if date_elem:
        date_text = date_elem.get("datetime", date_elem.get_text(strip=True))

    location = ""
    location_elem = card.select_one(".location, .venue, .place")
    if location_elem:
        location = location_elem.get_text(strip=True)

    description = ""
    desc_elem = card.select_one("p, .description, .excerpt")
    if desc_elem:
        description = desc_elem.get_text(strip=True)

    date = None
    if date_text:
        try:
            date = dateparser.parse(date_text, dayfirst=True)
        except (ValueError, TypeError):
            pass

    return Event(
        title=title,
        url=url or EVENTS_URL,
        source="Visit North Yorkshire",
        date=date,
        location=location,
        description=description[:500] if description else None,
    )


def _extract_events_from_json(soup: BeautifulSoup) -> List[Event]:
    events = []
    scripts = soup.find_all("script", type="application/json")

    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and ("title" in item or "name" in item):
                        event = _json_to_event(item)
                        if event:
                            events.append(event)
            elif isinstance(data, dict):
                for key in ["events", "items", "results"]:
                    if key in data and isinstance(data[key], list):
                        for item in data[key]:
                            if isinstance(item, dict):
                                event = _json_to_event(item)
                                if event:
                                    events.append(event)
        except (json.JSONDecodeError, TypeError):
            continue

    return events


def _json_to_event(data: dict) -> Event:
    title = data.get("title") or data.get("name") or ""
    if not title:
        return None

    url = data.get("url") or data.get("link") or ""
    if url and not url.startswith("http"):
        url = f"{BASE_URL}{url}" if url.startswith("/") else f"{BASE_URL}/{url}"

    date = None
    for key in ["date", "start_date", "startDate", "eventDate"]:
        if key in data and data[key]:
            try:
                date = dateparser.parse(str(data[key]), dayfirst=True)
                break
            except (ValueError, TypeError):
                continue

    location = data.get("location") or data.get("venue") or ""

    return Event(
        title=title.strip(),
        url=url or EVENTS_URL,
        source="Visit North Yorkshire",
        date=date,
        location=location if isinstance(location, str) else "",
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
    "country-shows", "entertainment", "live-music", "comedy", "theatre",
]


def _is_category_link(url: str) -> bool:
    url_lower = url.lower()
    for pattern in CATEGORY_PATTERNS:
        if pattern in url_lower:
            return True
    if url_lower.endswith("/events") or url_lower.endswith("/events/"):
        return True
    return False


def _fallback_scrape(soup: BeautifulSoup) -> List[Event]:
    events = []
    links = soup.find_all("a", href=re.compile(r"/events/"))

    for link in links:
        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        url = link.get("href", "")
        if url and not url.startswith("http"):
            url = f"{BASE_URL}{url}" if url.startswith("/") else f"{BASE_URL}/{url}"

        if _is_category_link(url):
            continue

        if not re.search(r"/events/\d+", url) and not re.search(r"/events/[a-z0-9-]{10,}", url):
            continue

        events.append(Event(
            title=title,
            url=url or EVENTS_URL,
            source="Visit North Yorkshire",
        ))

    return events
