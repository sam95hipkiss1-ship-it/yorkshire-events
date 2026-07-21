import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
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
    "User-Agent": "ImFromYorkshireEventsBot/1.1 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (4, 7)
ROBOTS_TIMEOUT = (4, 5)
MAX_EXCERPT = 320
MAX_DETAIL_PAGES = 12
MAX_SOURCE_SECONDS = 28
MAX_TOTAL_SECONDS = 210
WORKERS = 4


def scrape_registered_sources() -> List[Event]:
    events: List[Event] = []
    active = [source for source in GENERIC_SOURCES if source.enabled]
    overall_started = time.monotonic()
    print(f"\n[Generic sources] {len(active)} enabled", flush=True)

    for index, source in enumerate(active, start=1):
        if time.monotonic() - overall_started >= MAX_TOTAL_SECONDS:
            print("  Generic-source runtime cap reached; remaining sources deferred.", flush=True)
            break
        started = time.monotonic()
        try:
            source_events = scrape_source(source)
            events.extend(source_events)
            print(
                f"  [{index}/{len(active)}] {source.name}: {len(source_events)} events "
                f"in {time.monotonic() - started:.1f}s",
                flush=True,
            )
        except Exception as exc:
            print(
                f"  [{index}/{len(active)}] {source.name}: failed safely ({exc})",
                flush=True,
            )
    return events


def scrape_source(source: SourceConfig) -> List[Event]:
    deadline = time.monotonic() + MAX_SOURCE_SECONDS
    robots = _load_robots(source.entry_urls[0])
    if robots is None:
        print(f"    {source.name}: robots.txt unavailable; skipped", flush=True)
        return []

    direct_events: List[Event] = []
    discovered: List[str] = []
    for entry_url in source.entry_urls[:2]:
        if time.monotonic() >= deadline:
            break
        if not robots.can_fetch(HEADERS["User-Agent"], entry_url):
            continue
        response = _get(entry_url)
        if not response:
            continue
        soup = BeautifulSoup(response.text, "lxml")
        direct_events.extend(_events_from_soup(soup, entry_url, source.name))
        discovered.extend(_discover_links(soup, entry_url, source))

    urls: List[str] = []
    seen: Set[str] = set()
    limit = min(source.max_detail_pages, MAX_DETAIL_PAGES)
    for url in discovered:
        clean = url.split("#", 1)[0]
        if clean in seen or not robots.can_fetch(HEADERS["User-Agent"], clean):
            continue
        seen.add(clean)
        urls.append(clean)
        if len(urls) >= limit:
            break

    page_events: List[Event] = []
    if urls and time.monotonic() < deadline:
        executor = ThreadPoolExecutor(max_workers=min(WORKERS, len(urls)))
        futures = [executor.submit(_fetch_page_events, url, source.name, deadline) for url in urls]
        done, pending = wait(futures, timeout=max(0.1, deadline - time.monotonic()))
        for future in done:
            try:
                page_events.extend(future.result())
            except Exception:
                pass
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    return _dedupe(direct_events + page_events)


def _fetch_page_events(url: str, source_name: str, deadline: float) -> List[Event]:
    if time.monotonic() >= deadline:
        return []
    response = _get(url)
    if not response:
        return []
    return _events_from_soup(BeautifulSoup(response.text, "lxml"), url, source_name)


def _get(url: str) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "")
        return response if "html" in content_type or "xml" in content_type else None
    except requests.RequestException:
        return None


def _load_robots(entry_url: str) -> Optional[RobotFileParser]:
    parsed = urlparse(entry_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=ROBOTS_TIMEOUT)
        if response.status_code == 404:
            parser.parse([])
            return parser
        if response.status_code >= 400:
            return None
        parser.parse(response.text.splitlines())
        return parser
    except requests.RequestException:
        return None


def _discover_links(soup: BeautifulSoup, base_url: str, source: SourceConfig) -> List[str]:
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
        fallback = _fallback_event(soup, page_url, source_name)
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
    value = node.get("@type")
    types = value if isinstance(value, list) else [value]
    return any(str(item).lower() == "event" or str(item).lower().endswith("event") for item in types)


def _event_from_jsonld(node: Dict[str, Any], page_url: str, source_name: str) -> Optional[Event]:
    title = _plain(node.get("name") or node.get("headline") or "")
    start_raw = node.get("startDate") or node.get("startTime")
    end_raw = node.get("endDate") or node.get("endTime")
    start = _parse_date(start_raw)
    end = _parse_date(end_raw)
    if len(title) < 3 or not start:
        return None
    event_url = node.get("url") or node.get("mainEntityOfPage") or page_url
    if isinstance(event_url, dict):
        event_url = event_url.get("@id") or page_url
    description = _plain(node.get("description") or "")
    return Event(
        title=title,
        url=urljoin(page_url, str(event_url)),
        source=source_name,
        date=start,
        end_date=end,
        location=_location(node.get("location")) or None,
        description=description[:MAX_EXCERPT] if description else None,
        category=_category(node) or None,
        all_day=_all_day(start_raw) and (not end_raw or _all_day(end_raw)),
    )


def _fallback_event(soup: BeautifulSoup, page_url: str, source_name: str) -> Optional[Event]:
    heading = soup.select_one("h1")
    time_element = soup.select_one("time[datetime]")
    if not heading or not time_element:
        return None
    title = _plain(heading.get_text(" ", strip=True))
    start_raw = time_element.get("datetime")
    start = _parse_date(start_raw)
    if not title or not start:
        return None
    times = soup.select("time[datetime]")
    end = _parse_date(times[1].get("datetime")) if len(times) > 1 else None
    meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
    description = _plain(meta.get("content", "")) if meta else ""
    return Event(
        title=title,
        url=page_url,
        source=source_name,
        date=start,
        end_date=end,
        description=description[:MAX_EXCERPT] if description else None,
        all_day=_all_day(start_raw),
    )


def _parse_date(value: Any):
    if value is None:
        return None
    try:
        parsed = dateparser.parse(str(value), dayfirst=True)
        return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _all_day(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def _plain(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = BeautifulSoup(unescape(str(value)), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _location(value: Any) -> str:
    if isinstance(value, str):
        return _plain(value)
    if isinstance(value, list):
        return ", ".join(part for part in (_location(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""
    parts = [_plain(value.get("name"))]
    address = value.get("address")
    if isinstance(address, str):
        parts.append(_plain(address))
    elif isinstance(address, dict):
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            parts.append(_plain(address.get(key)))
    return ", ".join(dict.fromkeys(part for part in parts if part))


def _category(node: Dict[str, Any]) -> str:
    for key in ("eventType", "category", "keywords"):
        value = node.get(key)
        if isinstance(value, list):
            text = ", ".join(_plain(item) for item in value if _plain(item))
        else:
            text = _plain(value)
        if text:
            return text[:80]
    return ""


def _dedupe(events: List[Event]) -> List[Event]:
    seen: Set[str] = set()
    result: List[Event] = []
    for event in events:
        key = f"{event.url}|{event.date.isoformat() if event.date else ''}|{event.title.lower()}"
        if key not in seen:
            seen.add(key)
            result.append(event)
    return result
