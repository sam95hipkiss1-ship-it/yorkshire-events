from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    title: str
    url: str
    source: str
    date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[str] = None
    all_day: bool = False

    @property
    def fingerprint(self) -> str:
        title_clean = self.title.lower().strip()
        for word in ["the ", "a ", "an "]:
            title_clean = title_clean.replace(word, "")
        title_clean = " ".join(title_clean.split())

        date_str = self.date.strftime("%Y-%m-%d") if self.date else ""
        return f"{title_clean}|{date_str}"
