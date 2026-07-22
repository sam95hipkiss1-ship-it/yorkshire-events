"""Dedicated collectors for Yorkshire family event sources.

These sites use a mix of Modern Events Calendar, The Events Calendar,
Schema.org data and custom listing cards. This module reads structured data
first, then falls back to dated cards and a limited number of detail pages.
"""
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
    "User-Agent": "ImFromYorkshireEventsBot/1.2 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 11)
ROBOTS_TIMEOUT = (4, 6)
MAX_SOURCE_SECONDS = 35
MAX_TOTAL_SECONDS = 240
DETAIL_WORKERS = 6
MAX_DESCRIPTION = 360

MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)
WEEKDAYS = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?"
TEXT_DATE = (
    rf"(?:{WEEKDAYS}\s+)?"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{2,4}})?"
)
NUMERIC_DATE = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
DATE_VALUE = rf"(?:{TEXT_DATE}|{NUMERIC_DATE})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{DATE_VALUE})\s*(?:-|–|—|to|until)\s*(?P<end>{DATE_VALUE})",
    re.IGNORECASE,
)
DATE_TOKEN_RE = re.compile(DATE_VALUE, re.IGNORECASE)
TIME_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    re.IGNORECASE,
)


def _mumbler_month_urls(base: str, months: int = 4) -> Tuple[str, ...]:
    now = datetime.now().replace(day=1)
    urls = [f"{base}/events/"]
    for offset in range(months):
        month = now + relativedelta(months=offset)
        urls.append(f"{base}/events/month/{month:%Y-%m}/")
    return tuple(dict.fromkeys(urls))


SOURCE_CONFIGS: Sequence[Dict[str, object]] = (
    {
        "name": "Little Vikings",
        "entry_urls": ("https://little-vikings.co.uk/events/",),
        "link_contains": ("/events/",),
        "exclude_exact": ("https://little-vikings.co.uk/events",),
        "default_location": "York",
        "max_details": 30,
        "cards": False,
    },
    {
        "name": "York Mumbler",
        "entry_urls": _mumbler_month_urls("https://york.mumbler.co.uk"),
        "link_contains": ("/event/",),
        "default_location": "York",
        "max_details": 18,
    },
    {
        "name": "North Leeds Mumbler",
        "entry_urls": _mumbler_month_urls("https://northleeds.mumbler.co.uk"),
        "link_contains": ("/event/",),
        "default_location": "Leeds",
        "max_details": 18,
    },
    {
        "name": "Hull and East Riding Mumbler",
        "entry_urls": _mumbler_month_urls("https://hullandeastriding.mumbler.co.uk"),
        "link_contains": ("/event/",),
        "default_location": "Hull and East Yorkshire",
        "max_details": 18,
    },
    {
        "name": "Ryedale Mumbler",
        "entry_urls": _mumbler_month_urls("https://ryedale.mumbler.co.uk"),
        "link_contains": ("/event/",),
        "default_location": "Ryedale and Thirsk",
        "max_details": 18,
    },
    {
        "name": "Yorkshire Wildlife Park",
        "entry_urls": (
            "https://www.yorkshirewildlifepark.com/whats-on/special-events/",
            "https://www.yorkshirewildlifepark.com/whats-on/",
        ),
        "link_contains": ("/whats-on/special-events/",),
        "exclude_exact": ("https://www.yorkshirewildlifepark.com/whats-on/special-events",),
        "default_location": "Yorkshire Wildlife Park, Doncaster",
        "max_details": 24,
    },
    {
        "name": "Stockeld Park",
        "entry_urls": ("https://stockeldpark.co.uk/activities/season/",),
        "link_contains": ("/activities/season/",),
        "exclude_exact": ("https://stockeldpark.co.uk/activities/season",),
        "default_location": "Stockeld Park, Wetherby",
        "max_details": 18,
    },
    {
        "name": "Eureka! Science + Discovery",
        "entry_urls": ("https://discover.eureka.org.uk/whats-on/",),
        "link_contains": ("/event/",),
        "default_location": "Eureka! Science + Discovery",
        "max_details": 24,
    },
    {
        "name": "The Deep",
        "entry_urls": ("https://www.thedeep.co.uk/visit/whats-on?PageSpeed=noscript",),
        "link_contains": ("/visit/whats-on", "/event", "/events"),
        "exclude_exact": ("https://www.thedeep.co.uk/visit/whats-on",),
        "default_location": "The Deep, Hull",
        "max_details": 16,
    },
    {
        "name": "Web Adventure Park",
        "entry_urls": ("https://www.webadventurepark.co.uk/events/",),
        "link_contains": ("/events/", "tickets.webadventurepark.co.uk"),
        "exclude_exact": ("https://www.webadventurepark.co.uk/events",),
        "default_location": "Web Adventure Park, York",
        "max_details": 16,
        "allow_external": True,
    },
    {
        "name": "Lightwater Valley",
        "entry_urls": (
            "https://lightwatervalley.co.uk/",
            "https://lightwatervalley.co.uk/calendar",
        ),
        "link_contains": ("/events/view/",),
        "default_location": "Lightwater Valley, Ripon",
        "max_details": 24,
    },
)


