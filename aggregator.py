#!/usr/bin/env python3
"""Yorkshire Events RSS feed aggregator.

Fetches Yorkshire events, normalises and deduplicates them, then publishes:
- one combined RSS feed;
- one RSS feed per active source;
- one RSS feed per IFY category;
- a JSON manifest containing source health and category coverage.
"""
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List
from xml.etree.ElementTree import Element, SubElement, tostring

from scrapers import Event
from scrapers.categories import CATEGORY_ORDER, normalise_categories
from scrapers.family_sources import scrape_family_sources
from scrapers.generic_schemaorg import scrape_registered_sources
from scrapers.listing_adapters import scrape_listing_adapters
from scrapers.rss_feeds import fetch_rss_feeds
from scrapers.source_registry import CONTROLLED_SOURCES, GENERIC_SOURCES
from scrapers.visitnorthyorkshire import scrape_visitnorthyorkshire
from scrapers.yorkshire_com import scrape_yorkshire_com
from scrapers.yorkshiregigs import scrape_yorkshiregigs

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(ROOT_DIR, "docs")
FEED_FILE = os.path.join(OUTPUT_DIR, "feed.xml")
SOURCE_FEEDS_DIR = os.path.join(OUTPUT_DIR, "feeds")
CATEGORY_FEEDS_DIR = os.path.join(OUTPUT_DIR, "categories")
SOURCES_MANIFEST_FILE = os.path.join(OUTPUT_DIR, "sources.json")
CATEGORIES_MANIFEST_FILE = os.path.join(OUTPUT_DIR, "categories.json")

FEED_TITLE = "Yorkshire Events - Live Events in Yorkshire, UK"
FEED_DESCRIPTION = "Live Yorkshire events aggregated from approved sources."
FEED_LINK = "https://sam95hipkiss1-ship-it.github.io/yorkshire-events/"
FEED_LANGUAGE = "en-gb"
IFY_NAMESPACE = "https://imfromyorkshire.uk.com/ns/events/1.0"


def fetch_all_events() -> List[Event]:
    print("Fetching events from all sources...")
    all_events: List[Event] = []

    print("\n[1/7] RSS feeds...")
    all_events.extend(fetch_rss_feeds())

    print("\n[2/7] Source-specific listing adapters...")
    try:
        all_events.extend(scrape_listing_adapters())
    except Exception as exc:
        print(f"  Warning: listing-card collection failed safely: {exc}")

    print("\n[3/7] Family days out source adapters...")
    try:
        all_events.extend(scrape_family_sources())
    except Exception as exc:
        print(f"  Warning: family-source collection failed safely: {exc}")

    print("\n[4/7] Registered Schema.org sources...")
    try:
        all_events.extend(scrape_registered_sources())
    except Exception as exc:
        print(f"  Warning: registered source collection failed safely: {exc}")

    print("\n[5/7] Yorkshire Gig Guide...")
    try:
        all_events.extend(scrape_yorkshiregigs())
    except Exception as exc:
        print(f"  Warning: Yorkshire Gig Guide failed: {exc}")

    print("\n[6/7] Visit North Yorkshire detail enrichment...")
    try:
        all_events.extend(scrape_visitnorthyorkshire())
    except Exception as exc:
        print(f"  Warning: Visit North Yorkshire failed: {exc}")

    print("\n[7/7] Yorkshire.com...")
    try:
        all_events.extend(scrape_yorkshire_com())
    except Exception as exc:
        print(f"  Warning: Yorkshire.com failed: {exc}")

    print(f"\nTotal events fetched: {len(all_events)}")
    return all_events


