"""Regression tests for Yorkshire Events aggregator identity and filtering."""
import unittest
from datetime import datetime, timedelta, timezone

from aggregator import deduplicate_events, filter_future_events
from scrapers import Event


def event(title, url, start, location="Temple Newsam", source="Leeds Museums and Galleries", all_day=True):
    return Event(title=title, url=url, source=source, date=start, location=location, all_day=all_day)


class EventDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.day = datetime(2026, 12, 5, 0, 0)

    def test_duplicate_same_performance_different_urls(self):
        first = event("Home Educator Afternoons", "https://events.example/a?utm_source=one", self.day)
        second = event("Home Educator Afternoons", "https://events.example/b", self.day)
        actual = deduplicate_events([first, second])
        self.assertEqual(1, len(actual))

    def test_different_dates_same_url_remain_separate(self):
        first = event("Home Educator Afternoons", "https://events.example/a", self.day)
        second = event("Home Educator Afternoons", "https://events.example/a", self.day + timedelta(days=7))
        self.assertEqual(2, len(deduplicate_events([first, second])))

    def test_same_title_and_day_different_venues_remain_separate(self):
        first = event("Home Educator Afternoons", "https://events.example/a", self.day, "Temple Newsam")
        second = event("Home Educator Afternoons", "https://events.example/b", self.day, "Leeds City Museum")
        self.assertEqual(2, len(deduplicate_events([first, second])))

    def test_same_title_and_day_different_times_remain_separate(self):
        first = event("Talk and Tour", "https://events.example/a", self.day.replace(hour=10), all_day=False)
        second = event("Talk and Tour", "https://events.example/a", self.day.replace(hour=14), all_day=False)
        self.assertEqual(2, len(deduplicate_events([first, second])))

    def test_tracking_parameters_do_not_duplicate(self):
        first = event("Yorkshire Arts Weekend", "https://events.example/arts?utm_source=facebook&event=1", self.day)
        second = event("Yorkshire Arts Weekend", "https://www.events.example/arts?event=1&fbclid=abc", self.day)
        self.assertEqual(1, len(deduplicate_events([first, second])))

    def test_generic_calendar_pages_are_not_events(self):
        records = [
            event("Events calendar", "https://example.org/a/2026", self.day),
            event("Events calendar", "https://example.org/b/2026", self.day),
            event("Yorkshire Folk Festival", "https://example.org/festival", self.day),
        ]
        self.assertEqual(["Yorkshire Folk Festival"], [e.title for e in deduplicate_events(records)])

    def test_undated_copy_of_same_url_is_removed(self):
        dated = event("Leeds Autumn Festival", "https://example.org/festival", self.day)
        undated = event("Leeds Autumn Festival", "https://example.org/festival", None)
        self.assertEqual([dated], deduplicate_events([undated, dated]))

    def test_aware_dates_do_not_crash_future_filter(self):
        distant_future = datetime.now(timezone.utc) + timedelta(days=20)
        result = filter_future_events([
            event("Coming Soon", "https://example.org/future", distant_future, all_day=False)
        ])
        self.assertEqual(1, len(result))


if __name__ == "__main__":
    unittest.main()