def scrape_family_sources() -> List[Event]:
    events: List[Event] = []
    overall_started = time.monotonic()
    print(f"\n[Family source adapters] {len(SOURCE_CONFIGS)} configured", flush=True)

    for index, config in enumerate(SOURCE_CONFIGS, start=1):
        if time.monotonic() - overall_started >= MAX_TOTAL_SECONDS:
            print("  Family-source runtime cap reached; remaining sources deferred.", flush=True)
            break
        started = time.monotonic()
        try:
            source_events = scrape_family_source(config)
            events.extend(source_events)
            print(
                f"  [{index}/{len(SOURCE_CONFIGS)}] {config['name']}: "
                f"{len(source_events)} events in {time.monotonic() - started:.1f}s",
                flush=True,
            )
        except Exception as exc:
            print(f"  [{index}/{len(SOURCE_CONFIGS)}] {config['name']}: failed safely ({exc})", flush=True)

    return _dedupe(events)


def scrape_family_source(config: Dict[str, object]) -> List[Event]:
    entry_urls = tuple(str(value) for value in config.get("entry_urls", ()))
    if not entry_urls:
        return []

    robots = _load_robots(entry_urls[0])
    if robots is None:
        print(f"    {config['name']}: robots.txt unavailable; skipped", flush=True)
        return []

    deadline = time.monotonic() + MAX_SOURCE_SECONDS
    source_name = str(config["name"])
    direct_events: List[Event] = []
    candidates: List[str] = []

    for entry_url in entry_urls:
        if time.monotonic() >= deadline:
            break
        if not robots.can_fetch(HEADERS["User-Agent"], entry_url):
            print(f"    {source_name}: robots.txt disallows {entry_url}", flush=True)
            continue
        response = _get(entry_url)
        if not response:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        direct_events.extend(_apply_defaults(
            _events_from_soup(soup, entry_url, source_name),
            config,
        ))
        if config.get("cards", True):
            direct_events.extend(_events_from_cards(soup, entry_url, config))
        candidates.extend(_candidate_links(soup, entry_url, config))

    known_urls = {event.url.split("#", 1)[0].rstrip("/").lower() for event in direct_events}
    detail_urls: List[str] = []
    max_details = int(config.get("max_details", 16))
    for url in candidates:
        clean = url.split("#", 1)[0]
        key = clean.rstrip("/").lower()
        if key in known_urls or clean in detail_urls:
            continue
        if not robots.can_fetch(HEADERS["User-Agent"], clean):
            continue
        detail_urls.append(clean)
        if len(detail_urls) >= max_details:
            break

    detail_events: List[Event] = []
    if detail_urls and time.monotonic() < deadline:
        with ThreadPoolExecutor(max_workers=min(DETAIL_WORKERS, len(detail_urls))) as executor:
            futures = {
                executor.submit(_events_from_detail, url, config): url
                for url in detail_urls
            }
            for future in as_completed(futures):
                if time.monotonic() >= deadline:
                    break
                try:
                    detail_events.extend(future.result())
                except Exception:
                    pass

    return _dedupe(direct_events + detail_events)


