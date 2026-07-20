"""
ZIP code → geographic distance helper (stdlib-only, no network calls).

Uses a bundled CSV of US ZIP code centroid coordinates derived from the
GeoNames data set (via pgeocode, pre-extracted at build time).  The data
lives at matching/data/us_zip_coordinates.csv and is shipped inside the
Docker image via the normal COPY . . step.

Public API
----------
zip_distance_miles(zip1, zip2) -> float | None
    Returns the great-circle distance in miles between the centroids of two
    US ZIP codes, or None if either ZIP is not found in the dataset.

get_zip_coordinates(zip_code) -> tuple[float, float] | None
    Returns (latitude, longitude) for a given ZIP, or None if not found.
    Strips ZIP+4 suffixes (e.g. '94103-1234' → '94103').
"""

import csv
import math
import os
import threading

# ── Module-level cache (loaded once, shared across all threads) ─────────────
_ZIP_DB: dict[str, tuple[float, float]] | None = None
_ZIP_DB_LOCK = threading.Lock()

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "us_zip_coordinates.csv")

# ── Earth radius (mean) in miles ────────────────────────────────────────────
_EARTH_RADIUS_MILES = 3_958.8


# =============================================================================
# Internal helpers
# =============================================================================

def _load_zip_db() -> dict[str, tuple[float, float]]:
    """
    Load the ZIP→(lat, lon) table from the bundled CSV file.

    Called at most once; subsequent calls return the cached dict.
    Thread-safe via a module-level lock.
    """
    global _ZIP_DB
    if _ZIP_DB is not None:
        return _ZIP_DB

    with _ZIP_DB_LOCK:
        if _ZIP_DB is not None:          # double-check after acquiring lock
            return _ZIP_DB

        db: dict[str, tuple[float, float]] = {}
        try:
            with open(_DATA_PATH, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        z = row["zip"].strip()
                        lat = float(row["lat"])
                        lon = float(row["lon"])
                        if z:
                            db[z] = (lat, lon)
                    except (ValueError, KeyError):
                        continue
        except FileNotFoundError:
            # Data file missing — graceful degradation: return empty dict so
            # the caller falls back to the legacy prefix-match logic.
            pass

        _ZIP_DB = db
        return _ZIP_DB


def _normalize_zip(zip_code: str) -> str:
    """
    Strip a ZIP+4 suffix and any whitespace.

    '94103-1234' → '94103'
    '94103'      → '94103'
    """
    return zip_code.strip().split("-")[0].strip()


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute the great-circle distance (haversine formula) between two
    geographic coordinates and return the result in miles.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_RADIUS_MILES * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =============================================================================
# Public API
# =============================================================================

def get_zip_coordinates(zip_code: str) -> tuple[float, float] | None:
    """
    Return (latitude, longitude) for a given US ZIP code, or None if the
    ZIP code is not in the bundled dataset.

    Handles ZIP+4 formats automatically (e.g. '94103-1234' → looks up '94103').
    """
    normalized = _normalize_zip(zip_code)
    return _load_zip_db().get(normalized)


def zip_distance_miles(zip1: str, zip2: str) -> float | None:
    """
    Return the great-circle distance in miles between the centroids of two
    US ZIP codes, or None if either ZIP is not found in the dataset.

    This function performs no network calls and adds no runtime dependencies
    beyond the Python standard library.

    Examples
    --------
    >>> zip_distance_miles("90210", "90211")    # Beverly Hills neighbours
    3.5                                          # approx
    >>> zip_distance_miles("94103", "10001")    # SF → Manhattan
    2571.0                                       # approx
    >>> zip_distance_miles("00000", "90210")    # invalid ZIP
    None
    """
    normalized1 = _normalize_zip(zip1)
    normalized2 = _normalize_zip(zip2)

    # Exact same ZIP — zero distance (also avoids floating-point noise)
    if normalized1 == normalized2:
        return 0.0

    db = _load_zip_db()
    coords1 = db.get(normalized1)
    coords2 = db.get(normalized2)

    if coords1 is None or coords2 is None:
        return None

    lat1, lon1 = coords1
    lat2, lon2 = coords2
    return round(_haversine_miles(lat1, lon1, lat2, lon2), 1)


def location_score_from_distance(distance_miles: float | None) -> float:
    """
    Map a geographic distance (in miles) to a location compatibility score
    out of 10 points.

    Scoring tiers
    -------------
    ≤  5 mi  → 10.0 pts  (essentially local / same neighbourhood)
    ≤ 15 mi  →  7.0 pts  (neighbouring city / suburb)
    ≤ 30 mi  →  4.0 pts  (reasonable commute)
    ≤ 50 mi  →  2.0 pts  (possible but distant)
    >  50 mi →  0.0 pts  (too far for practical home care)
    None     →  0.0 pts  (unknown / invalid ZIP — no award)

    Args:
        distance_miles: Distance computed by zip_distance_miles(), or None.

    Returns:
        float — points toward the 100-point match score.
    """
    if distance_miles is None:
        return 0.0
    if distance_miles <= 5:
        return 10.0
    if distance_miles <= 15:
        return 7.0
    if distance_miles <= 30:
        return 4.0
    if distance_miles <= 50:
        return 2.0
    return 0.0
