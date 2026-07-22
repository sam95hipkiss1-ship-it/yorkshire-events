from typing import Iterable, List, Optional


CATEGORY_ORDER = (
    "Clubs",
    "Gigs",
    "Festivals",
    "Comedy",
    "Theatre & Arts",
    "Experiences",
    "Food & Drink",
    "Sport",
    "Family Days Out",
    "Seasonal",
)

CATEGORY_RULES = (
    ("Clubs", (
        "nightclub", "club night", "nightlife", "rave", "dancefloor",
        "dj set", "late night", "afterparty", "after party",
    )),
    ("Gigs", (
        "gig", "live music", "concert", "band", "singer", "orchestra",
        "acoustic", "tribute act", "music showcase", "choir", "recital",
        "festival of music", "folk music", "jazz", "rock music",
    )),
    ("Festivals", (
        "festival", "carnival", "fete", "fiesta", "country show",
        "county show", "food festival", "music festival", "fringe",
    )),
    ("Comedy", (
        "comedy", "comedian", "stand-up", "stand up", "chortle",
        "comic", "improv", "improvisation",
    )),
    ("Theatre & Arts", (
        "theatre", "theater", "play", "musical", "drama", "ballet",
        "opera", "dance", "performance", "art", "gallery", "exhibition",
        "museum", "craft", "creative workshop", "cinema", "film screening",
        "poetry", "literature", "author talk",
    )),
    ("Experiences", (
        "experience", "tour", "walk", "trail", "talk", "heritage",
        "history", "nature", "wildlife", "garden", "open day", "workshop",
        "activity", "adventure", "photography", "demonstration", "guided",
        "behind the scenes", "escape room", "day out",
    )),
    ("Food & Drink", (
        "food", "drink", "beer", "wine", "gin", "cocktail", "tasting",
        "restaurant", "supper", "brunch", "afternoon tea", "street food",
        "market", "farmers market", "artisan market", "cookery", "baking",
    )),
    ("Sport", (
        "sport", "football", "rugby", "cricket", "cycling", "cycle",
        "running", "race", "racing", "racecourse", "fitness", "yoga",
        "golf", "swim", "athletics", "tennis", "hockey", "boxing",
        "marathon", "triathlon", "parkrun",
    )),
    ("Family Days Out", (
        "family", "families", "family day", "family days out", "family day out",
        "children", "childrens", "children's", "child", "kids", "kid-friendly",
        "toddler", "baby", "under 5", "under 12", "young people", "all ages",
        "play day", "playground", "soft play", "storytime", "story time",
        "puppet", "fairy", "wizard", "dinosaur", "farm park", "zoo",
        "animal encounter", "family-friendly", "family friendly", "school holiday",
        "half term", "summer holiday", "easter holiday", "free entry day",
        "pokemon", "toy story", "children's theatre", "kids workshop",
    )),
    ("Seasonal", (
        "christmas", "xmas", "santa", "halloween", "easter", "bonfire",
        "firework", "festive", "winter", "summer of play", "spring trail",
        "autumn", "valentine", "mother's day", "mothers day", "father's day",
        "fathers day", "new year", "light trail", "illuminations",
    )),
)

DIRECT_MAP = {
    "clubs": "Clubs",
    "club": "Clubs",
    "nightlife": "Clubs",
    "music": "Gigs",
    "live music": "Gigs",
    "gigs": "Gigs",
    "concerts": "Gigs",
    "festival": "Festivals",
    "festivals": "Festivals",
    "comedy": "Comedy",
    "arts": "Theatre & Arts",
    "arts & culture": "Theatre & Arts",
    "culture": "Theatre & Arts",
    "theatre": "Theatre & Arts",
    "film": "Theatre & Arts",
    "exhibitions": "Theatre & Arts",
    "family": "Family Days Out",
    "families": "Family Days Out",
    "kids": "Family Days Out",
    "children": "Family Days Out",
    "family days": "Family Days Out",
    "family days out": "Family Days Out",
    "heritage": "Experiences",
    "history": "Experiences",
    "nature & outdoors": "Experiences",
    "community": "Experiences",
    "workshops": "Experiences",
    "experiences": "Experiences",
    "food & drink": "Food & Drink",
    "food and drink": "Food & Drink",
    "markets": "Food & Drink",
    "sport": "Sport",
    "sports": "Sport",
    "seasonal": "Seasonal",
    "christmas": "Seasonal",
    "other": "Experiences",
}


def _raw_category_values(category: Optional[str]) -> Iterable[str]:
    if not category:
        return ()
    value = str(category).replace("|", ",").replace(";", ",")
    return tuple(part.strip().lower() for part in value.split(",") if part.strip())


def normalise_categories(
    category: Optional[str],
    title: str = "",
    description: Optional[str] = None,
    source: str = "",
) -> List[str]:
    categories: List[str] = []
    raw_values = tuple(_raw_category_values(category))

    # Preserve and translate native source categories first.
    for raw in raw_values:
        mapped = DIRECT_MAP.get(raw)
        if mapped and mapped not in categories:
            categories.append(mapped)
        for native_name, mapped_name in DIRECT_MAP.items():
            if native_name in raw and mapped_name not in categories:
                categories.append(mapped_name)

    haystack = " ".join((*raw_values, title or "", description or "", source or "")).lower()
    for label, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords) and label not in categories:
            categories.append(label)

    if not categories:
        categories.append("Experiences")

    return [label for label in CATEGORY_ORDER if label in categories]


def normalise_category(
    category: Optional[str],
    title: str = "",
    description: Optional[str] = None,
    source: str = "",
) -> str:
    return normalise_categories(category, title, description, source)[0]
