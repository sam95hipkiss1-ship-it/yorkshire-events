import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser

from . import Event


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = (5, 15)
MAX_DESCRIPTION = 320

MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)
WEEKDAYS = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?"
DATE_TOKEN = (
    rf"(?:{WEEKDAYS}\s+)?"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:\s+\d{{2,4}})?"
)
DATE_RANGE_RE = re.compile(
    rf"(?P<start>Now|{DATE_TOKEN})\s*(?:-|–|—|to)\s*(?P<end>{DATE_TOKEN})",
    re.IGNORECASE,
)
SINGLE_DATE_RE = re.compile(DATE_TOKEN, re.IGNORECASE)
TIME_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2})\s*(?:-|–|—|to)\s*(?P<end>\d{1,2}:\d{2})",
    re.IGNORECASE,
)


ADAPTERS: Sequence[Dict[str, object]] = (
    {
        "name": "Visit Leeds",
        "urls": (
            "https://www.visitleeds.co.uk/whats-on/all-events/",
            "https://www.visitleeds.co.uk/whats-on/all-events/?sf_paged=2",
            "https://www.visitleeds.co.uk/whats-on/all-events/?sf_paged=3",
            "https://www.visitleeds.co.uk/whats-on/all-events/?sf_paged=4",
        ),
        "href_contains": ("/whats-on/all-events/",),
        "href_excludes": ("?sf_paged=",),
        "anchor_text": ("more info",),
    },
    {
        "name": "Welcome to Sheffield",
        "urls": (
            "https://www.welcometosheffield.co.uk/visit/whats-on/all-events/",
            "https://www.welcometosheffield.co.uk/visit/whats-on/all-events/?page=1",
            "https://www.welcometosheffield.co.uk/visit/whats-on/all-events/?page=2",
            "https://www.welcometosheffield.co.uk/visit/whats-on/all-events/?page=3",
        ),
        "href_contains": ("/content/events/",),
        "href_excludes": (),
        "anchor_text": (),
    },
    {
        "name": "Visit Bradford",
        "urls": (
            "https://www.visitbradford.com/whats-on/bradford-events",
            "https://www.visitbradford.com/whats-on/bradford-events?p=2",
            "https://www.visitbradford.com/whats-on/bradford-events?p=3",
        ),
        "href_contains": ("/whats-on/",),
        "href_excludes": ("/bradford-events",),
        "href_regex": r"-p\d+$",
        "anchor_text": (),
    },
    {
        "name": "Experience Wakefield",
        "urls": ("https://experiencewakefield.co.uk/whats-on/",),
        "href_contains": ("/event/",),
        "href_excludes": ("/event-applications",),
        "anchor_text": (),
    },
    {
        "name": "Visit North Yorkshire",
        "urls": ("https://visitharrogate.co.uk/events",),
        "href_contains": ("visitnorthyorkshire.com/events/",),
        "href_excludes": (),
        "anchor_text": (),
        "allow_external": True,
    },
    {
        "name": "National Trust Yorkshire",
        "urls": ("https://www.nationaltrust.org.uk/visit/yorkshire",),
        "href_contains": ("/visit/yorkshire/", "/events/"),
        "href_excludes": (),
        "anchor_text": (),
    },
)


def scrape_listing_adapters() -> List[Event]:
    all_events: List[Event] = []
    print("\n[Listing-card adapters]")

    session = requests.Session()
    session.headers.update(HEADERS)

    for adapter in ADAPTERS:
        name = str(adapter["name"])
        source_events: List[Event] = []

        for page_url in adapter["urls"]:
            try:
                response = session.get(str(page_url), timeout=TIMEOUT, allow_redirects=True)
                response.raise_for_status()
            except requests.RequestException as exc:
                print(f"  {name}: page failed safely ({exc})")
                continue

            soup = BeautifulSoup(response.text, "lxml")
            source_events.extend(_parse_listing_page(soup, str(page_url), adapter))

        source_events = _dedupe(source_events)
        print(f"  {name}: {len(source_events)} events")
        all_events.extend(source_events)

    return _dedupe(all_events)


def _parse_listing_page(
    soup: BeautifulSoup,
    page_url: str,
    adapter: Dict[str, object],
) -> List[Event]:
    events: List[Event] = []

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not _matches_anchor(anchor, href, page_url, adapter):
            continue

        container = _find_event_container(anchor)
        if container is None:
            continue

        event = _event_from_container(anchor, container, page_url, str(adapter["name"]))
        if event:
            events.append(event)

    return events


def _matches_anchor(
    anchor: Tag,
    href: str,
    page_url: str,
    adapter: Dict[str, object],
) -> bool:
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False

    absolute = urljoin(page_url, href)
    parsed = urlparse(absolute)

    if not adapter.get("allow_external"):
        source_domain = urlparse(page_url).netloc.lower().lstrip("www.")
        link_domain = parsed.netloc.lower().lstrip("www.")
        if source_domain != link_domain:
            return False

    href_lower = absolute.lower()
    if any(token.lower() not in href_lower for token in adapter.get("href_contains", ())):
        return False
    if any(token.lower() in href_lower for token in adapter.get("href_excludes", ())):
        return False

    href_regex = adapter.get("href_regex")
    if href_regex and not re.search(str(href_regex), parsed.path, re.IGNORECASE):
        return False

    allowed_text = tuple(str(value).lower() for value in adapter.get("anchor_text", ()))
    if allowed_text:
        text = _clean_text(anchor.get_text(" ", strip=True)).lower()
        if text not in allowed_text:
            return False

    return True


