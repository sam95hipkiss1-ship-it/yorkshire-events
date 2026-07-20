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

BASE_URL = "https://www.yorkshire.com"
EVENTS_URL = f"{BASE_URL}/events"

CATEGORIES = [
    "music", "theatre", "festivals", "sport", "family",
    "arts", "food-drink", "heritage", "comedy",
]


def scrape_yorkshire_com() -> List[Event]:
    events = []
    print("  Fetching Yorkshire.com events...")

    try:
        resp = requests.get(EVENTS_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        event_cards = soup.select("article, div.event-card, div.listing-item, div.event-item")

        if not event_cards:
            event_cards = soup.select("a[href*='/events/']")

        for card in event_cards:
            event = _parse_event_card(card)
            if event:
                events.append(event)

        if not events:
            events = _extract_from_next_data(soup)

        if not events:
            events = _fallback_scrape(soup)

        for category in CATEGORIES:
            try:
                cat_events = _scrape_category(category)
                events.extend(cat_events)
            except Exception as e:
                print(f"    Error scraping category {category}: {e}")

    except Exception as e:
        print(f"    Error fetching Yorkshire.com: {e}")

    print(f"    Found {len(events)} events from Yorkshire.com")
    return events


def _scrape_category(category: str) -> List[Event]:
    url = f"{EVENTS_URL}/{category}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    event_cards = soup.select("article, div.event-card, div.listing-item")

    for card in event_cards:
        event = _parse_event_card(card)
        if event:
            event.category = category.replace("-", " ").title()
            events.append(event)

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

    category = ""
    cat_elem = card.select_one(".category, .tag, .event-type")
    if cat_elem:
        category = cat_elem.get_text(strip=True)

    date = None
    if date_text:
        try:
            date = dateparser.parse(date_text, dayfirst=True)
        except (ValueError, TypeError):
            pass

    return Event(
        title=title,
        url=url or EVENTS_URL,
        source="Yorkshire.com",
        date=date,
        location=location,
        description=description[:500] if description else None,
        category=category,
    )


def _extract_from_next_data(soup: BeautifulSoup) -> List[Event]:
    events = []
    script = soup.find("script", id="__NEXT_DATA__")

    if script and script.string:
        try:
            data = json.loads(script.string)
            props = data.get("props", {}).get("pageProps", {})

            for key in ["events", "items", "results", "data"]:
                if key in props and isinstance(props[key], list):
                    for item in props[key]:
                        if isinstance(item, dict):
                            event = _json_to_event(item)
                            if event:
                                events.append(event)
        except (json.JSONDecodeError, TypeError):
            pass

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
    if isinstance(location, dict):
        location = location.get("name", "")

    return Event(
        title=title.strip(),
        url=url or EVENTS_URL,
        source="Yorkshire.com",
        date=date,
        location=location if isinstance(location, str) else "",
    )


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

        events.append(Event(
            title=title,
            url=url or EVENTS_URL,
            source="Yorkshire.com",
        ))

    return events
