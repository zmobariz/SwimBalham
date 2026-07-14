"""
OpenActive RPDE API Client — multi-centre (Balham + Tooting Bec Lido).

Fetches data from all four RPDE feeds, filters to supported centres, and
provides local JSON caching for instant startup.
"""

import requests
import json
import os
import sys
import re
import html
import threading
from datetime import datetime, timezone, timedelta, date

BASE = "https://opendata.leisurecloud.live/api/feeds"
APP_NAME = "SwimBalham"

# ── Supported centres ─────────────────────────────────────────────────────
# Each entry maps a centre_id to its display info.
CENTRES = {
    "14": {
        "name": "Balham Leisure Centre",
        "postcode": "SW17 8AN",
        "address": "Balham, London",
        "url": "https://www.placesleisure.org/centres/balham-leisure-centre/",
    },
    "17": {
        "name": "Tooting Bec Lido",
        "postcode": "SW16 1RU",
        "address": "Tooting Bec Common, London",
        "url": "https://www.placesleisure.org/centres/tooting-bec-lido/",
    },
}
# Default centre for backward-compat
DEFAULT_CENTRE_ID = "14"

# The centre's own booking widget page (separate from the OpenActive feed)
# embeds a JSON blob that its own JS uses to build genuine per-session
# Gladstone booking links. The OpenActive feed doesn't expose the two fields
# (activityGroupId/locationId) that link needs, so we scrape this as a
# best-effort enrichment — if the page layout ever changes, this quietly
# yields nothing and callers fall back to the generic centre-page URL.
TIMETABLE_PAGE_URL = "https://www.placesleisure.org/centres/balham-leisure-centre/"
GLADSTONE_BOOK_BASE = "https://placesleisure.gladstonego.cloud/book"

def _get_data_dir():
    """Return a per-user, non-admin-writable directory for app data."""
    override = os.environ.get("SWIMBALHAM_DATA_DIR")
    if override:
        data_dir = os.path.abspath(os.path.expanduser(override))
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        data_dir = os.path.join(local_app_data, APP_NAME)
    else:
        data_home = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        data_dir = os.path.join(data_home, APP_NAME)
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        # Read/write methods already handle an unavailable directory gracefully.
        pass
    return data_dir


DATA_DIR = _get_data_dir()
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
_LEGACY_APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LEGACY_CACHE_FILE = os.path.join(_LEGACY_APP_DIR, "cache.json")

FEEDS = {
    "session_series": f"{BASE}/PlacesLeisure-live-session-series",
    "scheduled_sessions": f"{BASE}/PlacesLeisure-live-scheduled-sessions",
    "facility_uses": f"{BASE}/PlacesLeisure-live-facility-uses",
    "slots": f"{BASE}/PlacesLeisure-live-slots",
}

UK_GMT = timezone.utc
UK_BST = timezone(timedelta(hours=1))


def _last_sunday(year, month):
    """The date of the last Sunday in the given month/year."""
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = first_of_next - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - 6) % 7)


def _is_bst(dt_utc):
    """UK clocks go forward (BST) at 01:00 UTC on the last Sunday in March,
    and back (GMT) at 01:00 UTC on the last Sunday in October."""
    year = dt_utc.year
    start = datetime(year, 3, _last_sunday(year, 3).day, 1, tzinfo=timezone.utc)
    end = datetime(year, 10, _last_sunday(year, 10).day, 1, tzinfo=timezone.utc)
    return start <= dt_utc < end


