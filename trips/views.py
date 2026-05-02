import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import TripSubmission
from .services.driver_schedule import annotate_calendar_dates
from .services.driver_schedule import parse_duty_clock
from .services.driver_schedule import parse_log_date
from .services.driver_schedule import persisted_driver_payload
from .services.geocode import resolve_location_payload
from .services.routing import get_route
from .services.stops import calculate_rest_stops
from .services.stops import generate_stops_from_geometry
from .services.hos_calculator import ceil_half_hour
from .services.hos_calculator import generate_eld_logs

logger = logging.getLogger(__name__)


@api_view(["POST"])
def trip_plan(request):
    try:
        data = request.data

        loc_keys = ("current_location", "pickup_location", "dropoff_location")
        missing = [k for k in loc_keys if k not in data]
        if missing:
            return Response(
                {"error": "Missing required fields"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current = data["current_location"]
        pickup = data["pickup_location"]
        dropoff = data["dropoff_location"]
        cycle_used = ceil_half_hour(float(data.get("cycle_used", 0)))

        driver_name = str(data.get("driver_name") or "").strip()[:255]
        log_date_inst = parse_log_date(data.get("log_date"))
        if log_date_inst is None:
            return Response(
                {"error": "Invalid or missing log_date (use YYYY-MM-DD)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        duty_hours, duty_time, ds_err = parse_duty_clock(
            data.get("duty_start_time"),
        )
        if ds_err:
            return Response(
                {"error": ds_err},
                status=status.HTTP_400_BAD_REQUEST,
            )
        duty_hours = float(duty_hours or 0)

        logger.info("Starting trip calculation")

        start_coords = resolve_location_payload(current)
        pickup_coords = resolve_location_payload(pickup)
        dropoff_coords = resolve_location_payload(dropoff)

        if not all([start_coords, pickup_coords, dropoff_coords]):
            return Response(
                {"error": "Geocoding failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        routing = get_route(start_coords, pickup_coords, dropoff_coords)

        if routing.route is None:
            return Response(
                {"error": routing.error_message or "Routing failed"},
                status=(
                    status.HTTP_400_BAD_REQUEST
                    if routing.client_error
                    else status.HTTP_502_BAD_GATEWAY
                ),
            )

        route = routing.route
        distance = route["distance"]
        legs = route.get("legs") or []
        if (
            isinstance(legs, list)
            and len(legs) >= 2
            and isinstance(legs[0], dict)
            and isinstance(legs[1], dict)
        ):
            drive_to_pickup = float(legs[0].get("duration") or 0)
            drive_after_pickup = float(legs[1].get("duration") or 0)
            d0 = ceil_half_hour(drive_to_pickup)
            d1 = ceil_half_hour(drive_after_pickup)
        else:
            d0 = 0.0
            d1 = ceil_half_hour(float(route.get("duration") or 0))
        duration = d0 + d1
        route["duration"] = duration

        fuel_stops = generate_stops_from_geometry(route["geometry"], distance)
        rest_stops = calculate_rest_stops(d0, d1)

        try:
            logs = generate_eld_logs(d0, d1, cycle_used, duty_hours)
        except ValueError as e:
            logger.warning("ELD scheduling invalid: %s", e)
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        annotate_calendar_dates(logs, log_date_inst)

        try:
            TripSubmission.objects.create(
                driver_name=driver_name,
                log_date=log_date_inst,
                duty_start=duty_time,
            )
        except Exception:
            logger.exception("Trip submission persistence failed")

        response = {
            "summary": {
                "total_distance_miles": round(distance, 1),
                "estimated_travel_hours": duration,
                "fuel_stops": len(fuel_stops),
                "rest_stops": len(rest_stops),
                "required_days": len(logs),
            },
            "route": route,
            "stops": {"fuel": fuel_stops, "rest": rest_stops},
            "logs": logs,
            "driver": persisted_driver_payload(
                driver_name, log_date_inst, duty_time
            ),
        }

        logger.info("Trip calculation completed successfully")

        return Response(response)

    except Exception:
        logger.exception("Trip planning failed")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
