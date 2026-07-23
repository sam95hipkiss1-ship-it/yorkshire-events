"""Enrich missing event dates from approved event detail pages.

The enrichment runs only for records whose destination URL has already passed
source/domain validation. It accepts explicit Schema.org Event dates, time
elements and recognised event-date metadata; it does not infer a date from a
page publication timestamp.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import Event
from .generic_schemaorg import _events_from_soup
from .security import validate_destination

HEADERS = {
    "User-Agent": "ImFromYorkshireEventsBot/1.5 (+https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 12)
MAX_PAGES = 100
MAX_TOTAL_SECONDS = 120
WORKERS = 8

META_START_SELECTORS = (
    "meta[itemprop='startDate']",
    "meta[property='event:start_time']",
    "meta[name='event_start']",
    "meta[name='event-start']",
    "meta[name='startDate']",
)
META_END_SELECTORS = (
    "meta[itemprop='endDate']",
    "meta[property='event:end_time']",
    "meta[name='event_end']",
    "meta[name='event-end']",
    "meta[name='endDate']",
)


@dataclass(frozen=True)
class DateResult:
    start: datetime
    end: Optional[datetime]
    all_day: bool


def enrich_missing_dates(events: Iterable[Event]) -> List[Event]:
    result = list(events)
    targets: Dict[str, List[Event]] = {}

    for event in result:
        if event.date:
            continue
        if validate_destination(str(event.url or ""), str(event.source or "")):
            continue
        url = str(event.url or "").split("#", 1)[0].strip()
        if not url:
            continue
        targets.setdefault(url, []).append(event)
        if len(targets) >= MAX_PAGES:
            break

    if not targets:
        print("Date enrichment: no missing approved dates", flush=True)
        return result

    print(f"Date enrichment: checking {len(targets)} approved detail pages", flush=True)
    started = time.monotonic()
    checked = 0
    found = 0

    with ThreadPoolExecutor(max_workers=min(WORKERS, len(targets))) as executor:
        futures = {
            executor.submit(_fetch_date, url, records): url
            for url, records in targets.items()
        }
        for future in as_completed(futures):
            if time.monotonic() - started >= MAX_TOTAL_SECONDS:
                break
            url = futures[future]
            checked += 1
            try:
                date_result = future.result()
            except Exception:
                date_result = None
            if not date_result:
                continue
            found += 1
            for event in targets[url]:
                event.date = date_result.start
                event.end_date = date_result.end
                event.all_day = date_result.all_day

    print(
        f"Date enrichment complete: {found} dates found from {checked} pages",
        flush=True,
    )
    return result


def _fetch_date(url: str, records: List[Event]) -> Optional[DateResult]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "xml" not in content_type:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(response.text, "lxml")
    source = str(records[0].source or "Yorkshire Events")
    candidates = _events_from_soup(soup, url, source)
    dated = [candidate for candidate in candidates if candidate.date]
    if dated:
        selected = _best_candidate(dated, records)
        return DateResult(
            start=selected.date,
            end=selected.end_date,
            all_day=bool(selected.all_day),
        )

    meta_result = _meta_date(soup)
    if meta_result:
        return meta_result

    time_result = _time_elements_date(soup)
    if time_result:
        return time_result

    return None


def _best_candidate(candidates: List[Event], records: List[Event]) -> Event:
    target = _normalise_title(records[0].title)
    if len(candidates) == 1 or not target:
        return candidates[0]

    def score(candidate: Event) -> float:
        candidate_title = _normalise_title(candidate.title)
        if candidate_title == target:
            return 2.0
        return SequenceMatcher(None, target, candidate_title).ratio()

    return max(candidates, key=score)


def _meta_date(soup: BeautifulSoup) -> Optional[DateResult]:
    start_raw = _first_meta_value(soup, META_START_SELECTORS)
    if not start_raw:
        return None
    start = _parse_date(start_raw)
    if not start:
        return None

    end_raw = _first_meta_value(soup, META_END_SELECTORS)
    end = _parse_date(end_raw) if end_raw else None
    if end and end < start:
        end = None
    return DateResult(start=start, end=end, all_day=_is_all_day(start_raw) and (not end_raw or _is_all_day(end_raw)))


def _time_elements_date(soup: BeautifulSoup) -> Optional[DateResult]:
    values = []
    for element in soup.select("main time[datetime], article time[datetime], [role='main'] time[datetime]"):
        raw = str(element.get("datetime") or "").strip()
        parsed = _parse_date(raw)
        if parsed and all(existing[0] != parsed for existing in values):
            values.append((parsed, raw))
        if len(values) >= 2:
            break

    if not values:
        return None
    start, start_raw = values[0]
    end = values[1][0] if len(values) > 1 and values[1][0] >= start else None
    end_raw = values[1][1] if len(values) > 1 else ""
    return DateResult(
        start=start,
        end=end,
        all_day=_is_all_day(start_raw) and (not end_raw or _is_all_day(end_raw)),
    )


def _first_meta_value(soup: BeautifulSoup, selectors) -> str:
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            value = str(element.get("content") or element.get("datetime") or "").strip()
            if value:
                return value
    return ""


def _parse_date(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = dateparser.parse(str(value), dayfirst=True)
        return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError):
        return None


def _is_all_day(value: object) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "").strip()))


def _normalise_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
