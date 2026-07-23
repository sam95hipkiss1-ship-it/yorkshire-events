"""Dedicated adapters for additional regional Yorkshire event sources."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from . import Event
from .generic_schemaorg import _events_from_soup

HEADERS = {
    "User-Agent": "ImFromYorkshireEventsBot/1.3 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 12)
ROBOTS_TIMEOUT = (4, 6)
MAX_SOURCE_SECONDS = 32
MAX_TOTAL_SECONDS = 230
WORKERS = 5
MAX_DESCRIPTION = 420

MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)
WEEKDAYS = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?"
DATE_TOKEN = rf"(?:{WEEKDAYS}\s+)?\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{2,4}})?"
DATE_RANGE_RE = re.compile(rf"(?P<start>{DATE_TOKEN})\s*(?:-|–|—|to|until)\s*(?P<end>{DATE_TOKEN})", re.I)
SINGLE_DATE_RE = re.compile(DATE_TOKEN, re.I)
TIME_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:-|–|—|to)\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.I,
)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)


def _ymt_urls(months: int = 5) -> Tuple[str, ...]:
    now = datetime.now().replace(day=1)
    return tuple(
        f"https://www.yorkmuseumstrust.org.uk/whats-on/events/?mo={month.month}&yr={month.year}"
        for month in (now + relativedelta(months=offset) for offset in range(months))
    )


SOURCES: Sequence[Dict[str, object]] = (
    {
        "name": "York Museums Trust",
        "entry_urls": _ymt_urls(),
        "link_contains": ("/whats-on/events/",),
        "exclude_queries": True,
        "max_details": 28,
    },
    {
        "name": "Leeds Museums and Galleries",
        "entry_urls": (
            "https://museumsandgalleries.leeds.gov.uk/whats-on?page=1",
            "https://museumsandgalleries.leeds.gov.uk/whats-on?page=2",
            "https://museumsandgalleries.leeds.gov.uk/whats-on/special-events",
            "https://museumsandgalleries.leeds.gov.uk/whats-on/under-5s-events",
        ),
        "link_contains": ("/whats-on/",),
        "max_details": 28,
    },
    {
        "name": "Visit Calderdale",
        "entry_urls": ("https://www.visitcalderdale.com/whats-on/",),
        "link_contains": ("/whats-on/",),
        "max_details": 24,
    },
    {
        "name": "Visit Doncaster",
        "entry_urls": (
            "https://www.visitdoncaster.com/whats-on/",
            "https://www.visitdoncaster.com/whats-on/family-friendly/",
            "https://www.visitdoncaster.com/whats-on/arts-and-culture/",
            "https://www.visitdoncaster.com/whats-on/sports-and-outdoors/",
        ),
        "link_contains": ("/whats-on/",),
        "max_details": 30,
    },
    {
        "name": "Visit Barnsley",
        "entry_urls": ("https://visitbarnsley.co.uk/whats-on",),
        "link_contains": ("/whats-on/",),
        "max_details": 24,
    },
    {
        "name": "Visit Rotherham",
        "entry_urls": ("https://www.visitrotherham.com/whats-on/",),
        "link_contains": ("/whats-on/",),
        "max_details": 24,
    },
    {
        "name": "Visit East Yorkshire",
        "entry_urls": ("https://www.visiteastyorkshire.co.uk/whats-on/event-calendar/",),
        "link_contains": ("/whats-on/",),
        "max_details": 28,
    },
    {
        "name": "Visit Hull",
        "entry_urls": ("https://www.visithull.org/whatson/",),
        "link_contains": ("/whatson/",),
        "max_details": 30,
    },
    {
        "name": "Hull What's On",
        "entry_urls": ("https://hullwhatson.com/events/",),
        "link_contains": ("/event/", "/events/"),
        "max_details": 24,
    },
)


def scrape_regional_sources() -> List[Event]:
    all_events: List[Event] = []
    started_all = time.monotonic()
    print(f"\n[Regional source adapters] {len(SOURCES)} configured", flush=True)

    for index, source in enumerate(SOURCES, 1):
        if time.monotonic() - started_all >= MAX_TOTAL_SECONDS:
            print("  Regional-source runtime cap reached; remaining sources deferred.", flush=True)
            break
        started = time.monotonic()
        try:
            source_events = scrape_source(source)
        except Exception as exc:
            print(f"  [{index}/{len(SOURCES)}] {source['name']}: failed safely ({exc})", flush=True)
            continue
        all_events.extend(source_events)
        print(
            f"  [{index}/{len(SOURCES)}] {source['name']}: {len(source_events)} events "
            f"in {time.monotonic() - started:.1f}s",
            flush=True,
        )
    return _dedupe(all_events)


def scrape_source(config: Dict[str, object]) -> List[Event]:
    urls = tuple(str(value) for value in config.get("entry_urls", ()))
    if not urls:
        return []
    robots = _load_robots(urls[0])
    if robots is None:
        print(f"    {config['name']}: robots.txt unavailable; skipped", flush=True)
        return []

    deadline = time.monotonic() + MAX_SOURCE_SECONDS
    direct: List[Event] = []
    candidates: List[str] = []
    for entry_url in urls:
        if time.monotonic() >= deadline:
            break
        if not robots.can_fetch(HEADERS["User-Agent"], entry_url):
            continue
        response = _get(entry_url)
        if not response:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        direct.extend(_events_from_soup(soup, entry_url, str(config["name"])))
        direct.extend(_events_from_cards(soup, entry_url, config))
        candidates.extend(_candidate_links(soup, entry_url, config))

    known = {event.url.split("#", 1)[0].rstrip("/").lower() for event in direct}
    detail_urls: List[str] = []
    for url in candidates:
        clean = url.split("#", 1)[0]
        key = clean.rstrip("/").lower()
        if key in known or clean in detail_urls or not robots.can_fetch(HEADERS["User-Agent"], clean):
            continue
        detail_urls.append(clean)
        if len(detail_urls) >= int(config.get("max_details", 20)):
            break

    details: List[Event] = []
    if detail_urls and time.monotonic() < deadline:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(detail_urls))) as executor:
            futures = {executor.submit(_events_from_detail, url, config): url for url in detail_urls}
            for future in as_completed(futures):
                if time.monotonic() >= deadline:
                    break
                try:
                    details.extend(future.result())
                except Exception:
                    continue
    return _dedupe(direct + details)


def _get(url: str) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "").lower()
        return response if "html" in content_type or "xml" in content_type else None
    except requests.RequestException:
        return None


def _load_robots(entry_url: str) -> Optional[RobotFileParser]:
    parsed = urlparse(entry_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    robot = RobotFileParser()
    robot.set_url(robots_url)
    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=ROBOTS_TIMEOUT)
        if response.status_code == 404:
            robot.parse([])
            return robot
        if response.status_code >= 400:
            return None
        robot.parse(response.text.splitlines())
        return robot
    except requests.RequestException:
        return None


def _candidate_links(soup: BeautifulSoup, page_url: str, config: Dict[str, object]) -> List[str]:
    page_domain = urlparse(page_url).netloc.lower().removeprefix("www.")
    tokens = tuple(str(value).lower() for value in config.get("link_contains", ()))
    links: List[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc.lower().removeprefix("www.") != page_domain:
            continue
        if tokens and not any(token in absolute.lower() for token in tokens):
            continue
        if config.get("exclude_queries") and parsed.query:
            continue
        text = _clean(anchor.get_text(" ", strip=True)).lower()
        if text in {"events", "what's on", "whats on", "view all", "see all", "calendar", "next", "previous"}:
            continue
        if parsed.path.rstrip("/") in {"/whats-on", "/whatson", "/events", "/whats-on/events"}:
            continue
        links.append(absolute)
    return list(dict.fromkeys(links))


def _events_from_cards(soup: BeautifulSoup, page_url: str, config: Dict[str, object]) -> List[Event]:
    candidate_set = set(_candidate_links(soup, page_url, config))
    events: List[Event] = []
    for anchor in soup.select("a[href]"):
        absolute = urljoin(page_url, anchor.get("href", ""))
        if absolute not in candidate_set:
            continue
        container = _nearest_dated_container(anchor)
        if container is None:
            continue
        title = _title(anchor, container)
        if len(title) < 4:
            continue
        occurrences = _occurrences(container)
        if not occurrences:
            continue
        description = _description(container, title)
        location = _location(container)
        category = _categories(container, absolute)
        for start, end, all_day in occurrences[:4]:
            events.append(Event(
                title=title,
                url=absolute,
                source=str(config["name"]),
                date=start,
                end_date=end,
                location=location,
                description=description,
                category=category,
                all_day=all_day,
            ))
    return _dedupe(events)


def _events_from_detail(url: str, config: Dict[str, object]) -> List[Event]:
    response = _get(url)
    if not response:
        return []
    soup = BeautifulSoup(response.text, "lxml")
    source = str(config["name"])
    structured = _events_from_soup(soup, url, source)
    if structured:
        return structured
    heading = soup.select_one("h1")
    title = _clean(heading.get_text(" ", strip=True)) if heading else ""
    occurrences = _occurrences(soup)
    if len(title) < 4 or not occurrences:
        return []
    meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
    description = _clean(meta.get("content", ""))[:MAX_DESCRIPTION] if meta else _description(soup, title)
    location = _location(soup)
    category = _categories(soup, url)
    return [
        Event(
            title=title,
            url=url,
            source=source,
            date=start,
            end_date=end,
            location=location,
            description=description,
            category=category,
            all_day=all_day,
        )
        for start, end, all_day in occurrences[:4]
    ]


def _nearest_dated_container(anchor: Tag) -> Optional[Tag]:
    node: Optional[Tag] = anchor
    best: Optional[Tag] = None
    for _ in range(9):
        node = node.parent if isinstance(node, Tag) else None
        if node is None or node.name in {"body", "html"}:
            break
        text = _clean(node.get_text(" ", strip=True))
        if len(text) > 5000:
            break
        if node.select_one("time[datetime]") or DATE_RANGE_RE.search(text) or SINGLE_DATE_RE.search(text):
            best = node
            if len(text) <= 1900:
                return node
    return best


def _occurrences(container: Tag) -> List[Tuple[datetime, Optional[datetime], bool]]:
    time_elements = container.select("time[datetime]")
    values: List[Tuple[datetime, str]] = []
    for element in time_elements:
        raw = element.get("datetime", "")
        parsed = _parse_date(raw)
        if parsed and all(existing[0] != parsed for existing in values):
            values.append((parsed, raw))
    if values:
        if len(values) >= 2 and values[1][0] >= values[0][0]:
            return [(values[0][0], values[1][0], _is_all_day(values[0][1]) and _is_all_day(values[1][1]))]
        return [(value, value, _is_all_day(raw)) for value, raw in values[:4]]

    text = _clean(container.get_text(" ", strip=True)).replace("Sept", "Sep")
    match = DATE_RANGE_RE.search(text)
    if match:
        end = _parse_date(match.group("end"))
        start = _parse_date(match.group("start"), fallback_year=end.year if end else None)
        if not start or not end:
            return []
        time_match = TIME_RANGE_RE.search(text)
        all_day = time_match is None
        if time_match:
            start = _apply_time(start, time_match.group("start"))
            end = _apply_time(end, time_match.group("end"))
        if end < start:
            end = end.replace(year=end.year + 1)
        return [(start, end, all_day)]

    match = SINGLE_DATE_RE.search(text)
    if not match:
        return []
    start = _parse_date(match.group(0))
    if not start:
        return []
    time_match = TIME_RANGE_RE.search(text)
    if time_match:
        return [( _apply_time(start, time_match.group("start")), _apply_time(start, time_match.group("end")), False )]
    return [(start, start, True)]


def _parse_date(value: object, fallback_year: Optional[int] = None) -> Optional[datetime]:
    if not value:
        return None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value), flags=re.I)
    cleaned = _clean(cleaned)
    if fallback_year and not re.search(r"\b\d{4}\b", cleaned):
        cleaned = f"{cleaned} {fallback_year}"
    try:
        parsed = dateparser.parse(cleaned, dayfirst=True, fuzzy=False)
        return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _apply_time(value: datetime, raw: str) -> datetime:
    parsed = dateparser.parse(raw, fuzzy=True)
    return value.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0) if parsed else value


def _is_all_day(value: object) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def _title(anchor: Tag, container: Tag) -> str:
    for element in container.select("h1, h2, h3, h4, h5"):
        value = _clean(element.get_text(" ", strip=True))
        if len(value) >= 4:
            return value[:220]
    return _clean(anchor.get_text(" ", strip=True))[:220]


def _description(container: Tag, title: str) -> Optional[str]:
    for paragraph in container.select("p"):
        value = _clean(paragraph.get_text(" ", strip=True))
        if len(value) >= 30 and value.lower() != title.lower() and not DATE_RANGE_RE.fullmatch(value):
            return value[:MAX_DESCRIPTION]
    return None


def _location(container: Tag) -> Optional[str]:
    for selector in (
        "address", "[itemprop='location']", "[itemprop='address']",
        "[class*='location']", "[class*='venue']", "[class*='address']",
    ):
        element = container.select_one(selector)
        if element:
            value = _clean(element.get_text(" ", strip=True))
            if 4 <= len(value) <= 240:
                return value
    text = _clean(container.get_text(" ", strip=True))
    match = re.search(r"(?:Venue|Location|Where)\s*:?\s*(.{4,220}?)(?=\s+(?:Date|Time|Tickets|Price|Book|Category)\b|$)", text, re.I)
    if match:
        return _clean(match.group(1))[:240]
    postcode = POSTCODE_RE.search(text)
    if postcode:
        start = max(0, postcode.start() - 110)
        return _clean(text[start:postcode.end()])[-240:]
    return None


def _categories(container: Tag, url: str) -> Optional[str]:
    values: List[str] = []
    for selector in ("[class*='category']", "[class*='event-type']", "[rel='tag']", ".tag", ".tags a"):
        for element in container.select(selector):
            value = _clean(element.get_text(" ", strip=True))
            if 2 <= len(value) <= 80 and value.lower() not in {item.lower() for item in values}:
                values.append(value)
            if len(values) >= 6:
                break
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    known = {
        "family-friendly": "Family Days Out", "arts-and-culture": "Theatre & Arts",
        "sports-and-outdoors": "Sport", "food-and-drink": "Food & Drink",
        "festival": "Festivals", "comedy": "Comedy", "music": "Gigs",
    }
    for part in path_parts:
        if part in known and known[part] not in values:
            values.append(known[part])
    return ", ".join(values[:6]) or None


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe(events: Iterable[Event]) -> List[Event]:
    seen = set()
    result = []
    for event in events:
        key = (event.url.rstrip("/").lower(), event.date.isoformat() if event.date else "", event.title.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result
