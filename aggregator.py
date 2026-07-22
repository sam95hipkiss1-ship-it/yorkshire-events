#!/usr/bin/env python3
"""
Yorkshire Events RSS Feed Aggregator

Fetches events from multiple Yorkshire sources, deduplicates them,
and generates a combined RSS 2.0 feed with IFY event metadata.
"""
import os
import re
import sys
from datetime import datetime
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring

from scrapers import Event
from scrapers.categories import normalise_category
from scrapers.generic_schemaorg import scrape_registered_sources
from scrapers.listing_adapters import scrape_listing_adapters
from scrapers.rss_feeds import fetch_rss_feeds
from scrapers.yorkshiregigs import scrape_yorkshiregigs
from scrapers.visitnorthyorkshire import scrape_visitnorthyorkshire
from scrapers.yorkshire_com import scrape_yorkshire_com

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
FEED_FILE = os.path.join(OUTPUT_DIR, "feed.xml")
FEED_TITLE = "Yorkshire Events - Live Events in Yorkshire, UK"
FEED_DESCRIPTION = "Comprehensive RSS feed of live events happening across Yorkshire, UK. Aggregated from multiple sources."
FEED_LINK = "https://sam95hipkiss1-ship-it.github.io/yorkshire-events/"
FEED_LANGUAGE = "en-gb"
IFY_NAMESPACE = "https://imfromyorkshire.uk.com/ns/events/1.0"


def fetch_all_events() -> List[Event]:
    print("Fetching events from all sources...")
    all_events = []

    print("\n[1/6] Web Scrapers...")
    all_events.extend(fetch_rss_feeds())

    print("\n[2/6] Source-specific listing adapters...")
    try:
        all_events.extend(scrape_listing_adapters())
    except Exception as exc:
        print(f"  Warning: listing-card collection failed safely: {exc}")

    print("\n[3/6] Registered Schema.org sources...")
    try:
        all_events.extend(scrape_registered_sources())
    except Exception as exc:
        print(f"  Warning: registered source collection failed safely: {exc}")

    print("\n[4/6] Yorkshire Gig Guide...")
    try:
        all_events.extend(scrape_yorkshiregigs())
    except Exception as exc:
        print(f"  Warning: Yorkshire Gig Guide failed: {exc}")

    print("\n[5/6] Visit North Yorkshire detail enrichment...")
    try:
        all_events.extend(scrape_visitnorthyorkshire())
    except Exception as exc:
        print(f"  Warning: Visit North Yorkshire failed: {exc}")

    print("\n[6/6] Yorkshire.com...")
    try:
        all_events.extend(scrape_yorkshire_com())
    except Exception as exc:
        print(f"  Warning: Yorkshire.com failed: {exc}")

    print(f"\nTotal events fetched: {len(all_events)}")
    return all_events


def deduplicate_events(events: List[Event]) -> List[Event]:
    seen = {}
    unique_events = []
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
        title_lower = event.title.lower().strip()
        if title_lower in category_titles or len(event.title) < 4:
            continue
        if not event.url or event.url.rstrip("/").endswith("/events"):
            continue
        if re.match(r"^[A-Z][a-z]{2}\d{2}", event.title):
            continue

        normalized_url = event.url.split("#", 1)[0].rstrip("/").lower()
        fingerprint = f"url:{normalized_url}" if normalized_url else f"event:{event.fingerprint}"

        if fingerprint in seen:
            existing = seen[fingerprint]
            for field in [
                "url", "description", "location", "date", "end_date",
                "category", "image_url", "price",
            ]:
                if not getattr(existing, field, None) and getattr(event, field, None):
                    setattr(existing, field, getattr(event, field))
            if event.all_day and not existing.date:
                existing.all_day = True
        else:
            seen[fingerprint] = event
            unique_events.append(event)

    print(f"After deduplication: {len(unique_events)} unique events")
    return unique_events


def filter_future_events(events: List[Event]) -> List[Event]:
    now = datetime.now()
    future_events = []
    for event in events:
        comparison_date = event.end_date or event.date
        if comparison_date is None or comparison_date >= now:
            future_events.append(event)
    print(f"Future and ongoing events (including undated): {len(future_events)}")
    return future_events


def sort_events(events: List[Event]) -> List[Event]:
    return sorted(events, key=lambda event: event.date or datetime.max)


def _rss_datetime(value: datetime) -> str:
    return value.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _iso_datetime(value: datetime, all_day: bool = False) -> str:
    return value.strftime("%Y-%m-%d") if all_day else value.strftime("%Y-%m-%dT%H:%M:%S")


def generate_rss_feed(events: List[Event]) -> str:
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    rss.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
    rss.set("xmlns:ify", IFY_NAMESPACE)

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = FEED_TITLE
    SubElement(channel, "link").text = FEED_LINK
    SubElement(channel, "description").text = FEED_DESCRIPTION
    SubElement(channel, "language").text = FEED_LANGUAGE
    SubElement(channel, "lastBuildDate").text = _rss_datetime(datetime.utcnow())
    SubElement(channel, "generator").text = "Yorkshire Events Aggregator"

    atom_link = SubElement(channel, "atom:link")
    atom_link.set("href", f"{FEED_LINK}feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    image = SubElement(channel, "image")
    SubElement(image, "url").text = f"{FEED_LINK}icon.png"
    SubElement(image, "title").text = FEED_TITLE
    SubElement(image, "link").text = FEED_LINK

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
        SubElement(item, "category").text = normalise_category(
            event.category,
            event.title,
            event.description,
            event.source,
        )
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


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    events = sort_events(filter_future_events(deduplicate_events(fetch_all_events())))
    print(f"\nGenerating RSS feed with {len(events)} events...")
    with open(FEED_FILE, "w", encoding="utf-8") as feed_file:
        feed_file.write(generate_rss_feed(events))
    print(f"RSS feed written to: {FEED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
