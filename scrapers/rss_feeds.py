import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
import re

from . import Event

WEB_SOURCES = [
    {
        "name": "Go Yorkshire",
        "url": "https://www.goyorkshire.com/events/",
        "type": "html",
    },
    {
        "name": "Whitby Events",
        "url": "https://www.whitbyevents.co.uk/index.php?com=events",
        "type": "html",
    },
    {
        "name": "What's On in Yorkshire",
        "url": "https://whatsoninyorkshire.co.uk/events/",
        "type": "html",
    },
    {
        "name": "What's On Yorkshire",
        "url": "https://whats-on-yorkshire.com/events/",
        "type": "html",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch_rss_feeds() -> List[Event]:
    events = []
    for source in WEB_SOURCES:
        try:
            print(f"  Scraping {source['name']}...")
            resp = requests.get(source["url"], headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            if source["name"] == "Go Yorkshire":
                events.extend(_parse_go_yorkshire(soup))
            elif source["name"] == "Whitby Events":
                events.extend(_parse_whitby_events(soup))
            elif source["name"] == "What's On in Yorkshire":
                events.extend(_parse_whats_on_in_yorkshire(soup))
            elif source["name"] == "What's On Yorkshire":
                events.extend(_parse_whats_on_yorkshire(soup))

        except Exception as e:
            print(f"    Error scraping {source['name']}: {e}")

    return events


def _parse_go_yorkshire(soup: BeautifulSoup) -> List[Event]:
    events = []
    seen = set()

    items = soup.select("div.jet-listing-dynamic-link, div.views-row, article, .event-item, .listing-item, .card, .node--type-event")
    for item in items:
        link_el = item.select_one("a[href*='/events/']")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href or href in seen or href.rstrip("/") == "https://www.goyorkshire.com/events":
            continue
        if not href.startswith("http"):
            href = "https://www.goyorkshire.com" + href
        seen.add(href)
        title = link_el.get_text(strip=True)
        if not title or len(title) < 3:
            title_el = item.select_one("h2, h3, h4, .title")
            title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3:
            continue

        date = None
        date_el = item.select_one("time, .date, .field-date, span.date, .event-date")
        if date_el:
            date_str = date_el.get("datetime") or date_el.get_text(strip=True)
            if date_str:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(date_str, dayfirst=True)
                except (ValueError, TypeError):
                    pass
        if not date:
            text = item.get_text()
            m = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\w*\s*(?:20\d{2})?', text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(m.group(0), dayfirst=True)
                except (ValueError, TypeError):
                    pass
        events.append(Event(
            title=title,
            url=href,
            source="Go Yorkshire",
            date=date,
        ))

    print(f"    Found {len(events)} events from Go Yorkshire")
    return events


def _parse_whitby_events(soup: BeautifulSoup) -> List[Event]:
    events = []
    items = soup.select("div.event, .event-item, .listing-item, article, .card, .views-row")
    if not items:
        items = soup.select("a[href*='com=detail']")
    seen = set()
    for item in items:
        link_el = item.select_one("a[href*='com=detail']") or item.select_one("a") if item.name != "a" else item
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href or href in seen:
            continue
        if not href.startswith("http"):
            href = "https://www.whitbyevents.co.uk" + href
        seen.add(href)
        title = ""
        if item.name == "a":
            title = item.get_text(strip=True)
        else:
            title_el = item.select_one("h2, h3, h4, a, .title")
            title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3:
            continue
        date = None
        date_el = item.select_one("time, .date, .event-date, span.date")
        if date_el:
            date_str = date_el.get("datetime") or date_el.get_text(strip=True)
            if date_str:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(date_str, dayfirst=True)
                except (ValueError, TypeError):
                    pass
        if not date:
            text = item.get_text()
            m = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\w*\s*(?:20\d{2})?', text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(m.group(0), dayfirst=True)
                except (ValueError, TypeError):
                    pass
        events.append(Event(
            title=title,
            url=href,
            source="Whitby Events",
            date=date,
        ))
    print(f"    Found {len(events)} events from Whitby Events")
    return events


def _parse_whats_on_in_yorkshire(soup: BeautifulSoup) -> List[Event]:
    events = []
    items = soup.select("div.post-item, article, .listing-item, .card, .views-row, .event-item")
    if not items:
        items = soup.select("a[href*='whats-on']")
    seen = set()
    for item in items:
        link_el = item.select_one("a") if item.name != "a" else item
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href or href in seen:
            continue
        if not href.startswith("http"):
            href = "https://whatsoninyorkshire.co.uk" + href
        seen.add(href)
        title = ""
        if item.name == "a":
            title = item.get_text(strip=True)
        else:
            title_el = item.select_one("h2, h3, h4, a, .title")
            title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3:
            continue
        date = None
        date_el = item.select_one("time, .date, span.date")
        if date_el:
            date_str = date_el.get("datetime") or date_el.get_text(strip=True)
            if date_str:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(date_str, dayfirst=True)
                except (ValueError, TypeError):
                    pass
        if not date:
            text = item.get_text()
            m = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\w*\s*(?:20\d{2})?', text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(m.group(0), dayfirst=True)
                except (ValueError, TypeError):
                    pass
        events.append(Event(
            title=title,
            url=href,
            source="What's On in Yorkshire",
            date=date,
        ))
    print(f"    Found {len(events)} events from What's On in Yorkshire")
    return events


def _parse_whats_on_yorkshire(soup: BeautifulSoup) -> List[Event]:
    events = []
    items = soup.select("div.post-item, article, .listing-item, .card, .views-row, .event-item, .tribe-events-calendar-list__event")
    if not items:
        items = soup.select("a[href*='event']")
    junk = {
        "events", "music", "sport", "family", "theatre", "comedy", "film",
        "food & drink", "heritage", "nightlife", "view event", "festivals",
        "family & kids", "live music", "arts & culture", "food and drink",
        "arts and culture", "horse racing", "other", "markets",
        "kids & family", "exhibitions", "talks", "discussions",
    }
    seen = set()
    for item in items:
        link_el = item.select_one("a") if item.name != "a" else item
        if not link_el:
            continue
        href = link_el.get("href", "")
        if not href or href in seen:
            continue
        if not href.startswith("http"):
            href = "https://whats-on-yorkshire.com" + href
        seen.add(href)
        title = ""
        if item.name == "a":
            title = item.get_text(strip=True)
        else:
            title_el = item.select_one("h2, h3, h4, a, .title")
            title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 3 or title.lower() in junk:
            continue
        date = None
        date_el = item.select_one("time, .date, span.date, .tribe-event-date-start")
        if date_el:
            date_str = date_el.get("datetime") or date_el.get_text(strip=True)
            if date_str:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(date_str, dayfirst=True)
                except (ValueError, TypeError):
                    pass
        if not date:
            text = item.get_text()
            m = re.search(r'(\d{1,2})\s*(?:st|nd|rd|th)?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\w*\s*(?:20\d{2})?', text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    date = dateparser.parse(m.group(0), dayfirst=True)
                except (ValueError, TypeError):
                    pass
        events.append(Event(
            title=title,
            url=href,
            source="What's On Yorkshire",
            date=date,
        ))
    print(f"    Found {len(events)} events from What's On Yorkshire")
    return events
