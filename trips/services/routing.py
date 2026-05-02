import logging
from typing import NamedTuple, Optional

import requests

logger = logging.getLogger(__name__)


class RouteResult(NamedTuple):
    """Result of calling OSRM for a driving route."""

    route: Optional[dict]
    error_message: Optional[str]
    client_error: bool


def get_route(start, pickup, dropoff) -> RouteResult:
    coords = (
        f"{start['lon']},{start['lat']};"
        f"{pickup['lon']},{pickup['lat']};"
        f"{dropoff['lon']},{dropoff['lat']}"
    )
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}"

    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    try:
        res = requests.get(url, params=params, timeout=15)

        try:
            data = res.json()
        except ValueError:
            logger.error("Routing failed: invalid JSON from OSRM HTTP %s", res.status_code)
            return RouteResult(
                route=None,
                error_message="Routing service returned an invalid response. Try again shortly.",
                client_error=False,
            )

        if not isinstance(data, dict):
            logger.error("Routing failed: unexpected OSRM payload type")
            return RouteResult(
                route=None,
                error_message="Unexpected routing response. Try again shortly.",
                client_error=False,
            )

        osrm_code = str(data.get("code") or "")
        routes = data.get("routes")
        msg = str(data.get("message") or "").strip()

        if (
            osrm_code == "Ok"
            and isinstance(routes, list)
            and len(routes) > 0
        ):
            route = routes[0]

            distance_miles = route["distance"] / 1609.34
            duration_hours = route["duration"] / 3600

            legs_out = []
            raw_legs = route.get("legs")
            if isinstance(raw_legs, list):
                for leg in raw_legs:
                    if not isinstance(leg, dict):
                        continue
                    try:
                        legs_out.append(
                            {
                                "distance": float(leg["distance"]) / 1609.34,
                                "duration": float(leg["duration"]) / 3600.0,
                            }
                        )
                    except (KeyError, TypeError, ValueError):
                        continue

            if len(legs_out) < 2:
                legs_out = [
                    {"distance": 0.0, "duration": 0.0},
                    {
                        "distance": distance_miles,
                        "duration": duration_hours,
                    },
                ]

            return RouteResult(
                route={
                    "distance": distance_miles,
                    "duration": duration_hours,
                    "geometry": route["geometry"],
                    "legs": legs_out,
                },
                error_message=None,
                client_error=False,
            )

        client_codes = ("NoRoute", "NoSegment")
        if osrm_code in client_codes:
            hint = (
                msg
                if msg
                else "These points may be off-road, disconnected, or in the wrong region."
            )
            return RouteResult(
                route=None,
                error_message=(
                    f"No drivable route between these locations: {hint} "
                    "Try more precise addresses or map clicks on roads."
                ),
                client_error=True,
            )

        if osrm_code == "Ok":
            logger.warning(
                "OSRM returned Ok without routes coords=%s", coords[:80]
            )
            return RouteResult(
                route=None,
                error_message="Routing service returned no path. Try different locations.",
                client_error=False,
            )

        if not res.ok:
            logger.warning(
                "OSRM HTTP %s code=%s message=%s",
                res.status_code,
                osrm_code or "<empty>",
                msg or data,
            )
            return RouteResult(
                route=None,
                error_message=msg or "Routing service unavailable. Try again in a moment.",
                client_error=False,
            )

        logger.warning(
            "OSRM unexpected code=%s message=%s payload=%s",
            osrm_code or "<empty>",
            msg,
            data,
        )
        return RouteResult(
            route=None,
            error_message=(
                msg
                if msg
                else "Could not calculate a route. Try different locations."
            ),
            client_error=False,
        )

    except requests.Timeout:
        logger.error("Routing failed: timeout")
        return RouteResult(
            route=None,
            error_message="Routing service timed out. Try again shortly.",
            client_error=False,
        )
    except requests.RequestException as e:
        logger.error("Routing failed: %s", e)
        return RouteResult(
            route=None,
            error_message="Could not reach routing service. Check network and try again.",
            client_error=False,
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.error("Routing failed: unexpected response shape: %s", e)
        return RouteResult(
            route=None,
            error_message="Unexpected routing response. Try again or use different coordinates.",
            client_error=False,
        )
