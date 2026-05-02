import logging
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"


def resolve_location_payload(value: Any) -> Optional[Dict[str, float]]:
    """Turn API input into routing coords {\"lat\",\"lon\"}. Accepts plain string or {lat,lng|lon}."""
    if value is None:
        return None
    if isinstance(value, str):
        q = value.strip()
        return geocode_location(q) if q else None
    if isinstance(value, dict):
        try:
            raw_lat = value.get("lat")
            if raw_lat is None:
                return None
            lat_f = float(raw_lat)
            lon_raw = value.get("lng")
            if lon_raw is None:
                lon_raw = value.get("lon")
            if lon_raw is None:
                return None
            lon_f = float(lon_raw)
            if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
                return None
            return {"lat": lat_f, "lon": lon_f}
        except (TypeError, ValueError):
            return None
    return None


def geocode_location(query: str) -> Optional[Dict[str, Any]]:
    """Resolve a free-text place to {lat, lon} using Nominatim (OSM)."""
    if not query or not str(query).strip():
        return None

    params: Dict[str, Any] = {
        "q": query.strip(),
        "format": "json",
        "limit": 1,
    }
    codes = str(getattr(settings, "GEOCODING_COUNTRY_CODES", "") or "").strip()
    if codes:
        params["countrycodes"] = codes.lower()

    try:
        res = requests.get(
            NOMINATIM_SEARCH,
            params=params,
            headers={"User-Agent": "TruckLog/1.0 (home assignment)"},
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()
        if not data:
            return None
        first = data[0]
        return {"lat": float(first["lat"]), "lon": float(first["lon"])}
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        logger.warning("Geocode failed for %r: %s", query, e)
        return None