def _get(url: str) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xml" not in content_type:
            return None
        return response
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
    links: List[str] = []
    source_domain = urlparse(page_url).netloc.lower().removeprefix("www.")
    contains = tuple(str(value).lower() for value in config.get("link_contains", ()))
    excluded = {str(value).rstrip("/").lower() for value in config.get("exclude_exact", ())}

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        domain = parsed.netloc.lower().removeprefix("www.")
        if not config.get("allow_external") and domain != source_domain:
            continue
        if contains and not any(token in absolute.lower() for token in contains):
            continue
        if absolute.rstrip("/").lower() in excluded:
            continue
        text = _clean(anchor.get_text(" ", strip=True)).lower()
        if text in {"events", "what's on", "whats on", "view all", "see all", "calendar"}:
            continue
        links.append(absolute)
    return list(dict.fromkeys(links))


def _events_from_cards(soup: BeautifulSoup, page_url: str, config: Dict[str, object]) -> List[Event]:
    events: List[Event] = []
    source_name = str(config["name"])
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        if absolute not in _candidate_links_for_anchor(anchor, page_url, config):
            continue
        container = _nearest_dated_container(anchor)
        if container is None:
            continue
        title = _title(anchor, container)
        if len(title) < 3:
            continue
        occurrences = _occurrences(container)
        if not occurrences:
            continue
        description = _description(container, title)
        categories = _native_categories(container)
        location = _location(container) or str(config.get("default_location") or "")
        for start, end, all_day in occurrences[:4]:
            events.append(Event(
                title=title,
                url=absolute,
                source=source_name,
                date=start,
                end_date=end,
                location=location or None,
                description=description,
                category=_combined_category(categories),
                all_day=all_day,
            ))
    return _dedupe(events)


def _candidate_links_for_anchor(anchor: Tag, page_url: str, config: Dict[str, object]) -> set[str]:
    href = anchor.get("href", "").strip()
    if not href:
        return set()
    absolute = urljoin(page_url, href)
    contains = tuple(str(value).lower() for value in config.get("link_contains", ()))
    excluded = {str(value).rstrip("/").lower() for value in config.get("exclude_exact", ())}
    page_domain = urlparse(page_url).netloc.lower().removeprefix("www.")
    link_domain = urlparse(absolute).netloc.lower().removeprefix("www.")
    if not config.get("allow_external") and page_domain != link_domain:
        return set()
    if contains and not any(token in absolute.lower() for token in contains):
        return set()
    if absolute.rstrip("/").lower() in excluded:
        return set()
    return {absolute}


def _nearest_dated_container(anchor: Tag) -> Optional[Tag]:
    node: Optional[Tag] = anchor
    best: Optional[Tag] = None
    for _ in range(9):
        node = node.parent if isinstance(node, Tag) else None
        if node is None or node.name in {"body", "html"}:
            break
        text = _clean(node.get_text(" ", strip=True))
        if len(text) > 4500:
            break
        if node.select_one("time[datetime]") or _occurrences_from_text(text):
            best = node
            if len(text) <= 1600:
                return node
    return best


def _events_from_detail(url: str, config: Dict[str, object]) -> List[Event]:
    response = _get(url)
    if not response:
        return []
    soup = BeautifulSoup(response.text, "lxml")
    source_name = str(config["name"])
    structured = _apply_defaults(_events_from_soup(soup, url, source_name), config)
    if structured:
        return structured

    heading = soup.select_one("h1")
    title = _clean(heading.get_text(" ", strip=True)) if heading else ""
    if len(title) < 3:
        return []
    occurrences = _occurrences(soup)
    if not occurrences:
        return []
    meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
    description = _clean(meta.get("content", ""))[:MAX_DESCRIPTION] if meta else _description(soup, title)
    categories = _native_categories(soup)
    location = _location(soup) or str(config.get("default_location") or "")
    return [
        Event(
            title=title,
            url=url,
            source=source_name,
            date=start,
            end_date=end,
            location=location or None,
            description=description or None,
            category=_combined_category(categories),
            all_day=all_day,
        )
        for start, end, all_day in occurrences[:4]
    ]


def _apply_defaults(events: Iterable[Event], config: Dict[str, object]) -> List[Event]:
    result = []
    for event in events:
        native = event.category or ""
        event.category = _combined_category([native] if native else [])
        if not event.location and config.get("default_location"):
            event.location = str(config["default_location"])
        result.append(event)
    return result


