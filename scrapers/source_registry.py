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
    SourceConfig("Days Out Yorkshire", "daysoutyorkshire.com", ("https://www.daysoutyorkshire.com/yorkshire-events/",), include_paths=("/yorkshire-events/", "/whats-on/"), enabled=True, max_detail_pages=40),
    SourceConfig("Yorkshire Attractions", "yorkshireattractions.org", ("https://yorkshireattractions.org/", "https://yorkshireattractions.org/events/"), include_paths=("/listing/", "/events/")),
    SourceConfig("What's On in Yorkshire", "whatsoninyorkshire.co.uk", ("https://www.whatsoninyorkshire.co.uk/",)),
    SourceConfig("Go Yorkshire", "goyorkshire.com", ("https://www.goyorkshire.com/events/",), include_paths=("/events/",), enabled=True, max_detail_pages=40),
    SourceConfig("Yorkshire Walks and Wellies", "yorkshirewalksandwellies.com", ("https://yorkshirewalksandwellies.com/",), include_paths=("event", "whats-on", "whatson"), max_detail_pages=20),
    SourceConfig("Visit Harrogate", "visitharrogate.co.uk", ("https://www.visitharrogate.co.uk/events/", "https://www.visitharrogate.co.uk/whats-on/"), enabled=True, max_detail_pages=40),
    SourceConfig("Visit York", "visityork.org", ("https://visityork.org/whats-on", "https://visityork.org/events"), enabled=True, max_detail_pages=40),
    SourceConfig("Visit Leeds", "visitleeds.co.uk", ("https://www.visitleeds.co.uk/whats-on/",), enabled=True, max_detail_pages=40),
    SourceConfig("Leeds City Council", "leeds.gov.uk", ("https://www.leeds.gov.uk/events", "https://www.leeds.gov.uk/whats-on")),
    SourceConfig("Welcome to Sheffield", "welcometosheffield.co.uk", ("https://www.welcometosheffield.co.uk/content/events/", "https://www.welcometosheffield.co.uk/visit/whats-on/"), enabled=True, max_detail_pages=40),
    SourceConfig("Our Favourite Places", "ourfaveplaces.co.uk", ("https://www.ourfaveplaces.co.uk/whats-on/", "https://www.ourfaveplaces.co.uk/events/")),
    SourceConfig("Visit Bradford", "visitbradford.com", ("https://www.visitbradford.com/whats-on/",), enabled=True, max_detail_pages=40),
    SourceConfig("Experience Wakefield", "experiencewakefield.co.uk", ("https://experiencewakefield.co.uk/events/", "https://experiencewakefield.co.uk/whats-on/"), enabled=True, max_detail_pages=40),
    SourceConfig("Visit Calderdale", "visitcalderdale.com", ("https://www.visitcalderdale.com/whats-on/",), max_detail_pages=40),
    SourceConfig("Calderdale Council", "new.calderdale.gov.uk", ("https://new.calderdale.gov.uk/events",), max_detail_pages=25),
    SourceConfig("Visit Doncaster", "visitdoncaster.com", ("https://www.visitdoncaster.com/whats-on/", "https://www.visitdoncaster.com/events/"), max_detail_pages=40),
    SourceConfig("Visit East Yorkshire", "visiteastyorkshire.co.uk", ("https://www.visiteastyorkshire.co.uk/whats-on/event-calendar/",), enabled=True, max_detail_pages=50),
    SourceConfig("Visit Hull", "visithull.org", ("https://www.visithull.org/whatson/", "https://www.visithull.org/events/"), enabled=True, max_detail_pages=40),
    SourceConfig("Hull What's On", "hullwhatson.com", ("https://hullwhatson.com/events/",), max_detail_pages=40),
    SourceConfig("Visit Barnsley", "visitbarnsley.co.uk", ("https://visitbarnsley.co.uk/whats-on/", "https://visitbarnsley.co.uk/events/"), max_detail_pages=35),
    SourceConfig("Visit Rotherham", "visitrotherham.com", ("https://www.visitrotherham.com/whats-on/", "https://www.visitrotherham.com/events/"), max_detail_pages=35),
    SourceConfig("North York Moors National Park", "northyorkmoors.org.uk", ("https://www.northyorkmoors.org.uk/things-to-do/whats-on",), enabled=True, max_detail_pages=35),
    SourceConfig("Yorkshire Dales National Park", "yorkshiredales.org.uk", ("https://www.yorkshiredales.org.uk/whats-on/",), enabled=True, max_detail_pages=35),
    SourceConfig("North Yorkshire Council", "northyorks.gov.uk", ("https://www.northyorks.gov.uk/leisure-tourism-and-culture/whats", "https://www.northyorks.gov.uk/events"), max_detail_pages=25),
    SourceConfig("Little Vikings", "little-vikings.co.uk", ("https://little-vikings.co.uk/whats-on-in-york-for-kids/",), max_detail_pages=30),
    SourceConfig("Mumbler", "mumbler.co.uk", ("https://mumbler.co.uk/",), include_paths=("events", "whats-on", "whatson"), max_detail_pages=25),
    SourceConfig("Yorkshire Wildlife Park", "yorkshirewildlifepark.com", ("https://www.yorkshirewildlifepark.com/events/",), enabled=True, max_detail_pages=30),
    SourceConfig("Stockeld Park", "stockeldpark.co.uk", ("https://stockeldpark.co.uk/events/", "https://stockeldpark.co.uk/whats-on/"), max_detail_pages=25),
    SourceConfig("Web Adventure Park", "webadventurepark.co.uk", ("https://webadventurepark.co.uk/events/", "https://webadventurepark.co.uk/whats-on/"), max_detail_pages=20),
    SourceConfig("Eureka!", "discover.eureka.org.uk", ("https://discover.eureka.org.uk/whats-on/", "https://discover.eureka.org.uk/events/"), max_detail_pages=25),
    SourceConfig("Diggerland", "diggerland.com", ("https://www.diggerland.com/events/", "https://www.diggerland.com/whats-on/"), max_detail_pages=20),
    SourceConfig("The Deep", "thedeep.co.uk", ("https://www.thedeep.co.uk/events", "https://www.thedeep.co.uk/plan-your-visit/whats-on"), max_detail_pages=25),
    SourceConfig("Lightwater Valley", "lightwatervalley.co.uk", ("https://lightwatervalley.co.uk/events/", "https://lightwatervalley.co.uk/whats-on/"), max_detail_pages=25),
    SourceConfig("York Museums Trust", "yorkmuseumstrust.org.uk", ("https://www.yorkmuseumstrust.org.uk/whats-on/",), enabled=True, max_detail_pages=35),
    SourceConfig("Leeds Museums and Galleries", "museumsandgalleries.leeds.gov.uk", ("https://museumsandgalleries.leeds.gov.uk/events/",), max_detail_pages=35),
    SourceConfig("The Piece Hall", "thepiecehall.co.uk", ("https://www.thepiecehall.co.uk/events/",), enabled=True, max_detail_pages=35),
    SourceConfig("Yorkshire Wildlife Trust", "ywt.org.uk", ("https://www.ywt.org.uk/events",), enabled=True, max_detail_pages=35),
    SourceConfig("National Trust Yorkshire", "nationaltrust.org.uk", ("https://www.nationaltrust.org.uk/visit/yorkshire/events",), include_paths=("/visit/", "/events/"), max_detail_pages=40),
    SourceConfig("English Heritage Yorkshire", "english-heritage.org.uk", ("https://www.english-heritage.org.uk/visit/whats-on/",), include_paths=("/visit/whats-on/",), max_detail_pages=40),
    SourceConfig("RSPB Yorkshire", "rspb.org.uk", ("https://events.rspb.org.uk/", "https://www.rspb.org.uk/events"), include_paths=("event", "events"), max_detail_pages=35),
    SourceConfig("Forestry England Yorkshire", "forestryengland.uk", ("https://www.forestryengland.uk/events",), include_paths=("/events/",), max_detail_pages=35),
)


CONTROLLED_SOURCES = (
    ("Yorkshire.com", "custom scraper already present"),
    ("Visit North Yorkshire", "custom detail-page scraper already present"),
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
