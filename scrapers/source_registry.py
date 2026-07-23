from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SourceConfig:
    name: str
    domain: str
    entry_urls: Tuple[str, ...]
    include_paths: Tuple[str, ...] = ("event", "events", "whats-on", "whatson")
    enabled: bool = False
    max_detail_pages: int = 30
    mode: str = "schemaorg"
    notes: str = ""


GENERIC_SOURCES = (
    SourceConfig("Days Out Yorkshire", "daysoutyorkshire.com", ("https://www.daysoutyorkshire.com/yorkshire-events/",), include_paths=("/yorkshire-events/", "/whats-on/"), notes="Cloudflare challenge blocks unattended GitHub requests"),
    SourceConfig("Yorkshire Attractions", "yorkshireattractions.org", ("https://yorkshireattractions.org/", "https://yorkshireattractions.org/events/"), include_paths=("/listing/", "/events/"), notes="Dynamic directory requires a dedicated endpoint adapter"),
    SourceConfig("What's On in Yorkshire", "whatsoninyorkshire.co.uk", ("https://whatsoninyorkshire.co.uk/events/",), notes="Handled by dedicated expansion source adapter"),
    SourceConfig("Go Yorkshire", "goyorkshire.com", ("https://www.goyorkshire.com/events/",), include_paths=("/events/",), notes="Collected through the RSS importer"),
    SourceConfig("Yorkshire Gig Guide", "yorkshiregigs.co.uk", ("https://www.yorkshiregigs.co.uk/",), notes="Handled by the dedicated Yorkshire Gig Guide scraper"),
    SourceConfig("Yorkshire Walks and Wellies", "yorkshirewalksandwellies.com", ("https://yorkshirewalksandwellies.com/",), include_paths=("event", "whats-on", "whatson"), max_detail_pages=20),
    SourceConfig("Visit Harrogate", "visitharrogate.co.uk", ("https://visitharrogate.co.uk/events",), notes="Handled by the Visit North Yorkshire listing adapter"),
    SourceConfig("Visit York", "visityork.org", ("https://visityork.org/whats-on", "https://visityork.org/events"), enabled=True, max_detail_pages=40),
    SourceConfig("Visit Leeds", "visitleeds.co.uk", ("https://www.visitleeds.co.uk/whats-on/all-events/",), notes="Handled by source-specific listing adapter"),
    SourceConfig("Leeds City Council", "leeds.gov.uk", ("https://www.leeds.gov.uk/events", "https://www.leeds.gov.uk/whats-on")),
    SourceConfig("Our Favourite Places", "ourfaveplaces.co.uk", ("https://www.ourfaveplaces.co.uk/whats-on/",), notes="Handled by dedicated expansion source adapter"),
    SourceConfig("Visit Bradford", "visitbradford.com", ("https://www.visitbradford.com/whats-on/bradford-events",), notes="Handled by source-specific listing adapter"),
    SourceConfig("Experience Wakefield", "experiencewakefield.co.uk", ("https://experiencewakefield.co.uk/whats-on/",), include_paths=("/event/",), notes="Handled by source-specific listing adapter"),
    SourceConfig("Visit Calderdale", "visitcalderdale.com", ("https://www.visitcalderdale.com/whats-on/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Calderdale Council", "new.calderdale.gov.uk", ("https://new.calderdale.gov.uk/events",), max_detail_pages=25),
    SourceConfig("Visit Doncaster", "visitdoncaster.com", ("https://www.visitdoncaster.com/whats-on/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Visit East Yorkshire", "visiteastyorkshire.co.uk", ("https://www.visiteastyorkshire.co.uk/whats-on/event-calendar/",), notes="Handled by dedicated regional source adapter; dynamic entries are followed to detail pages"),
    SourceConfig("Visit Hull", "visithull.org", ("https://www.visithull.org/whatson/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Hull What's On", "hullwhatson.com", ("https://hullwhatson.com/events/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Visit Barnsley", "visitbarnsley.co.uk", ("https://visitbarnsley.co.uk/whats-on",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Visit Rotherham", "visitrotherham.com", ("https://www.visitrotherham.com/whats-on/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("North York Moors National Park", "northyorkmoors.org.uk", ("https://www.northyorkmoors.org.uk/things-to-do/whats-on",), notes="robots.txt was unavailable to the GitHub runner"),
    SourceConfig("Yorkshire Dales National Park", "yorkshiredales.org.uk", ("https://www.yorkshiredales.org.uk/whats-on/",), enabled=True, max_detail_pages=35),
    SourceConfig("North Yorkshire Council", "northyorks.gov.uk", ("https://www.northyorks.gov.uk/leisure-tourism-and-culture/whats", "https://www.northyorks.gov.uk/events"), max_detail_pages=25),
    SourceConfig("Little Vikings", "little-vikings.co.uk", ("https://little-vikings.co.uk/events/",), notes="Handled by dedicated family source adapter"),
    SourceConfig("Mumbler", "mumbler.co.uk", ("https://mumbler.co.uk/",), include_paths=("events", "whats-on", "whatson"), notes="York, North Leeds, Hull and Ryedale subdomains handled by dedicated family adapters"),
    SourceConfig("Yorkshire Wildlife Park", "yorkshirewildlifepark.com", ("https://www.yorkshirewildlifepark.com/whats-on/special-events/",), notes="Handled by dedicated family source adapter"),
    SourceConfig("Stockeld Park", "stockeldpark.co.uk", ("https://stockeldpark.co.uk/activities/season/",), notes="Handled by dedicated family source adapter"),
    SourceConfig("Web Adventure Park", "webadventurepark.co.uk", ("https://www.webadventurepark.co.uk/events/",), notes="Handled by dedicated family source adapter; ticket calendar may remain external"),
    SourceConfig("Eureka!", "discover.eureka.org.uk", ("https://discover.eureka.org.uk/whats-on/",), notes="Handled by dedicated family source adapter"),
    SourceConfig("Diggerland", "diggerland.com", ("https://www.diggerland.com/events/",), notes="Yorkshire-specific outside events handled by dedicated expansion adapter"),
    SourceConfig("The Deep", "thedeep.co.uk", ("https://www.thedeep.co.uk/visit/whats-on",), notes="Handled by dedicated family source adapter"),
    SourceConfig("Lightwater Valley", "lightwatervalley.co.uk", ("https://lightwatervalley.co.uk/", "https://lightwatervalley.co.uk/calendar"), notes="Handled by dedicated family source adapter"),
    SourceConfig("York Museums Trust", "yorkmuseumstrust.org.uk", ("https://www.yorkmuseumstrust.org.uk/whats-on/events/",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("Leeds Museums and Galleries", "museumsandgalleries.leeds.gov.uk", ("https://museumsandgalleries.leeds.gov.uk/whats-on",), notes="Handled by dedicated regional source adapter"),
    SourceConfig("The Piece Hall", "thepiecehall.co.uk", ("https://www.thepiecehall.co.uk/events/",), enabled=True, max_detail_pages=35),
    SourceConfig("Yorkshire Wildlife Trust", "ywt.org.uk", ("https://www.ywt.org.uk/events",), enabled=True, max_detail_pages=35),
    SourceConfig("National Trust Yorkshire", "nationaltrust.org.uk", ("https://www.nationaltrust.org.uk/visit/yorkshire",), include_paths=("/visit/yorkshire/", "/events/"), notes="Handled by source-specific listing adapter"),
    SourceConfig("English Heritage Yorkshire", "english-heritage.org.uk", ("https://www.english-heritage.org.uk/visit/region/yorkshire/yorkshire-events/",), notes="Handled by dedicated expansion source adapter"),
    SourceConfig("RSPB Yorkshire", "rspb.org.uk", ("https://events.rspb.org.uk/", "https://www.rspb.org.uk/events"), include_paths=("event", "events"), max_detail_pages=35),
    SourceConfig("Forestry England Yorkshire", "forestryengland.uk", ("https://www.forestryengland.uk/dalby-forest/venue/events-dalby-forest",), notes="Dalby, Guisborough and Gisburn handled by dedicated expansion source adapter"),
)


CONTROLLED_SOURCES = (
    ("Yorkshire.com", "custom scraper already present"),
    ("Visit North Yorkshire", "listing adapter plus detail enrichment"),
    ("York Mumbler", "dedicated family source adapter"),
    ("North Leeds Mumbler", "dedicated family source adapter"),
    ("Hull and East Riding Mumbler", "dedicated family source adapter"),
    ("Ryedale Mumbler", "dedicated family source adapter"),
    ("Eureka! Science + Discovery", "dedicated family source adapter"),
    ("Leeds Inspired", "official API key and attribution agreement required"),
    ("Facebook Events", "Meta permission or official developer access required; direct scraping is not permitted"),
    ("WhereCanWeGo", "partner/feed permission required"),
    ("Data Thistle", "Publishing API or licensed feed required"),
    ("Day Out With The Kids", "commercial listings/affiliate permission required"),
    ("Kids Days Out", "permission or partner feed required"),
    ("Eventbrite", "partner route required"),
    ("Ticketmaster", "official Discovery API key required"),
    ("Skiddle", "official API or affiliate credentials required"),
    ("Ents24", "partner or affiliate feed required"),
    ("Fatsoma", "partner or API permission required"),
    ("Meetup", "Meetup Pro GraphQL API access required"),
    ("Chortle", "permission and a dedicated parser required"),
)
