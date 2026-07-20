import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List
from dateutil import parser as dateparser
import re

from . import Event

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

CITIES = [
    "Barnsley", "Bradford", "Bridlington", "Dewsbury", "Doncaster",
    "Halifax", "Harrogate", "Hebden Bridge", "Holmfirth", "Huddersfield",
    "Hull", "Ilkley", "Leeds", "Malton", "Masham", "Pocklington",
    "Rotherham", "Saltaire", "Scarborough", "Settle", "Sheffield",
    "Sowerby Bridge", "Wetherby", "Whitby", "York",
]


def scrape_yorkshiregigs() -> List[Event]:
    events = []
    print("  Fetching Yorkshire Gig Guide...")

    for city in CITIES:
        try:
            city_events = _scrape_city(city)
            events.extend(city_events)
        except Exception as e:
            print(f"    Error scraping {city}: {e}")

    print(f"    Found {len(events)} events from Yorkshire Gig Guide")
    return events


def _scrape_city(city: str) -> List[Event]:
    url = f"https://www.yorkshiregigs.co.uk/w_city_by_date_{city.replace(' ', '_')}.html"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    event_items = soup.select("div.event-item, div.gig-item, tr.event-row, div.listing-item")

    if not event_items:
        event_items = soup.select("a[href*='w_event_']")

    for item in event_items:
        event = _parse_event_item(item, city)
        if event:
            events.append(event)

    if not events:
        event_links = soup.find_all("a", href=re.compile(r"w_event_\d+"))
        for link in event_links:
            event = _parse_event_link(link, city)
            if event:
                events.append(event)

    return events


def _parse_event_item(item, city: str) -> Event:
    title_elem = item.select_one("h3, h4, .event-title, .gig-title, a[href*='w_event_']")
    if not title_elem:
        return None

    title = title_elem.get_text(strip=True)
    if not title:
        return None

    url = ""
    if title_elem.name == "a":
        url = title_elem.get("href", "")
    else:
        link = item.select_one("a[href*='w_event_']")
        if link:
            url = link.get("href", "")

    if url and not url.startswith("http"):
        url = f"https://www.yorkshiregigs.co.uk/{url.lstrip('/')}"

    date_text = ""
    date_elem = item.select_one(".date, .event-date, time, .gig-date")
    if date_elem:
        date_text = date_elem.get_text(strip=True)

    venue = ""
    venue_elem = item.select_one(".venue, .location, .gig-venue")
    if venue_elem:
        venue = venue_elem.get_text(strip=True)

    date = None
    if date_text:
        try:
            date = dateparser.parse(date_text, dayfirst=True)
        except (ValueError, TypeError):
            pass

    return Event(
        title=title,
        url=url or f"https://www.yorkshiregigs.co.uk/w_city_by_date_{city.replace(' ', '_')}.html",
        source="Yorkshire Gig Guide",
        date=date,
        location=f"{venue}, {city}" if venue else city,
        category="Music",
    )


def _parse_event_link(link, city: str) -> Event:
    title = link.get_text(strip=True)
    if not title or len(title) < 3:
        return None

    url = link.get("href", "")
    if url and not url.startswith("http"):
        url = f"https://www.yorkshiregigs.co.uk/{url.lstrip('/')}"

    parent = link.parent
    date_text = ""
    if parent:
        time_elem = parent.select_one("time, .date, .event-date")
        if time_elem:
            date_text = time_elem.get_text(strip=True)

    date = None
    if date_text:
        try:
            date = dateparser.parse(date_text, dayfirst=True)
        except (ValueError, TypeError):
            pass

    return Event(
        title=title,
        url=url or "",
        source="Yorkshire Gig Guide",
        date=date,
        location=city,
        category="Music",
    )
