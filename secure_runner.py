#!/usr/bin/env python3
"""Secure production runner for the Yorkshire events feed."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from aggregator import deduplicate_events, fetch_all_events, sort_events, write_outputs
from scrapers.regional_sources import scrape_regional_sources
from scrapers.security import filter_events


def filter_current_events(events):
    now = datetime.now()
    current = []
    expired = 0
    for event in events:
        if not event.date:
            current.append(event)
            continue

        if event.all_day:
            inclusive_end = (event.end_date or event.date).date()
            expiry = datetime.combine(inclusive_end + timedelta(days=1), time.min)
        else:
            expiry = event.end_date or event.date

        if expiry <= now:
            expired += 1
            continue
        current.append(event)

    print(f"Expiry filter: {len(current)} current events; {expired} expired events removed", flush=True)
    return current


def main() -> int:
    events = fetch_all_events()

    print("\n[Additional regional source adapters]", flush=True)
    try:
        events.extend(scrape_regional_sources())
    except Exception as exc:
        print(f"  Warning: regional source collection failed safely: {exc}", flush=True)

    events, security_report = filter_events(events)
    events = deduplicate_events(events)
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
