from typing import Optional


CATEGORY_RULES = (
    ("Seasonal", ("christmas", "xmas", "santa", "halloween", "easter", "bonfire", "firework", "festive", "winter", "summer of play", "summer holiday", "school holiday", "half term", "spring trail", "autumn")),
    ("Comedy", ("comedy", "comedian", "stand-up", "stand up", "chortle")),
    ("Festivals", ("festival", "carnival", "fete", "fiesta")),
    ("Clubs", ("nightclub", "club night", "nightlife", "rave", "dancefloor", "dj set", "late night")),
    ("Gigs", ("gig", "live music", "concert", "band", "singer", "orchestra", "acoustic", "tribute act", "music showcase")),
    ("Theatre & Arts", ("theatre", "theater", "play", "musical", "drama", "ballet", "opera", "dance", "performance", "art", "gallery", "exhibition", "museum", "craft", "creative workshop")),
    ("Food & Drink", ("food", "drink", "beer", "wine", "gin", "cocktail", "tasting", "restaurant", "supper", "brunch", "afternoon tea", "street food")),
    ("Sport", ("sport", "football", "rugby", "cricket", "cycling", "cycle", "running", "race", "racing", "racecourse", "fitness", "yoga", "golf", "swim", "athletics")),
    ("Family Days", ("family", "children", "childrens", "children's", "kids", "toddler", "play day", "free entry day", "family-friendly", "family friendly", "pokemon", "toy story")),
    ("Experiences", ("experience", "tour", "walk", "trail", "talk", "heritage", "history", "nature", "wildlife", "garden", "open day", "workshop", "activity", "adventure", "photography")),
)

DIRECT_MAP = {
    "music": "Gigs",
    "arts": "Theatre & Arts",
    "arts & culture": "Theatre & Arts",
    "theatre": "Theatre & Arts",
    "family": "Family Days",
    "heritage": "Experiences",
    "nature & outdoors": "Experiences",
    "community": "Experiences",
    "markets": "Food & Drink",
    "workshops": "Experiences",
    "other": "Experiences",
}


def normalise_category(
    category: Optional[str],
    title: str = "",
    description: Optional[str] = None,
    source: str = "",
) -> str:
    raw = (category or "").strip().lower()
    haystack = " ".join((raw, title or "", description or "", source or "")).lower()

    for label, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return label

    return DIRECT_MAP.get(raw, "Experiences")
