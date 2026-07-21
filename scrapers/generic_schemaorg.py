import json
import re
import time
from datetime import datetime
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import Event
from .source_registry import GENERIC_SOURCES, SourceConfig


HEADERS = {
    "User-Agent": "ImFromYorkshireEventsBot/1.0 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SECONDS = 0.15
MAX_EXCERPT = 320


def scrape_registered_sources() -> List[Event]:
    events: List[Event] = []
    active = [source for source in GENERIC_SOURCES if source.enabled]
    print(f"\n[Generic sources] {len(active)} enabled")

    for index, source in enumerate(active, start=1):
        try:
            source_events = scrape_source(source)
            events.extend(source_events)
            print(f"  [{index}/{len(active)}] {source.name}: {len(source_events)} events")
        except Exception as exc:
            print(f"  [{index}/{len(active)}] {source.name}: failed safely ({exc})")

    return events


def scrape_source(source: SourceConfig) -> List[Event]:
    session = requests.Session()
    session.headers.update(HEADERS)
    discovered_urls: List[str] = []
    direct_events: List[Event] = []

    for entry_url in source.entry_urls:
        if not _robots_allowed(session, entry_url):
            print(f"    robots.txt disallows {entry_url}")
            continue
        response = _get(session, entry_url)
        if not response:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        direct_events.extend(_events_from_soup(soup, entry_url, source.name))
        discovered_urls.extend(_discover_event_links(soup, entry_url, source))

    unique_urls: List[str] = []
    seen_urls: Set[str] = set()
    for url in discovered_urls:
        clean = url.split("#", 1)[0]
        if clean not in seen_urls:
            seen_urls.add(clean)
            unique_urls.append(clean)

    page_events: List[Event] = []
    for url in unique_urls[: source.max_detail_pages]:
        if not _robots_allowed(session, url):
            continue
        response = _get(session, url)
        if not response:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        page_events.extend(_events_from_soup(soup, url, source.name))
        time.sleep(REQUEST_DELAY_SECONDS)

    return _dedupe_local(direct_events + page_events)


def _get(session: requests.Session, url: str) -> Optional[requests.Response]:
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type:
            return None
        return response
    except requests.RequestException:
        return None


def _robots_allowed(session: requests.Session, url: str) -> bool:
    parsed = urlparse(url)
    parser = RobotFileParser()
    parser.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        response = session.get(parser.url, timeout=8)
        if response.status_code == 404:
            return True
        if response.status_code >= 400:
            return False
        parser.parse(response.text.splitlines())
        return parser.can_fetch(HEADERS["User-Agent"], url)
    except requests.RequestException:
        return False


def _discover_event_links(soup: BeautifulSoup, base_url: str, source: SourceConfig) -> List[str]:
    links: List[str] = []
    source_domain = source.domain.lower().lstrip("www.")

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        domain = parsed.netloc.lower().lstrip("www.")
        if not (domain == source_domain or domain.endswith(f".{source_domain}")):
            continue
        path = parsed.path.lower()
        if not any(token.lower() in path for token in source.include_paths):
            continue
        if path.rstrip("/") in ("/events", "/whats-on", "/whatson"):
            continue
        text = anchor.get_text(" ", strip=True).lower()
        if text in {"events", "what's on", "whats on", "what’s on", "view all", "see all"}:
            continue
        links.append(absolute)
    return links


def _events_from_soup(soup: BeautifulSoup, page_url: str, source_name: str) -> List[Event]:
    events: List[Event] = []
    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_json(payload):
            if _is_event_node(node):
                event = _event_from_jsonld(node, page_url, source_name)
                if event:
                    events.append(event)

    if not events:
        fallback = _fallback_event_from_page(soup, page_url, source_name)
        if fallback:
            events.append(fallback)
    return events


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _is_event_node(node: Dict[str, Any]) -> bool:
    event_type = node.get("@type")
    types = event_type if isinstance(event_type, list) else [event_type]
    return any(str(value).lower() == "event" or str(value).lower().endswith("event") for value in types)


def _event_from_jsonld(node: Dict[str, Any], page_url: str, source_name: str) -> Optional[Event]:
    title = _plain_text(node.get("name") or node.get("headline") or "")
    start_raw = node.get("startDate") or node.get("startTime")
    end_raw = node.get("endDate") or node.get("endTime")
    start = _parse_date(start_raw)
    end = _parse_date(end_raw)
    if len(title) < 3 or not start:
        return None

    event_url = node.get("url") or node.get("mainEntityOfPage") or page_url
    if isinstance(event_url, dict):
        event_url = event_url.get("@id") or page_url

    description = _plain_text(node.get("description") or "")
    return Event(
        title=title,
        url=urljoin(page_url, str(event_url)),
        source=source_name,
        date=start,
        end_date=end,
        location=_location_text(node.get("location")) or None,
        description=description[:MAX_EXCERPT] if description else None,
        category=_category_text(node) or None,
        all_day=_is_all_day_value(start_raw) and (not end_raw or _is_all_day_value(end_raw)),
    )


def _fallback_event_from_page(soup: BeautifulSoup, page_url: str, source_name: str) -> Optional[Event]:
    heading = soup.select_one("h1")
    title = _plain_text(heading.get_text(" ", strip=True)) if heading else ""
    time_element = soup.select_one("time[datetime]")
    if not title or not time_element:
        return None
    start_raw = time_element.get("datetime")
    start = _parse_date(start_raw)
    if not start:
        return None
    all_times = soup.select("time[datetime]")
    end = _parse_date(all_times[1].get("datetime")) if len(all_times) > 1 else None
    meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
    description = _plain_text(meta.get("content", "")) if meta else ""
    return Event(
        title=title,
        url=page_url,
        source=source_name,
        date=start,
        end_date=end,
        description=description[:MAX_EXCERPT] if description else None,
        all_day=_is_all_day_value(start_raw),
    )


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = dateparser.parse(str(value), dayfirst=True)
        if parsed and parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _is_all_day_value(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def _plain_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = BeautifulSoup(unescape(str(value)), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _location_text(value: Any) -> str:
    if isinstance(value, str):
        return _plain_text(value)
    if isinstance(value, list):
        return ", ".join(part for part in (_location_text(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""
    parts = [_plain_text(value.get("name"))]
    address = value.get("address")
    if isinstance(address, str):
        parts.append(_plain_text(address))
    elif isinstance(address, dict):
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            parts.append(_plain_text(address.get(key)))
    return ", ".join(dict.fromkeys(part for part in parts if part))


def _category_text(node: Dict[str, Any]) -> str:
    for key in ("eventType", "category", "keywords"):
        value = node.get(key)
        if isinstance(value, list):
            text = ", ".join(_plain_text(item) for item in value if _plain_text(item))
        else:
            text = _plain_text(value)
        if text:
            return text[:80]
    return ""


def _dedupe_local(events: List[Event]) -> List[Event]:
    seen: Set[str] = set()
    result: List[Event] = []
    for event in events:
        key = f"{event.url}|{event.date.isoformat() if event.date else ''}|{event.title.lower()}"
        if key not in seen:
            seen.add(key)
            result.append(event)
    return result
