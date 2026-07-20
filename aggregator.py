#!/usr/bin/env python3
"""
Yorkshire Events RSS Feed Aggregator

Fetches events from multiple Yorkshire sources, deduplicates them,
and generates a combined RSS 2.0 feed.
"""

import os
import sys
from datetime import datetime
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString
import hashlib

from scrapers import Event
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


def fetch_all_events() -> List[Event]:
    print("Fetching events from all sources...")
    all_events = []

    print("\n[1/4] RSS Feeds...")
    rss_events = fetch_rss_feeds()
    all_events.extend(rss_events)

    print("\n[2/4] Yorkshire Gig Guide...")
    try:
        gig_events = scrape_yorkshiregigs()
        all_events.extend(gig_events)
    except Exception as e:
        print(f"  Warning: Yorkshire Gig Guide failed: {e}")

    print("\n[3/4] Visit North Yorkshire...")
    try:
        visit_events = scrape_visitnorthyorkshire()
        all_events.extend(visit_events)
    except Exception as e:
        print(f"  Warning: Visit North Yorkshire failed: {e}")

    print("\n[4/4] Yorkshire.com...")
    try:
        yorkshire_events = scrape_yorkshire_com()
        all_events.extend(yorkshire_events)
    except Exception as e:
        print(f"  Warning: Yorkshire.com failed: {e}")

    print(f"\nTotal events fetched: {len(all_events)}")
    return all_events


def deduplicate_events(events: List[Event]) -> List[Event]:
    seen = {}
    unique_events = []

    CATEGORY_TITLES = {
        "food & drink events", "science & nature events", "heritage events",
        "garden events", "talks & discussions", "literature events",
        "easter events", "halloween events", "bonfire night", "christmas events",
        "kids & family events", "artisans & farmers markets", "festivals",
        "learning & workshops", "exhibitions", "country shows",
        "sport & active events", "entertainment", "live music", "comedy",
        "theatre", "film events", "dance events", "kids", "markets",
        "food and drink events", "science and nature events",
        "talks", "discussions", "view event", "view events",
        "music", "sport", "horse racing", "family", "arts & culture",
        "arts and culture", "film", "food & drink", "food and drink",
        "other", "nightlife",
    }

    for event in events:
        title_lower = event.title.lower().strip()

        if title_lower in CATEGORY_TITLES:
            continue

        if len(event.title) < 4:
            continue

        if not event.url or event.url.endswith("/events"):
            continue

        import re
        if re.match(r"^[A-Z][a-z]{2}\d{2}", event.title):
            continue

        fp = event.fingerprint

        if fp in seen:
            existing = seen[fp]
            if not existing.url and event.url:
                existing.url = event.url
            if not existing.description and event.description:
                existing.description = event.description
            if not existing.location and event.location:
                existing.location = event.location
            if not existing.date and event.date:
                existing.date = event.date
        else:
            seen[fp] = event
            unique_events.append(event)

    print(f"After deduplication: {len(unique_events)} unique events")
    return unique_events


def filter_future_events(events: List[Event]) -> List[Event]:
    now = datetime.now()
    future_events = []

    for event in events:
        if event.date is None:
            future_events.append(event)
        elif event.date >= now:
            future_events.append(event)

    print(f"Future events (including undated): {len(future_events)}")
    return future_events


def sort_events(events: List[Event]) -> List[Event]:
    def sort_key(event):
        if event.date:
            return event.date
        return datetime.max

    return sorted(events, key=sort_key)


def generate_rss_feed(events: List[Event]) -> str:
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    rss.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = FEED_TITLE
    SubElement(channel, "link").text = FEED_LINK
    SubElement(channel, "description").text = FEED_DESCRIPTION
    SubElement(channel, "language").text = FEED_LANGUAGE
    SubElement(channel, "lastBuildDate").text = datetime.utcnow().strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
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
            desc = SubElement(item, "description")
            desc.text = event.description

        if event.date:
            SubElement(item, "pubDate").text = event.date.strftime(
                "%a, %d %b %Y %H:%M:%S +0000"
            )

        if event.location:
            SubElement(item, "dc:creator").text = event.source
            location_elem = SubElement(item, "location")
            location_elem.text = event.location
        else:
            SubElement(item, "dc:creator").text = event.source

        if event.category:
            SubElement(item, "category").text = event.category

        source_elem = SubElement(item, "source")
        source_elem.text = event.source
        source_elem.set("url", event.url)

    raw_xml = tostring(rss, encoding="unicode", xml_declaration=False)
    xml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw_xml

    try:
        import re
        xml_string = re.sub(r'><', '>\n<', xml_string)

        lines = xml_string.split('\n')
        formatted = []
        indent = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('<?xml'):
                formatted.append(line)
                continue

            if line.startswith('</'):
                indent = max(0, indent - 1)

            formatted.append('  ' * indent + line)

            if (line.startswith('<') and not line.startswith('</') and
                not line.startswith('<?') and not line.endswith('/>') and
                '</' not in line):
                indent += 1

        return '\n'.join(formatted)
    except Exception:
        return xml_string


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    events = fetch_all_events()
    events = deduplicate_events(events)
    events = filter_future_events(events)
    events = sort_events(events)

    print(f"\nGenerating RSS feed with {len(events)} events...")
    rss_xml = generate_rss_feed(events)

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write(rss_xml)

    print(f"RSS feed written to: {FEED_FILE}")

    stats = {
        "total_events": len(events),
        "sources": {},
        "categories": {},
    }

    for event in events:
        stats["sources"][event.source] = stats["sources"].get(event.source, 0) + 1
        if event.category:
            stats["categories"][event.category] = stats["categories"].get(event.category, 0) + 1

    print("\n--- Statistics ---")
    print(f"Total unique events: {stats['total_events']}")
    print("\nEvents by source:")
    for source, count in sorted(stats["sources"].items()):
        print(f"  {source}: {count}")
    print("\nEvents by category:")
    for cat, count in sorted(stats["categories"].items()):
        print(f"  {cat}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