def deduplicate_events(events: Iterable[Event]) -> List[Event]:
    seen: Dict[str, Event] = {}
    unique_events: List[Event] = []
    category_titles = {
        "food & drink events", "science & nature events", "heritage events",
        "garden events", "talks & discussions", "literature events",
        "easter events", "halloween events", "bonfire night", "christmas events",
        "kids & family events", "artisans & farmers markets", "festivals",
        "learning & workshops", "exhibitions", "country shows",
        "sport & active events", "entertainment", "live music", "comedy",
        "theatre", "film events", "dance events", "kids", "markets",
        "food and drink events", "science and nature events", "talks",
        "discussions", "view event", "view events", "music", "sport",
        "horse racing", "family", "arts & culture", "arts and culture",
        "film", "food & drink", "food and drink", "other", "nightlife",
    }

    for event in events:
        title_lower = (event.title or "").lower().strip()
        if title_lower in category_titles or len(event.title or "") < 4:
            continue
        if not event.url or event.url.rstrip("/").endswith("/events"):
            continue
        if re.match(r"^[A-Z][a-z]{2}\d{2}", event.title):
            continue

        normalized_url = event.url.split("#", 1)[0].rstrip("/").lower()
        fingerprint = f"url:{normalized_url}" if normalized_url else f"event:{event.fingerprint}"

        if fingerprint in seen:
            existing = seen[fingerprint]
            for field in (
                "url", "description", "location", "date", "end_date",
                "category", "image_url", "price",
            ):
                if not getattr(existing, field, None) and getattr(event, field, None):
                    setattr(existing, field, getattr(event, field))
            if event.all_day and not existing.date:
                existing.all_day = True
        else:
            seen[fingerprint] = event
            unique_events.append(event)

    print(f"After deduplication: {len(unique_events)} unique events")
    return unique_events


def filter_future_events(events: Iterable[Event]) -> List[Event]:
    now = datetime.now()
    result = []
    for event in events:
        comparison_date = event.end_date or event.date
        if comparison_date is None or comparison_date >= now:
            result.append(event)
    print(f"Future and ongoing events (including undated): {len(result)}")
    return result


def sort_events(events: Iterable[Event]) -> List[Event]:
    return sorted(events, key=lambda event: event.date or datetime.max)