def _find_event_container(anchor: Tag) -> Optional[Tag]:
    node: Optional[Tag] = anchor
    best: Optional[Tag] = None

    for _ in range(10):
        node = node.parent if isinstance(node, Tag) else None
        if node is None or node.name in {"body", "html"}:
            break

        text = _clean_text(node.get_text(" ", strip=True))
        if len(text) > 6000:
            break

        if _contains_date(text):
            best = node
            if len(text) <= 2200:
                return node

    return best


def _event_from_container(
    anchor: Tag,
    container: Tag,
    page_url: str,
    source_name: str,
) -> Optional[Event]:
    text = _clean_text(container.get_text(" ", strip=True))
    start, end, all_day = _parse_date_range(text)
    if not start:
        return None

    title = _title_from_container(anchor, container)
    if len(title) < 3 or title.lower() in {"more info", "read more", "book now", "see all events"}:
        return None

    event_url = urljoin(page_url, anchor.get("href", ""))
    location = _location_from_container(container)
    description = _description_from_container(container, title)

    return Event(
        title=title,
        url=event_url,
        source=source_name,
        date=start,
        end_date=end,
        location=location,
        description=description,
        all_day=all_day,
    )


def _title_from_container(anchor: Tag, container: Tag) -> str:
    anchor_text = _clean_text(anchor.get_text(" ", strip=True))
    if anchor_text and anchor_text.lower() not in {"more info", "read more", "book now", "see all events"}:
        return anchor_text[:220]

    for heading in container.select("h1, h2, h3, h4, h5"):
        text = _clean_text(heading.get_text(" ", strip=True))
        if text:
            return text[:220]

    for candidate in container.select("a[href]"):
        text = _clean_text(candidate.get_text(" ", strip=True))
        if text and text.lower() not in {"more info", "read more", "book now", "see all events"}:
            return text[:220]

    return ""


def _location_from_container(container: Tag) -> Optional[str]:
    for selector in (
        "address",
        "[class*='location']",
        "[class*='venue']",
        "[class*='place']",
    ):
        element = container.select_one(selector)
        if element:
            text = _clean_text(element.get_text(" ", strip=True))
            if 2 < len(text) <= 240:
                return text

    for element in container.select("p, span, div"):
        text = _clean_text(element.get_text(" ", strip=True))
        if 5 < len(text) <= 180 and re.search(
            r"\b(?:North|South|East|West) Yorkshire\b|\bYorkshire\b",
            text,
            re.IGNORECASE,
        ):
            return text

    return None


def _description_from_container(container: Tag, title: str) -> Optional[str]:
    for paragraph in container.select("p"):
        text = _clean_text(paragraph.get_text(" ", strip=True))
        if text and text != title and not _contains_date(text) and len(text) >= 30:
            return text[:MAX_DESCRIPTION]
    return None


def _contains_date(text: str) -> bool:
    return bool(DATE_RANGE_RE.search(text) or SINGLE_DATE_RE.search(text))


def _parse_date_range(text: str) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    normalized = _clean_text(text).replace("Sept", "Sep")
    match = DATE_RANGE_RE.search(normalized)

    if match:
        start_raw = match.group("start")
        end_raw = match.group("end")
        end = _parse_date_token(end_raw)
        if not end:
            return None, None, False

        if start_raw.lower() == "now":
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start = _parse_date_token(start_raw, fallback_year=end.year)

        if not start:
            return None, None, False

        time_match = TIME_RANGE_RE.search(normalized)
        all_day = time_match is None
        if time_match:
            start = _apply_time(start, time_match.group("start"))
            end = _apply_time(end, time_match.group("end"))

        if end < start:
            end = end.replace(year=end.year + 1)

        return start, end, all_day

    single = SINGLE_DATE_RE.search(normalized)
    if not single:
        return None, None, False

    start = _parse_date_token(single.group(0))
    if not start:
        return None, None, False

    time_match = TIME_RANGE_RE.search(normalized)
    if time_match:
        return (
            _apply_time(start, time_match.group("start")),
            _apply_time(start, time_match.group("end")),
            False,
        )

    return start, start, True


def _parse_date_token(value: str, fallback_year: Optional[int] = None) -> Optional[datetime]:
    cleaned = re.sub(
        r"\b(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)(?:day)?\b",
        "",
        value,
        flags=re.I,
    )
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", cleaned, flags=re.I)
    cleaned = _clean_text(cleaned)

    has_year = bool(re.search(rf"(?:{MONTHS})\s+\d{{2,4}}\b", cleaned, flags=re.I))
    if fallback_year and not has_year:
        cleaned = f"{cleaned} {fallback_year}"

    try:
        parsed = dateparser.parse(cleaned, dayfirst=True, fuzzy=False)
    except (ValueError, TypeError, OverflowError):
        return None

    if parsed and parsed.tzinfo:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _apply_time(value: datetime, raw_time: str) -> datetime:
    hours, minutes = [int(part) for part in raw_time.split(":", 1)]
    return value.replace(hour=hours, minute=minutes, second=0, microsecond=0)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _dedupe(events: Iterable[Event]) -> List[Event]:
    seen = set()
    result: List[Event] = []

    for event in events:
        key = (
            event.url.rstrip("/").lower(),
            event.date.isoformat() if event.date else "",
            event.title.lower().strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(event)

    return result
