#!/usr/bin/env python3
"""Repair missing structured dates in the generated IFY Yorkshire events feed."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

FEED_FILE = Path("docs/feed.xml")
IFY_NS = "https://imfromyorkshire.uk.com/ns/events/1.0"
DC_NS = "http://purl.org/dc/elements/1.1/"
ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

ET.register_namespace("ify", IFY_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("atom", ATOM_NS)
ET.register_namespace("content", CONTENT_NS)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ImFromYorkshireEvents/1.0; +https://imfromyorkshire.uk.com/events/)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}
TARGET_DOMAINS = {"visitnorthyorkshire.com"}
MAX_WORKERS = 6

MONTHS = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
WEEKDAYS = r"Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
DATE_TOKEN = rf"(?:{WEEKDAYS})?\s*\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}(?:\s+\d{{1,2}}(?::\d{{2}})?\s*(?:AM|PM))?"
RANGE_RE = re.compile(rf"Dates?\s*:\s*({DATE_TOKEN})\s*(?:-|–|—|to)\s*({DATE_TOKEN})", re.I)
SINGLE_RE = re.compile(rf"Dates?\s*:\s*({DATE_TOKEN})", re.I)


def walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = re.sub(r"\bSept\b", "Sep", str(value), flags=re.I)
    try:
        parsed = dateparser.parse(text, dayfirst=True, fuzzy=True)
        if parsed and parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except (ValueError, TypeError, OverflowError):
        return None


def has_time(value: Any) -> bool:
    return bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\b|\b\d{1,2}:\d{2}\b", str(value or ""), re.I))


def location_from_json(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    if value.get("name"):
        parts.append(str(value["name"]).strip())
    address = value.get("address")
    if isinstance(address, str):
        parts.append(address.strip())
    elif isinstance(address, dict):
        for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode"):
            if address.get(key):
                parts.append(str(address[key]).strip())
    return ", ".join(dict.fromkeys(part for part in parts if part))


def extract_page_data(url: str) -> Optional[dict[str, Any]]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=(5, 14), allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  repair warning: {url} ({exc})", flush=True)
        return None

    soup = BeautifulSoup(response.text, "lxml")

    for script in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in walk_json(payload):
            event_type = node.get("@type")
            types = event_type if isinstance(event_type, list) else [event_type]
            if not any(value and "event" in str(value).lower() for value in types):
                continue
            start_raw = node.get("startDate") or node.get("start_date")
            end_raw = node.get("endDate") or node.get("end_date")
            start = parse_date(start_raw)
            if start:
                return {
                    "start": start,
                    "end": parse_date(end_raw),
                    "all_day": not has_time(start_raw) and (not end_raw or not has_time(end_raw)),
                    "location": location_from_json(node.get("location")),
                }

    text = " ".join(soup.stripped_strings)
    match = RANGE_RE.search(text)
    if match:
        start_raw, end_raw = match.group(1), match.group(2)
        start, end = parse_date(start_raw), parse_date(end_raw)
        if start:
            return {
                "start": start,
                "end": end,
                "all_day": not has_time(start_raw) and not has_time(end_raw),
                "location": extract_visible_location(text),
            }

    match = SINGLE_RE.search(text)
    if match:
        start_raw = match.group(1)
        start = parse_date(start_raw)
        if start:
            return {
                "start": start,
                "end": None,
                "all_day": not has_time(start_raw),
                "location": extract_visible_location(text),
            }
    return None


def extract_visible_location(text: str) -> str:
    match = re.search(r"Address\s*:\s*(.{3,250}?)(?=\s+(?:Telephone|Email|Visit Website|Social Media|Book Now)\s*:|$)", text, re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def set_text(parent: ET.Element, tag: str, value: str) -> None:
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = value


def repair_item(item: ET.Element, data: dict[str, Any]) -> None:
    start: datetime = data["start"]
    end: Optional[datetime] = data.get("end")
    all_day = bool(data.get("all_day"))

    set_text(item, "pubDate", start.strftime("%a, %d %b %Y %H:%M:%S +0000"))
    set_text(item, f"{{{IFY_NS}}}start", start.strftime("%Y-%m-%d") if all_day else start.strftime("%Y-%m-%dT%H:%M:%S"))
    if end:
        set_text(item, f"{{{IFY_NS}}}end", end.strftime("%Y-%m-%d") if all_day else end.strftime("%Y-%m-%dT%H:%M:%S"))
    set_text(item, f"{{{IFY_NS}}}allDay", "true" if all_day else "false")

    location = str(data.get("location") or "").strip()
    if location:
        set_text(item, "location", location)
        set_text(item, f"{{{IFY_NS}}}location", location)


def main() -> int:
    if not FEED_FILE.exists():
        print(f"Repair skipped: {FEED_FILE} does not exist", flush=True)
        return 0

    tree = ET.parse(FEED_FILE)
    root = tree.getroot()
    pending: list[tuple[ET.Element, str]] = []

    for item in root.findall("./channel/item"):
        if item.find(f"{{{IFY_NS}}}start") is not None:
            continue
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or item.findtext(f"{{{DC_NS}}}creator") or "").strip()
        domain = urlparse(link).netloc.lower().removeprefix("www.")
        if source == "Visit North Yorkshire" or domain in TARGET_DOMAINS:
            pending.append((item, link))

    print(f"Date repair: {len(pending)} undated Visit North Yorkshire items", flush=True)
    if not pending:
        return 0

    repaired = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(extract_page_data, url): (item, url) for item, url in pending if url}
        for future in as_completed(future_map):
            item, url = future_map[future]
            try:
                data = future.result()
            except Exception as exc:
                print(f"  repair warning: {url} ({exc})", flush=True)
                continue
            if not data:
                continue
            repair_item(item, data)
            repaired += 1
            print(f"  repaired: {item.findtext('title')} -> {data['start']}", flush=True)

    tree.write(FEED_FILE, encoding="utf-8", xml_declaration=True)
    print(f"Date repair complete: {repaired}/{len(pending)} repaired", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
