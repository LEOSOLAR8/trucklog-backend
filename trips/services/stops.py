import math

from .hos_calculator import BREAK_AFTER_HOURS, MAX_DRIVE_HOURS
from .hos_calculator import ceil_half_hour


def calculate_rest_stops(drive_before_pickup, drive_after_pickup):
    """
    Milestones where mandatory break or end-of-driving-day rest is needed.
    after_hours counts hours of driving elapsed along the route (OSRM duration axis),
    in order: current→pickup, then pickup→dropoff (pickup time itself does not advance this).
    """
    leg1 = ceil_half_hour(drive_before_pickup)
    leg2 = ceil_half_hour(drive_after_pickup)
    if leg1 <= 0 and leg2 <= 0:
        return []

    stops = []
    drive_into_trip = 0.0

    while leg1 > 1e-9 or leg2 > 1e-9:
        drive_today = 0.0
        break_taken = False

        while drive_today < MAX_DRIVE_HOURS and (leg1 > 1e-9 or leg2 > 1e-9):
            pool = leg1 if leg1 > 1e-9 else leg2

            if drive_today >= BREAK_AFTER_HOURS and not break_taken:
                stops.append(
                    {
                        "type": "rest",
                        "after_hours": ceil_half_hour(drive_into_trip),
                        "reason": "30_min_break",
                    }
                )
                break_taken = True
                continue

            chunk = min(
                MAX_DRIVE_HOURS - drive_today,
                pool,
                (BREAK_AFTER_HOURS - drive_today) if not break_taken else MAX_DRIVE_HOURS - drive_today,
            )
            if chunk <= 0:
                break

            drive_into_trip += chunk
            drive_today += chunk
            if leg1 > 1e-9:
                leg1 -= chunk
            else:
                leg2 -= chunk

        if leg1 > 1e-9 or leg2 > 1e-9:
            stops.append(
                {
                    "type": "rest",
                    "after_hours": ceil_half_hour(drive_into_trip),
                    "reason": "hos_daily_limit",
                }
            )

    return stops


def haversine_distance(coord1, coord2):
    # returns miles
    from math import radians, sin, cos, sqrt, atan2

    lat1, lon1 = coord1
    lat2, lon2 = coord2

    R = 3958.8  # Earth radius in miles

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def interpolate_point(p1, p2, fraction):
    lat = p1[0] + (p2[0] - p1[0]) * fraction
    lon = p1[1] + (p2[1] - p1[1]) * fraction
    return [lat, lon]


def generate_stops_from_geometry(geometry, total_distance_miles):
    coords = [(lat, lon) for lon, lat in geometry["coordinates"]]

    fuel_interval = 1000
    fuel_targets = [i * fuel_interval for i in range(1, int(total_distance_miles // fuel_interval) + 1)]

    stops = []
    cumulative = 0
    target_index = 0

    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]

        segment_dist = haversine_distance(p1, p2)

        while target_index < len(fuel_targets) and cumulative + segment_dist >= fuel_targets[target_index]:
            remaining = fuel_targets[target_index] - cumulative
            fraction = remaining / segment_dist if segment_dist != 0 else 0

            stop_point = interpolate_point(p1, p2, fraction)

            stops.append({
                "type": "fuel",
                "location": {
                    "lat": stop_point[0],
                    "lng": stop_point[1]
                },
                "mile_marker": fuel_targets[target_index]
            })

            target_index += 1

        cumulative += segment_dist

    return stops