# Yorkshire Events RSS Feed

A comprehensive RSS feed of live events happening across Yorkshire, UK. Aggregated from multiple sources and updated daily.

## Sources

- **What's On in Yorkshire** - General events across Yorkshire
- **Go Yorkshire** - Events and attractions
- **Whitby Events** - Whitby area events
- **Visit North Yorkshire** - North Yorkshire tourism events
- **Yorkshire.com** - Comprehensive Yorkshire listings
- **Yorkshire Gig Guide** - Music and gig listings (when available)

## RSS Feed URL

```
https://yorkshire-events.github.io/yorkshire-events/feed.xml
```

## How to Subscribe

1. Copy the RSS feed URL above
2. Open your preferred RSS reader app
3. Add a new feed and paste the URL
4. The feed updates automatically every day at 6:00 AM UTC

### Popular RSS Readers

- [Feedly](https://feedly.com/)
- [NetNewsWire](https://netnewswire.com/) (macOS/iOS)
- [Inoreader](https://inoreader.com/)
- [Miniflux](https://miniflux.app/)
- [Tiny Tiny RSS](https://tt-rss.org/)

## Local Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Aggregator

```bash
python aggregator.py
```

This will:
1. Fetch events from all sources
2. Deduplicate events across sources
3. Filter to only future events
4. Generate the RSS feed at `docs/feed.xml`

## Adding New Sources

To add a new source:

1. Create a new scraper in `scrapers/` directory
2. Implement a function that returns a list of `Event` objects
3. Import and call the function in `aggregator.py`

### Event Data Structure

```python
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
```

## Deployment

This project is designed to be deployed on GitHub Pages:

1. Create a GitHub repository
2. Push this code to the repository
3. Enable GitHub Pages in repository settings
4. The GitHub Actions workflow will automatically update the feed daily

## License

MIT