def slugify(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "source"


def _rss_datetime(value: datetime) -> str:
    return value.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _iso_datetime(value: datetime, all_day: bool = False) -> str:
    return value.strftime("%Y-%m-%d") if all_day else value.strftime("%Y-%m-%dT%H:%M:%S")


def event_categories(event: Event) -> List[str]:
    return normalise_categories(
        event.category,
        event.title,
        event.description,
        event.source,
    )


def generate_rss_feed(
    events: Iterable[Event],
    title: str = FEED_TITLE,
    description: str = FEED_DESCRIPTION,
    link: str = FEED_LINK,
) -> str:
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    rss.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
    rss.set("xmlns:ify", IFY_NAMESPACE)

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description
    SubElement(channel, "language").text = FEED_LANGUAGE
    SubElement(channel, "lastBuildDate").text = _rss_datetime(datetime.utcnow())
    SubElement(channel, "generator").text = "I’m From Yorkshire Events Aggregator"

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", link)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for event in events:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = event.title
        SubElement(item, "link").text = event.url
        SubElement(item, "guid").text = event.url
        if event.description:
            SubElement(item, "description").text = event.description
        if event.date:
            SubElement(item, "pubDate").text = _rss_datetime(event.date)
            SubElement(item, "ify:start").text = _iso_datetime(event.date, event.all_day)
        if event.end_date:
            SubElement(item, "ify:end").text = _iso_datetime(event.end_date, event.all_day)
        if event.date:
            SubElement(item, "ify:allDay").text = "true" if event.all_day else "false"
        if event.location:
            SubElement(item, "location").text = event.location
            SubElement(item, "ify:location").text = event.location
        for category in event_categories(event):
            SubElement(item, "category").text = category
        if event.image_url:
            SubElement(item, "ify:image").text = event.image_url
        if event.price:
            SubElement(item, "ify:price").text = event.price
        SubElement(item, "dc:creator").text = event.source
        source_elem = SubElement(item, "source")
        source_elem.text = event.source
        source_elem.set("url", event.url)

    raw_xml = tostring(rss, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + re.sub(r"><", ">\n<", raw_xml)


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as output:
        output.write(content)


def _clear_xml_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    for filename in os.listdir(path):
        if filename.endswith(".xml"):
            os.remove(os.path.join(path, filename))


def _status_from_notes(notes: str, enabled: bool = False) -> str:
    value = (notes or "").lower()
    if any(token in value for token in ("api", "partner", "permission", "credentials", "licensed")):
        return "requires_access"
    if any(token in value for token in ("challenge", "blocked", "robots.txt")):
        return "blocked"
    if any(token in value for token in ("dedicated adapter required", "dynamically")):
        return "not_implemented"
    if "handled" in value or "collected" in value or enabled:
        return "configured"
    return "registered"


def build_registered_source_status(active_counts: Counter) -> List[dict]:
    registered: Dict[str, dict] = {}

    for source in GENERIC_SOURCES:
        registered[source.name] = {
            "name": source.name,
            "domain": source.domain,
            "status": _status_from_notes(source.notes, source.enabled),
            "notes": source.notes,
        }

    for name, notes in CONTROLLED_SOURCES:
        registered.setdefault(name, {
            "name": name,
            "domain": "",
            "status": _status_from_notes(notes),
            "notes": notes,
        })

    for source_name, count in active_counts.items():
        record = registered.setdefault(source_name, {
            "name": source_name,
            "domain": "",
            "notes": "Active event source",
        })
        record["status"] = "active"
        record["item_count"] = count
        record["slug"] = slugify(source_name)
        record["feed_url"] = f"{FEED_LINK}feeds/{record['slug']}.xml"

    for record in registered.values():
        record.setdefault("item_count", 0)
        record.setdefault("slug", slugify(record["name"]))
        record.setdefault("feed_url", "")
        if record["item_count"] == 0 and record["status"] == "configured":
            record["status"] = "empty"

    return sorted(registered.values(), key=lambda item: item["name"].lower())


def write_outputs(events: List[Event]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    _clear_xml_directory(SOURCE_FEEDS_DIR)
    _clear_xml_directory(CATEGORY_FEEDS_DIR)

    _write_text(
        FEED_FILE,
        generate_rss_feed(events, link=f"{FEED_LINK}feed.xml"),
    )

    by_source: Dict[str, List[Event]] = defaultdict(list)
    by_category: Dict[str, List[Event]] = {category: [] for category in CATEGORY_ORDER}
    for event in events:
        by_source[event.source or "Yorkshire Events"].append(event)
        for category in event_categories(event):
            by_category.setdefault(category, []).append(event)

    active_feeds = []
    active_counts = Counter()
    for source_name, source_events in sorted(by_source.items()):
        source_events = sort_events(source_events)
        slug = slugify(source_name)
        feed_url = f"{FEED_LINK}feeds/{slug}.xml"
        _write_text(
            os.path.join(SOURCE_FEEDS_DIR, f"{slug}.xml"),
            generate_rss_feed(
                source_events,
                title=f"{source_name} Yorkshire Events",
                description=f"Upcoming Yorkshire events from {source_name}.",
                link=feed_url,
            ),
        )
        active_counts[source_name] = len(source_events)
        category_counts = Counter(
            category
            for event in source_events
            for category in event_categories(event)
        )
        active_feeds.append({
            "name": source_name,
            "slug": slug,
            "feed_url": feed_url,
            "item_count": len(source_events),
            "category_counts": dict(category_counts),
            "status": "active",
        })

    category_manifest = []
    for category in CATEGORY_ORDER:
        category_events = sort_events(by_category.get(category, []))
        slug = slugify(category)
        feed_url = f"{FEED_LINK}categories/{slug}.xml"
        _write_text(
            os.path.join(CATEGORY_FEEDS_DIR, f"{slug}.xml"),
            generate_rss_feed(
                category_events,
                title=f"Yorkshire {category} Events",
                description=f"Upcoming Yorkshire events in the {category} category.",
                link=feed_url,
            ),
        )
        category_manifest.append({
            "name": category,
            "slug": slug,
            "feed_url": feed_url,
            "item_count": len(category_events),
        })

    source_status = build_registered_source_status(active_counts)
    manifest = {
        "version": 2,
        "generated_at": generated_at,
        "master_feed": f"{FEED_LINK}feed.xml",
        "active_source_count": len(active_feeds),
        "registered_source_count": len(source_status),
        "event_count": len(events),
        "active_feeds": active_feeds,
        "sources": source_status,
        "categories": category_manifest,
    }
    _write_text(SOURCES_MANIFEST_FILE, json.dumps(manifest, ensure_ascii=False, indent=2))
    _write_text(CATEGORIES_MANIFEST_FILE, json.dumps({
        "generated_at": generated_at,
        "categories": category_manifest,
    }, ensure_ascii=False, indent=2))

    print(f"Published {len(active_feeds)} source feeds")
    for category in category_manifest:
        print(f"  Category {category['name']}: {category['item_count']} events")


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    events = sort_events(filter_future_events(deduplicate_events(fetch_all_events())))
    print(f"\nGenerating feeds with {len(events)} events...")
    write_outputs(events)
    print(f"Master RSS feed written to: {FEED_FILE}")
    print(f"Source manifest written to: {SOURCES_MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
