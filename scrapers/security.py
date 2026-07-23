"""Security and trust validation for aggregated Yorkshire event records."""
from __future__ import annotations

import html
import ipaddress
import re
from collections import Counter
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from . import Event
from .source_registry import GENERIC_SOURCES

MAX_TITLE = 220
MAX_DESCRIPTION = 1500
MAX_LOCATION = 240
MAX_SOURCE = 120
MAX_CATEGORY = 240
MAX_URL = 2048

APPROVED_TICKETING_DOMAINS = {
    "eventbrite.co.uk", "eventbrite.com", "ticketmaster.co.uk", "ticketmaster.com",
    "skiddle.com", "fatsoma.com", "ents24.com", "ticketsource.co.uk",
    "tickettailor.com", "seetickets.com", "universe.com", "dice.fm",
    "billetto.co.uk", "ticketsolve.com", "spektrix.com", "accessable.co.uk",
}

CUSTOM_SOURCE_DOMAINS = {
    "Whitby Events": {"whitbyevents.co.uk"},
    "What's On Yorkshire": {"whats-on-yorkshire.com"},
    "What's On in Yorkshire": {"whatsoninyorkshire.co.uk"},
    "Visit North Yorkshire": {"visitnorthyorkshire.com", "visitharrogate.co.uk"},
    "Yorkshire.com": {"yorkshire.com"},
    "York Mumbler": {"york.mumbler.co.uk", "mumbler.co.uk"},
    "North Leeds Mumbler": {"northleeds.mumbler.co.uk", "mumbler.co.uk"},
    "Hull and East Riding Mumbler": {"hullandeastriding.mumbler.co.uk", "mumbler.co.uk"},
    "Ryedale Mumbler": {"ryedale.mumbler.co.uk", "mumbler.co.uk"},
    "Eureka! Science + Discovery": {"discover.eureka.org.uk", "eureka.org.uk"},
    "National Trust Yorkshire": {"nationaltrust.org.uk"},
    "York Museums Trust": {"yorkmuseumstrust.org.uk"},
    "Leeds Museums and Galleries": {"museumsandgalleries.leeds.gov.uk"},
    "Visit Hull": {"visithull.org", "visithull.com"},
    "Hull What's On": {"hullwhatson.com"},
}

BLOCKED_CONTENT_PHRASES = {
    "pornography", "pornographic", "sex party", "swingers party", "swingers night",
    "escort service", "fetish night", "explicit sexual content", "adult sex show",
    "crypto giveaway", "wallet connect", "seed phrase", "guaranteed investment return",
    "payday loan", "malware download", "download cracked software", "phishing",
    "buy cocaine", "buy heroin", "buy firearms", "weapon sale",
}

MALICIOUS_MARKUP_PATTERNS = (
    r"<\s*script\b", r"javascript\s*:", r"data\s*:\s*text/html",
    r"onerror\s*=", r"onload\s*=", r"document\.cookie", r"eval\s*\(",
)

BROAD_LOCATIONS = {
    "york", "leeds", "sheffield", "bradford", "wakefield", "doncaster",
    "hull", "scarborough", "harrogate", "barnsley", "rotherham", "whitby",
    "calderdale", "east yorkshire", "north yorkshire", "west yorkshire",
    "south yorkshire", "yorkshire", "ryedale and thirsk", "hull and east yorkshire",
}


def _plain(value: object, limit: int) -> str:
    if value is None:
        return ""
    text = BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _source_domain_map() -> dict[str, set[str]]:
    result = {name: set(domains) for name, domains in CUSTOM_SOURCE_DOMAINS.items()}
    for source in GENERIC_SOURCES:
        result.setdefault(source.name, set()).add(source.domain.lower().removeprefix("www."))
    return result


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().removeprefix("www.")
    domain = domain.lower().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def _is_private_host(host: str) -> bool:
    value = host.lower().strip(".[]")
    if value in {"localhost", "localhost.localdomain"} or value.endswith((".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    )


def validate_destination(url: str, source: str) -> Optional[str]:
    if not url or len(url) > MAX_URL:
        return "missing_or_oversized_url"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid_url"
    if parsed.scheme.lower() != "https":
        return "non_https_url"
    if not parsed.hostname or parsed.username or parsed.password:
        return "unsafe_url_authority"
    host = parsed.hostname.lower().removeprefix("www.")
    if _is_private_host(host):
        return "private_network_destination"

    source_domains = _source_domain_map().get(source, set())
    if source_domains and any(_host_matches(host, domain) for domain in source_domains):
        return None
    if any(_host_matches(host, domain) for domain in APPROVED_TICKETING_DOMAINS):
        return None

    # Unknown sources are accepted only when their link points to a domain already
    # registered in the approved source catalogue.
    all_domains = {domain for domains in _source_domain_map().values() for domain in domains}
    if any(_host_matches(host, domain) for domain in all_domains):
        return None
    return "source_destination_mismatch"


def content_risk_reason(title: str, description: str) -> Optional[str]:
    raw = f"{title}\n{description}".lower()
    for pattern in MALICIOUS_MARKUP_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            return "malicious_markup"
    for phrase in BLOCKED_CONTENT_PHRASES:
        if phrase in raw:
            return "blocked_content_phrase"
    return None


def clean_location(location: object) -> Optional[str]:
    value = _plain(location, MAX_LOCATION)
    if not value or value.lower().strip(" ,.") in BROAD_LOCATIONS:
        return None
    return value


def validate_event(event: Event) -> Tuple[Optional[Event], List[str]]:
    reasons: List[str] = []
    title = _plain(event.title, MAX_TITLE)
    description = _plain(event.description, MAX_DESCRIPTION)
    source = _plain(event.source, MAX_SOURCE)
    category = _plain(event.category, MAX_CATEGORY)
    url = str(event.url or "").strip()[:MAX_URL]

    if len(title) < 4:
        reasons.append("invalid_title")
    destination_reason = validate_destination(url, source)
    if destination_reason:
        reasons.append(destination_reason)
    content_reason = content_risk_reason(str(event.title or ""), str(event.description or ""))
    if content_reason:
        reasons.append(content_reason)
    if event.end_date and event.date and event.end_date < event.date:
        reasons.append("reversed_date_range")

    if reasons:
        return None, reasons

    event.title = title
    event.description = description or None
    event.source = source or "Yorkshire Events"
    event.category = category or None
    event.url = url
    event.location = clean_location(event.location)
    return event, []


def filter_events(events: Iterable[Event]) -> Tuple[List[Event], dict]:
    accepted: List[Event] = []
    rejected = Counter()
    for event in events:
        clean, reasons = validate_event(event)
        if not clean:
            for reason in reasons:
                rejected[reason] += 1
            print(
                f"  Security quarantine: {getattr(event, 'source', 'Unknown')} / "
                f"{getattr(event, 'title', 'Untitled')} ({', '.join(reasons)})",
                flush=True,
            )
            continue
        accepted.append(clean)

    report = {
        "accepted": len(accepted),
        "rejected": sum(rejected.values()),
        "reasons": dict(rejected),
    }
    print(
        f"Security filter: {report['accepted']} accepted; "
        f"{report['rejected']} rejection reasons across quarantined items",
        flush=True,
    )
    return accepted, report