def _combined_category(native: Iterable[str]) -> str:
    values = ["Family Days Out"]
    for value in native:
        cleaned = _clean(str(value))
        if cleaned and cleaned.lower() not in {item.lower() for item in values}:
            values.append(cleaned[:100])
    return ", ".join(values)


def _occurrences(container: Tag) -> List[Tuple[datetime, Optional[datetime], bool]]:
    time_values = []
    for element in container.select("time[datetime]"):
        value = element.get("datetime")
        parsed = _parse_date(value)
        if parsed and parsed not in time_values:
            time_values.append(parsed)
    if time_values:
        if len(time_values) == 2 and time_values[1] >= time_values[0]:
            return [(time_values[0], time_values[1], _is_all_day_value(container.select_one("time[datetime]").get("datetime")))]
        return [(value, value, _is_all_day_value(element.get("datetime"))) for value, element in zip(time_values[:4], container.select("time[datetime]")[:4])]
    return _occurrences_from_text(_clean(container.get_text(" ", strip=True)))


def _occurrences_from_text(text: str) -> List[Tuple[datetime, Optional[datetime], bool]]:
    text = text.replace("Sept", "Sep")
    range_match = DATE_RANGE_RE.search(text)
    if range_match:
        end = _parse_date(range_match.group("end"))
        if not end:
            return []
        start = _parse_date(range_match.group("start"), fallback_year=end.year)
        if not start:
            return []
        time_match = TIME_RANGE_RE.search(text)
        all_day = time_match is None
        if time_match:
            start = _apply_time(start, time_match.group("start"))
            end = _apply_time(end, time_match.group("end"))
        if end < start:
            end = end.replace(year=end.year + 1)
        return [(start, end, all_day)]

    results = []
    for match in DATE_TOKEN_RE.finditer(text):
        value = _parse_date(match.group(0))
        if value and all(existing[0].date() != value.date() for existing in results):
            results.append((value, value, True))
        if len(results) >= 4:
            break
    return results


def _parse_date(value: object, fallback_year: Optional[int] = None) -> Optional[datetime]:
    if value is None:
        return None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value), flags=re.I)
    cleaned = _clean(cleaned)
    has_year = bool(re.search(r"\b\d{4}\b", cleaned))
    if fallback_year and not has_year:
        cleaned = f"{cleaned} {fallback_year}"
    try:
        parsed = dateparser.parse(cleaned, dayfirst=True, fuzzy=False)
        return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _apply_time(value: datetime, raw: str) -> datetime:
    parsed = dateparser.parse(raw.strip(), fuzzy=True)
    if not parsed:
        return value
    return value.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)


def _is_all_day_value(value: object) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def _title(anchor: Tag, container: Tag) -> str:
    for element in container.select("h1, h2, h3, h4, h5"):
        value = _clean(element.get_text(" ", strip=True))
        if len(value) >= 3:
            return value[:220]
    value = _clean(anchor.get_text(" ", strip=True))
    return value[:220]


def _description(container: Tag, title: str) -> Optional[str]:
    for paragraph in container.select("p"):
        value = _clean(paragraph.get_text(" ", strip=True))
        if len(value) >= 35 and value.lower() != title.lower() and not DATE_RANGE_RE.fullmatch(value):
            return value[:MAX_DESCRIPTION]
    return None


def _location(container: Tag) -> Optional[str]:
    for selector in ("address", "[class*='location']", "[class*='venue']", "[class*='place']"):
        element = container.select_one(selector)
        if element:
            value = _clean(element.get_text(" ", strip=True))
            if 2 < len(value) <= 240:
                return value
    return None


def _native_categories(container: Tag) -> List[str]:
    values = []
    selectors = (
        "a[rel='tag']", "a[href*='event-category']", "a[href*='/category/']",
        "[class*='category'] a", "[class*='categories'] a", "[class*='tag'] a",
    )
    for element in container.select(", ".join(selectors)):
        value = _clean(element.get_text(" ", strip=True))
        if 2 < len(value) <= 80 and value.lower() not in {item.lower() for item in values}:
            values.append(value)
        if len(values) >= 6:
            break
    return values


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _dedupe(events: Iterable[Event]) -> List[Event]:
    seen = set()
    result = []
    for event in events:
        key = (
            event.url.split("#", 1)[0].rstrip("/").lower(),
            event.date.isoformat() if event.date else "",
            event.title.lower().strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result