def to_uk_local(dt):
    """Convert an aware (or naive-UTC) datetime to UK local time, correctly
    accounting for the GMT/BST transition rather than assuming a fixed offset."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.astimezone(UK_BST if _is_bst(dt_utc) else UK_GMT)


def uk_now():
    return to_uk_local(datetime.now(timezone.utc))


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_duration_minutes(duration):
    if not duration:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _iso_z(dt):
    """Format a datetime the way the Gladstone booking site expects
    (UTC, 'Z' suffix), matching what its own JS generates."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_centre(data, centre_id):
    """Check if a raw RPDE item belongs to the given centre_id."""
    loc = data.get("location") or {}
    if str(loc.get("identifier", "")) == centre_id:
        return True
    # Fallback: match by centre name keyword
    centre_info = CENTRES.get(centre_id)
    if centre_info:
        name_lower = (loc.get("name") or "").lower()
        centre_name_lower = centre_info["name"].lower()
        # Match on distinctive words to avoid false positives
        if centre_name_lower in name_lower:
            return True
        # "balham" or "tooting bec lido" substring checks
        for keyword in ("balham", "tooting bec lido"):
            if keyword in name_lower and keyword in centre_name_lower:
                return True
    return False


def _is_any_centre(data):
    """Check if a raw RPDE item belongs to any supported centre."""
    return any(_is_centre(data, cid) for cid in CENTRES)


class PlacesLeisureClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "SwimBalham/1.0 (+https://github.com/zmobariz/SwimBalham)",
            "Accept": "application/json",
        })

    def fetch_all(self, progress_callback=None, max_days=None):
        """
        Fetch all four feeds, filter to supported centres, join, and return
        enriched data for ALL configured centres. The UI filters by centre.

        If max_days is set, sessions/slots starting more than that many days
        from now are pruned before caching — this massively reduces data volume
        for first-time users (1 day ≈ instant, vs 14 days ≈ 80K items).
        """
        from datetime import timedelta as td
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc + td(days=max_days) if max_days else None

        results = {
            "session_series": [],
            "scheduled_sessions": [],
            "facility_uses": [],
            "slots": [],
        }

        # Build sets of series/facility IDs for all centres
        series_ids = set()
        series_data = []

        # Phase 1: Fetch SessionSeries (filter to any supported centre)
        if progress_callback:
            progress_callback("session_series", None)
        for item in self._paginate(FEEDS["session_series"]):
            if _is_any_centre(item):
                norm = self._norm_session_series(item)
                if norm:
                    series_data.append(norm)
                    series_ids.add(norm["id"])
        results["session_series"] = series_data
        if progress_callback:
            progress_callback("session_series", len(series_data))

        # Phase 2: Fetch ScheduledSessions (filter by superEvent → our series)
        if progress_callback:
            progress_callback("scheduled_sessions", None)
        for item in self._paginate(FEEDS["scheduled_sessions"]):
            super_event = item.get("superEvent", "")
            sid = super_event.rstrip("/").split("/")[-1] if super_event else ""
            if sid in series_ids:
                norm = self._norm_scheduled_session(item)
                if norm:
                    # Prune sessions beyond the cutoff date
                    if cutoff and norm.get("start") and norm["start"] > cutoff:
                        continue
                    results["scheduled_sessions"].append(norm)
        if progress_callback:
            progress_callback("scheduled_sessions", len(results["scheduled_sessions"]))

        # Phase 3: Fetch FacilityUses (filter to supported centres)
        if progress_callback:
            progress_callback("facility_uses", None)
        facility_ids = set()
        for item in self._paginate(FEEDS["facility_uses"]):
            if _is_any_centre(item):
                norm = self._norm_facility_use(item)
                if norm:
                    results["facility_uses"].append(norm)
                    facility_ids.add(norm["id"])
        if progress_callback:
            progress_callback("facility_uses", len(results["facility_uses"]))

        # Phase 4: Fetch Slots (filter to supported facilities)
        if progress_callback:
            progress_callback("slots", None)
        for item in self._paginate(FEEDS["slots"]):
            fu_url = item.get("facilityUse", "")
            fid = fu_url.rstrip("/").split("/")[-1] if fu_url else ""
            if fid in facility_ids:
                norm = self._norm_slot(item)
                if norm:
                    if cutoff and norm.get("start") and norm["start"] > cutoff:
                        continue
                    results["slots"].append(norm)
        if progress_callback:
            progress_callback("slots", len(results["slots"]))

        # Phase 5: Scrape booking links for each centre
        if progress_callback:
            progress_callback("booking_links", None)
        results["timetable_index"] = self._fetch_timetable_index()
        if progress_callback:
            progress_callback("booking_links", len(results["timetable_index"]))

        return results

    def _fetch_timetable_index(self):
        """Scrape the centre page's embedded booking-widget JSON, returning
        {(activityId, start_minute): {ag, al, ti}} for every session it
        knows about. Returns {} on any failure — this is an enrichment,
        never a hard dependency for the core OpenActive-derived data."""
        try:
            resp = self.session.get(TIMETABLE_PAGE_URL, timeout=20)
            resp.raise_for_status()
            m = re.search(r'id="timetable-data"[^>]*value="(.*?)"\s*/?>', resp.text, re.S)
            if not m:
                return {}
            data = json.loads(html.unescape(m.group(1)))
        except (requests.RequestException, ValueError) as e:
            print(f"[API] Booking-link scrape skipped: {e}")
            return {}

        index = {}
        for timetable in data.get("timetables", []):
            for s in timetable.get("sessions", []):
                start = _parse_iso(s.get("s"))
                aid = s.get("aId")
                if not start or not aid:
                    continue
                key = (aid, start.astimezone(timezone.utc).replace(second=0, microsecond=0))
                index[key] = {"ag": s.get("ag", ""), "al": s.get("al", ""), "ti": s.get("ti", "")}
        return index

    def _paginate(self, url):
        """RPDE pagination — yields raw data dicts.

        Raises rather than silently truncating on a failed request or an
        unfinished feed, so a transient network error can't be mistaken by
        the caller for a complete (but partial) fetch and cached as such.
        """
        current_url = url
        seen = set()
        for _ in range(2000):
            if not current_url or current_url in seen:
                return
            seen.add(current_url)
            try:
                resp = self.session.get(current_url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as e:
                raise RuntimeError(f"Failed to fetch RPDE page {current_url}: {e}") from e
            items = data.get("items", [])
            if not items:
                return
            for item in items:
                if item.get("state") == "updated" and item.get("data"):
                    yield item["data"]
            nxt = data.get("next")
            if not nxt or nxt == current_url:
                return
            current_url = nxt
        raise RuntimeError(f"RPDE feed {url} did not finish pagination within 2000 pages")

    # ── Normalisers ──
    def _extract_location(self, d):
        loc = d.get("location") or {}
        addr = loc.get("address") or {}
        parts = [addr.get("streetAddress"), addr.get("addressLocality"), addr.get("postalCode")]
        return {
            "centre_id": str(loc.get("identifier", "")),
            "centre_name": loc.get("name", "Balham Leisure Centre"),
            "address": ", ".join(p for p in parts if p),
            "postcode": addr.get("postalCode", ""),
            "latitude": (loc.get("geo") or {}).get("latitude"),
            "longitude": (loc.get("geo") or {}).get("longitude"),
        }

    def _norm_session_series(self, d):
        loc = self._extract_location(d)
        activities = d.get("activity", [])
        categories = d.get("category", [])
        offers = d.get("offers", [])
        images = d.get("image", [])
        return {
            "type": "session_series",
            "id": d.get("identifier", ""),
            "name": d.get("name", "Session"),
            "description": d.get("description", ""),
            "category": categories[0] if categories else "",
            "activity": activities[0].get("prefLabel", "") if activities else "",
            "price": offers[0].get("price") if offers else None,
            "centre_id": loc["centre_id"],
            "centre_name": loc["centre_name"],
            "address": loc["address"],
            "postcode": loc["postcode"],
            "duration_minutes": _parse_duration_minutes(d.get("duration")),
            "image": (images[0].get("url", "") if images else ""),
            "attendee_instructions": d.get("attendeeInstructions", ""),
            "url": d.get("url", ""),
        }

    def _norm_scheduled_session(self, d):
        super_event = d.get("superEvent", "")
        sid = super_event.rstrip("/").split("/")[-1] if super_event else ""
        return {
            "type": "scheduled_session",
            "id": str(d.get("identifier", "")),
            "series_id": sid,
            "start": _parse_iso(d.get("startDate")),
            "end": _parse_iso(d.get("endDate")),
            "duration_minutes": _parse_duration_minutes(d.get("duration")),
            "remaining": d.get("remainingAttendeeCapacity"),
            "max_capacity": d.get("maximumAttendeeCapacity"),
            "location_name": (
                d.get("beta:sportsActivityLocation", [{}])[0].get("name", "")
                if d.get("beta:sportsActivityLocation") else ""
            ),
        }

    def _norm_facility_use(self, d):
        loc = self._extract_location(d)
        activities = d.get("activity", [])
        categories = d.get("category", [])
        images = d.get("image", [])
        return {
            "type": "facility_use",
            "id": d.get("identifier", ""),
            "name": d.get("name", "Facility"),
            "description": d.get("description", ""),
            "category": categories[0] if categories else "",
            "activity": activities[0].get("prefLabel", "") if activities else "",
            "centre_id": loc["centre_id"],
            "centre_name": loc["centre_name"],
            "address": loc["address"],
            "postcode": loc["postcode"],
            "image": (images[0].get("url", "") if images else ""),
            "url": d.get("url", ""),
        }

    def _norm_slot(self, d):
        fu_url = d.get("facilityUse", "")
        fid = fu_url.rstrip("/").split("/")[-1] if fu_url else ""
        offers = d.get("offers", [])
        loc_names = d.get("beta:sportsActivityLocation", [])
        court_names = []
        if loc_names:
            names = loc_names[0].get("name", [])
            court_names = names if isinstance(names, list) else [names]
        return {
            "type": "slot",
            "id": d.get("identifier", ""),
            "facility_id": fid,
            "start": _parse_iso(d.get("startDate")),
            "end": _parse_iso(d.get("endDate")),
            "duration_minutes": _parse_duration_minutes(d.get("duration")),
            "remaining": d.get("remainingUses"),
            "max_capacity": d.get("maximumUses"),
            "price": offers[0].get("price") if offers else None,
            "courts": court_names,
        }


def join_data(raw):
    """Join sessions and facilities with their parent metadata."""
    series_map = {s["id"]: s for s in raw.get("session_series", [])}
    fu_map = {f["id"]: f for f in raw.get("facility_uses", [])}

    sessions = []
    for sched in raw.get("scheduled_sessions", []):
        row = dict(sched)
        series = series_map.get(sched["series_id"])
        if series:
            for k in ("name", "description", "category", "activity", "centre_id", "centre_name",
                       "address", "postcode", "price", "image", "url"):
                row[k] = series.get(k, "")
        else:
            row.setdefault("name", sched.get("location_name", "Session"))
            row.setdefault("description", "")
            row.setdefault("category", "")
            row.setdefault("activity", "")
            row.setdefault("centre_id", DEFAULT_CENTRE_ID)
            row.setdefault("centre_name", "Balham Leisure Centre")
            row.setdefault("address", "")
            row.setdefault("postcode", "")
            row.setdefault("price", None)
            row.setdefault("image", "")
            row.setdefault("url", "")
        sessions.append(row)

    facilities = []
    for slot in raw.get("slots", []):
        row = dict(slot)
        fu = fu_map.get(slot["facility_id"])
        if fu:
            for k in ("name", "description", "category", "activity", "centre_id", "centre_name",
                       "address", "postcode", "image", "url"):
                row[k] = fu.get(k, "")
        else:
            row.setdefault("name", "Facility")
            row.setdefault("description", "")
            row.setdefault("category", "")
            row.setdefault("activity", "")
            row.setdefault("centre_id", DEFAULT_CENTRE_ID)
            row.setdefault("centre_name", "Balham Leisure Centre")
            row.setdefault("address", "")
            row.setdefault("postcode", "")
            row.setdefault("image", "")
            row.setdefault("url", "")
        facilities.append(row)

    return sessions, facilities


def attach_booking_urls(sessions, facilities, timetable_index):
    """Upgrade each item's generic centre-page URL to a direct Gladstone
    booking deep link, where the facility_id/series_id + start time let us
    build one exactly. Silently leaves the generic URL in place otherwise —
    this is enrichment, not a required step."""
    for item in facilities:
        start = item.get("start")
        fid = item.get("facility_id")
        if start and fid:
            item["url"] = f"{GLADSTONE_BOOK_BASE}/calendar/{fid}?activityDate={_iso_z(start)}"

    if not timetable_index:
        return

    for item in sessions:
        start = item.get("start")
        series_id = item.get("series_id")
        if not (start and series_id):
            continue
        key = (series_id, start.astimezone(timezone.utc).replace(second=0, microsecond=0))
        enrich = timetable_index.get(key)
        if not enrich:
            continue
        if enrich["ti"] == "activity":
            item["url"] = f"{GLADSTONE_BOOK_BASE}/calendar/{series_id}?activityDate={_iso_z(start)}"
        else:
            end = item.get("end") or start
            site_id = item.get("centre_id") or DEFAULT_CENTRE_ID
            item["url"] = (
                f"{GLADSTONE_BOOK_BASE}/details?activityEndTime={_iso_z(end)}"
                f"&activityGroupId={enrich['ag']}&activityId={series_id}"
                f"&activityStartTime={_iso_z(start)}&locationId={enrich['al']}"
                f"&siteId={site_id}"
            )


class DataCache:
    """Thread-safe cache with JSON persistence for instant startup."""

    def __init__(self):
        self._lock = threading.Lock()
        self._raw = {}
        self._sessions = []
        self._facilities = []
        self._activities = set()
        self._categories = set()
        self._last_updated = None
        self._last_synced_feed = ""

    def update(self, raw):
        with self._lock:
            self._raw = raw
            self._sessions, self._facilities = join_data(raw)
            attach_booking_urls(self._sessions, self._facilities, raw.get("timetable_index", {}))
            self._activities = sorted({
                x.get("activity", "") for x in self._sessions + self._facilities
                if x.get("activity")
            })
            self._categories = sorted({
                x.get("category", "") for x in self._sessions + self._facilities
                if x.get("category")
            })
            self._last_updated = datetime.now(timezone.utc)

    def save_to_disk(self):
        """Persist current data to cache.json so next launch is instant."""
        with self._lock:
            data = {
                "sessions": _serialise(self._sessions),
                "facilities": _serialise(self._facilities),
                "activities": self._activities,
                "categories": self._categories,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError as e:
            print(f"[Cache] Save error: {e}")

    def load_from_disk(self):
        """Load cached data for instant display. Returns True if loaded."""
        source_file = CACHE_FILE
        if not os.path.exists(source_file) and os.path.exists(LEGACY_CACHE_FILE):
            source_file = LEGACY_CACHE_FILE
        if not os.path.exists(source_file):
            return False
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._sessions = _deserialise(data.get("sessions", []))
                self._facilities = _deserialise(data.get("facilities", []))
                self._activities = data.get("activities", [])
                self._categories = data.get("categories", [])
                saved = data.get("saved_at")
                self._last_updated = _parse_iso(saved) if saved else None
            print(f"[Cache] Loaded {len(self._sessions)} sessions, {len(self._facilities)} facilities from disk")
            if source_file != CACHE_FILE:
                self.save_to_disk()
            return True
        except (OSError, ValueError) as e:
            print(f"[Cache] Load error: {e}")
            return False

    def get_sessions(self, filters=None):
        with self._lock:
            results = list(self._sessions)
        return self._filter_and_sort(results, filters)

    def get_facilities(self, filters=None):
        with self._lock:
            results = list(self._facilities)
        return self._filter_and_sort(results, filters)

    def find(self, item_type, item_id):
        """Look up a single item's current state by type+id (used to re-check
        availability of a watched item after a refresh)."""
        with self._lock:
            for x in self._sessions + self._facilities:
                if x.get("type") == item_type and str(x.get("id")) == str(item_id):
                    return dict(x)
        return None

    def _filter_and_sort(self, items, filters):
        if not filters:
            items.sort(key=lambda x: x.get("start") or datetime.max.replace(tzinfo=timezone.utc))
            return items

        # ── Centre filter ──
        centre = filters.get("centre")
        if centre and centre != "All":
            items = [x for x in items if x.get("centre_name", "") == centre]

        category = filters.get("category")
        if category and category != "All":
            items = [x for x in items if x.get("category", "") == category]

        activity = filters.get("activity")
        if activity and activity != "All":
            items = [x for x in items if x.get("activity", "") == activity]

        search = filters.get("search", "").lower().strip()
        if search:
            items = [
                x for x in items
                if search in x.get("name", "").lower()
                or search in x.get("description", "").lower()
                or search in x.get("activity", "").lower()
            ]

        avail = filters.get("availability")
        if avail == "avail":
            items = [x for x in items if (x.get("remaining") or 0) > 0]
        elif avail == "full":
            items = [x for x in items if (x.get("remaining") or 0) == 0]

        # ── Date filter ──
        date_from = filters.get("date_from")
        if date_from:
            items = [x for x in items if x.get("start") and to_uk_local(x["start"]).date() >= date_from]

        date_to = filters.get("date_to")
        if date_to:
            items = [x for x in items if x.get("start") and to_uk_local(x["start"]).date() <= date_to]

        # ── Specific date filter (takes precedence over from/to) ──
        specific_date = filters.get("specific_date")
        if specific_date:
            items = [x for x in items if x.get("start") and to_uk_local(x["start"]).date() == specific_date]

        # ── Time-of-day filter ──
        tod = filters.get("time_of_day", "all")
        if tod != "all":
            def in_range(x):
                st = x.get("start")
                if not st:
                    return False
                h = to_uk_local(st).hour
                if tod == "morning":
                    return 6 <= h < 12
                elif tod == "afternoon":
                    return 12 <= h < 17
                elif tod == "evening":
                    return 17 <= h < 22
                return True
            items = [x for x in items if in_range(x)]

        items.sort(key=lambda x: x.get("start") or datetime.max.replace(tzinfo=timezone.utc))
        return items

    @property
    def activities(self):
        with self._lock:
            return list(self._activities)

    @property
    def categories(self):
        with self._lock:
            return list(self._categories)

    @property
    def centre_names(self):
        """Unique centre names currently in the cache."""
        with self._lock:
            return sorted({
                x.get("centre_name", "") for x in self._sessions + self._facilities
                if x.get("centre_name")
            })

    @property
    def last_updated(self):
        with self._lock:
            return self._last_updated

    @property
    def is_empty(self):
        with self._lock:
            return len(self._sessions) == 0 and len(self._facilities) == 0

    @property
    def sessions_count(self):
        with self._lock:
            return len(self._sessions)

    @property
    def facilities_count(self):
        with self._lock:
            return len(self._facilities)


def _serialise(items):
    """Convert datetime objects to ISO strings for JSON."""
    out = []
    for item in items:
        row = dict(item)
        for k in ("start", "end"):
            if row.get(k) and isinstance(row[k], datetime):
                row[k] = row[k].isoformat()
        out.append(row)
    return out


def _deserialise(items):
    """Convert ISO strings back to datetime objects."""
    out = []
    for item in items:
        row = dict(item)
        for k in ("start", "end"):
            if row.get(k) and isinstance(row[k], str):
                row[k] = _parse_iso(row[k])
        out.append(row)
    return out
