"""
Unit tests for api_client.py — pure-logic pieces only (no network calls).

Run with:  python -m unittest discover -s tests
"""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import (
    _is_any_centre,
    _is_centre,
    _is_bst,
    _iso_z,
    _last_sunday,
    _parse_duration_minutes,
    _parse_iso,
    attach_booking_urls,
    join_data,
    to_uk_local,
    DataCache,
)


class TestParsing(unittest.TestCase):
    def test_parse_duration_minutes(self):
        self.assertEqual(_parse_duration_minutes("PT1H30M"), 90)
        self.assertEqual(_parse_duration_minutes("PT45M"), 45)
        self.assertEqual(_parse_duration_minutes("PT2H"), 120)
        self.assertIsNone(_parse_duration_minutes(None))
        self.assertIsNone(_parse_duration_minutes(""))

    def test_parse_iso(self):
        dt = _parse_iso("2026-06-30T10:00:00Z")
        self.assertEqual(dt, datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc))
        self.assertIsNone(_parse_iso(None))
        self.assertIsNone(_parse_iso("not-a-date"))


class TestIsBalham(unittest.TestCase):
    def test_matches_by_identifier(self):
        self.assertTrue(_is_centre({"location": {"identifier": "14"}}, "14"))

    def test_matches_by_name(self):
        self.assertTrue(_is_centre({"location": {"name": "Balham Leisure Centre"}}, "14"))

    def test_no_match(self):
        self.assertFalse(_is_centre({"location": {"identifier": "99", "name": "Tooting Centre"}}, "14"))

    def test_missing_location(self):
        self.assertFalse(_is_centre({}, "14"))

    def test_null_location(self):
        self.assertFalse(_is_centre({"location": None}, "14"))

    def test_null_name(self):
        # Regression: explicit null name must not raise AttributeError.
        self.assertFalse(_is_centre({"location": {"identifier": "99", "name": None}}, "14"))

    def test_any_centre_includes_tooting_bec_lido(self):
        self.assertTrue(_is_any_centre({"location": {"identifier": "17"}}))

    def test_any_centre_rejects_unknown_centre(self):
        self.assertFalse(_is_any_centre({"location": {"identifier": "99", "name": "Elsewhere"}}))


class TestUkDst(unittest.TestCase):
    def test_last_sunday_march_2026(self):
        self.assertEqual(_last_sunday(2026, 3).isoformat(), "2026-03-29")

    def test_last_sunday_october_2026(self):
        self.assertEqual(_last_sunday(2026, 10).isoformat(), "2026-10-25")

    def test_winter_is_gmt(self):
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(_is_bst(winter))
        self.assertEqual(to_uk_local(winter).utcoffset().total_seconds(), 0)

    def test_summer_is_bst(self):
        summer = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(_is_bst(summer))
        self.assertEqual(to_uk_local(summer).utcoffset().total_seconds(), 3600)

    def test_transition_boundary(self):
        # 2026-03-29 01:00 UTC is the instant clocks go forward.
        just_before = datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc)
        just_after = datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)
        self.assertFalse(_is_bst(just_before))
        self.assertTrue(_is_bst(just_after))

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime(2026, 1, 15, 12, 0)
        self.assertEqual(to_uk_local(naive), to_uk_local(naive.replace(tzinfo=timezone.utc)))


class TestJoinData(unittest.TestCase):
    def test_join_attaches_series_metadata(self):
        raw = {
            "session_series": [{"id": "s1", "name": "Swimming", "description": "", "category": "Swim",
                                 "activity": "Swimming", "centre_name": "Balham", "address": "", "postcode": "",
                                 "price": 5, "image": ""}],
            "scheduled_sessions": [{"id": "ss1", "series_id": "s1", "start": None, "end": None,
                                     "duration_minutes": 60, "remaining": 3, "max_capacity": 10,
                                     "location_name": ""}],
            "facility_uses": [],
            "slots": [],
        }
        sessions, facilities = join_data(raw)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["name"], "Swimming")
        self.assertEqual(sessions[0]["price"], 5)

    def test_join_falls_back_when_series_missing(self):
        raw = {
            "session_series": [],
            "scheduled_sessions": [{"id": "ss1", "series_id": "missing", "start": None, "end": None,
                                     "duration_minutes": 60, "remaining": 3, "max_capacity": 10,
                                     "location_name": "Court 1"}],
            "facility_uses": [],
            "slots": [],
        }
        sessions, _ = join_data(raw)
        self.assertEqual(sessions[0]["name"], "Court 1")


