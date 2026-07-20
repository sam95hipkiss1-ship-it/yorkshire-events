import feedparser
import requests
from datetime import datetime
from typing import List
from dateutil import parser as dateparser

from . import Event

RSS_SOURCES = [
    {
        "name": "What's On in Yorkshire",
        "url": "https://whatsoninyorkshire.co.uk/feed/",
        "type": "rss",
    },
    {
        "name": "Go Yorkshire",
        "url": "https://www.goyorkshire.com/events/feed/",
        "type": "rss",
    },
    {
        "name": "Whitby Events",
        "url": "https://www.whitbyevents.co.uk/rss/",
        "type": "rss",
    },
    {
        "name": "What's On Yorkshire",
        "url": "https://whats-on-yorkshire.com/feed/",
        "type": "rss",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YorkshireEventsBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_rss_feeds() -> List[Event]:
    events = []
    for source in RSS_SOURCES:
        try:
            print(f"  Fetching RSS: {source['name']}...")
            resp = requests.get(source["url"], headers=HEADERS, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            count = 0
            for entry in feed.entries:
                event = _parse_rss_entry(entry, source["name"])
                if event:
                    events.append(event)
                    count += 1

            print(f"    Found {count} events from {source['name']}")
        except Exception as e:
            print(f"    Error fetching {source['name']}: {e}")

    return events


def _parse_rss_entry(entry, source_name: str) -> Event:
    title = entry.get("title", "").strip()
    if not title:
        return None

    url = entry.get("link", "")
    if not url:
        return None

    description = ""
    if hasattr(entry, "summary"):
        description = entry.summary
    elif hasattr(entry, "description"):
        description = entry.description

    import re
    description = re.sub(r"<[^>]+>", "", description).strip()

    date = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            date = datetime(*entry.published_parsed[:6])
        except (TypeError, ValueError):
            pass
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            date = datetime(*entry.updated_parsed[:6])
        except (TypeError, ValueError):
            pass

    if not date:
        date_str = entry.get("published", entry.get("updated", ""))
        if date_str:
            try:
                date = dateparser.parse(date_str)
            except (ValueError, TypeError):
                pass

    return Event(
        title=title,
        url=url,
        source=source_name,
        date=date,
        description=description[:500] if description else None,
    )
