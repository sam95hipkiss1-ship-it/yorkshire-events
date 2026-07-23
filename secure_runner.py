#!/usr/bin/env python3
"""Secure production runner for the Yorkshire events feed."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from aggregator import deduplicate_events, fetch_all_events, sort_events, write_outputs
from scrapers.date_enrichment import enrich_missing_dates
from scrapers.location_enrichment import enrich_missing_locations
from scrapers.regional_sources import scrape_regional_sources
from scrapers.security import filter_events


def filter_current_events(events):
    now = datetime.now()
    current = []
    expired = 0
    undated = 0
    for event in events:
        if not event.date:
            # Public event records require a verified date. Undated listings are
            # excluded instead of being published as "TBC".
            undated += 1
            continue

        if event.all_day:
            inclusive_end = (event.end_date or event.date).date()
            expiry = datetime.combine(inclusive_end + timedelta(days=1), time.min)
        elif event.end_date and event.end_date > event.date:
            expiry = event.end_date
        else:
            # When a timed listing supplies no genuine end time, keep it for
            # the whole event date and remove it at the following midnight.
            expiry = datetime.combine(event.date.date() + timedelta(days=1), time.min)

        if expiry <= now:
            expired += 1
            continue
        current.append(event)

    print(
        f"Expiry/date filter: {len(current)} current events; "
        f"{expired} expired and {undated} undated events removed",
        flush=True,
    )
    return current


def main() -> int:
    events = fetch_all_events()

    print("\n[Additional regional source adapters]", flush=True)
    try:
        events.extend(scrape_regional_sources())
    except Exception as exc:
        print(f"  Warning: regional source collection failed safely: {exc}", flush=True)

    # Validate URLs and content before making any second-pass requests.
    events, security_report = filter_events(events)
    events = deduplicate_events(events)

    # Listing pages may omit dates or venues even though the approved event
    # detail page contains explicit structured values.
    events = enrich_missing_dates(events)
    events = enrich_missing_locations(events)

    events = filter_current_events(events)
    events = sort_events(events)

    print(f"\nGenerating secure feeds with {len(events)} events...", flush=True)
    write_outputs(events)
    print(
        "Security summary: "
        f"{security_report['accepted']} accepted; "
        f"{security_report['rejected']} rejection reasons",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