class TestAttachBookingUrls(unittest.TestCase):
    def test_facility_gets_calendar_link_without_widget_data(self):
        facilities = [{"facility_id": "014A200101", "url": "https://generic/",
                       "start": datetime(2026, 7, 4, 15, 30, tzinfo=timezone.utc)}]
        attach_booking_urls([], facilities, {})
        self.assertEqual(
            facilities[0]["url"],
            "https://placesleisure.gladstonego.cloud/book/calendar/014A200101?activityDate=2026-07-04T15:30:00Z",
        )

    def test_session_gets_details_link_when_widget_data_matches(self):
        start = datetime(2026, 7, 1, 5, 30, tzinfo=timezone.utc)
        end = datetime(2026, 7, 1, 6, 14, 59, tzinfo=timezone.utc)
        sessions = [{"series_id": "01430630SSS0824", "url": "https://generic/", "start": start, "end": end}]
        index = {("01430630SSS0824", start.replace(second=0, microsecond=0)):
                 {"ag": "HEALTH", "al": "014ZHEA001", "ti": "class"}}
        attach_booking_urls(sessions, [], index)
        url = sessions[0]["url"]
        self.assertIn("activityId=01430630SSS0824", url)
        self.assertIn("activityGroupId=HEALTH", url)
        self.assertIn("locationId=014ZHEA001", url)
        self.assertIn("siteId=14", url)

    def test_session_keeps_generic_url_when_no_widget_match(self):
        start = datetime(2026, 7, 1, 5, 30, tzinfo=timezone.utc)
        sessions = [{"series_id": "unknown", "url": "https://generic/", "start": start, "end": start}]
        attach_booking_urls(sessions, [], {})
        self.assertEqual(sessions[0]["url"], "https://generic/")

    def test_session_link_uses_its_own_centre_id(self):
        start = datetime(2026, 7, 1, 5, 30, tzinfo=timezone.utc)
        sessions = [{
            "series_id": "lido-series",
            "centre_id": "17",
            "url": "https://generic/",
            "start": start,
            "end": start,
        }]
        index = {("lido-series", start): {"ag": "SWIM", "al": "LIDO", "ti": "class"}}
        attach_booking_urls(sessions, [], index)
        self.assertIn("siteId=17", sessions[0]["url"])


class TestDataCacheFilters(unittest.TestCase):
    def setUp(self):
        self.cache = DataCache()
        self.items = [
            {"name": "Morning Swim", "category": "Swim", "activity": "Swimming",
             "remaining": 5, "max_capacity": 10,
             "start": datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc)},
            {"name": "Evening Gym", "category": "Gym", "activity": "Gym",
             "remaining": 0, "max_capacity": 10,
             "start": datetime(2026, 6, 30, 19, 0, tzinfo=timezone.utc)},
        ]

    def test_filter_by_availability(self):
        result = self.cache._filter_and_sort(list(self.items), {"availability": "avail"})
        self.assertEqual([x["name"] for x in result], ["Morning Swim"])

    def test_filter_by_time_of_day(self):
        result = self.cache._filter_and_sort(list(self.items), {"time_of_day": "evening"})
        self.assertEqual([x["name"] for x in result], ["Evening Gym"])

    def test_filter_by_search(self):
        result = self.cache._filter_and_sort(list(self.items), {"search": "swim"})
        self.assertEqual([x["name"] for x in result], ["Morning Swim"])

    def test_no_filters_sorts_by_start(self):
        result = self.cache._filter_and_sort(list(reversed(self.items)), None)
        self.assertEqual([x["name"] for x in result], ["Morning Swim", "Evening Gym"])


if __name__ == "__main__":
    unittest.main()
