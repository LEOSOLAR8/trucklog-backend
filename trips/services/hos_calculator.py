import math

MAX_DRIVE_HOURS = 11
MAX_DUTY_HOURS = 14
BREAK_AFTER_HOURS = 8
MANDATORY_BREAK_HOURS = 0.5
CYCLE_LIMIT = 70
CYCLE_DAYS = 8
RESET_HOURS = 34
RESET_DAY1_HOURS = 24
RESET_DAY2_HOURS = RESET_HOURS - RESET_DAY1_HOURS  # 10

PICKUP_DROPOFF_TIME = 1
PRE_TRIP_TIME = 0.5


def ceil_half_hour(hours):
    """Round hours up to the nearest 0.5h increment."""
    return math.ceil(max(0.0, float(hours)) * 2.0 - 1e-9) / 2.0


def generate_eld_logs(
    drive_to_pickup,
    drive_after_pickup,
    cycle_used,
    duty_start_hours=0.0,
):
    """
    Split route driving across days with simplified US property HOS:
    11h drive / 14h on-duty clock, 30m off-duty break after 8h driving,
    70h / 8-day cycle with 34h restart (split into 24h + 10h log days for UI).

    drive_to_pickup / drive_after_pickup: OSRM leg durations (current→pickup,
    pickup→dropoff). On-duty pickup (PICKUP_DROPOFF_TIME) is inserted only after
    all drive_to_pickup hours are consumed (arrival at pickup). If the 14h window
    fills first, pickup moves to the next calendar day.

    Day 1 begins with PRE_TRIP_TIME on-duty once.

    duty_start_hours: hours after midnight day 1 when on-duty timeline begins — prepends leading
    off-duty and trims the terminal off-duty slice so each day remains 24h on the sheet.
    Raises ValueError if duty_start_hours exceeds slack before terminal off-duty.
    """
    logs = []

    pending_leg1 = ceil_half_hour(drive_to_pickup)
    pending_leg2 = ceil_half_hour(drive_after_pickup)
    cycle_used = ceil_half_hour(cycle_used)
    day = 1

    cycle_history = []

    pickup_placed = False

    def place_pickup_if_due():
        nonlocal clock14, cycle_day, pickup_placed
        if pickup_placed:
            return
        if pending_leg1 > 1e-9:
            return
        segments.append(
            {
                "type": "on_duty",
                "hours": PICKUP_DROPOFF_TIME,
                "duty_kind": "pickup",
            }
        )
        clock14 += PICKUP_DROPOFF_TIME
        cycle_day += PICKUP_DROPOFF_TIME
        pickup_placed = True

    def try_place_pickup_after_leg1_drive():
        """Place pickup same day once leg-1 driving is done, if it fits in the 14h window."""
        nonlocal clock14, cycle_day, pickup_placed
        if pickup_placed or pending_leg1 > 1e-9:
            return
        if clock14 + PICKUP_DROPOFF_TIME > MAX_DUTY_HOURS + 1e-9:
            return
        place_pickup_if_due()

    while pending_leg1 > 1e-9 or pending_leg2 > 1e-9:
        clock14 = 0.0
        drive_today = 0.0
        cycle_day = 0.0
        segments = []

        if day == 1:
            segments.append(
                {
                    "type": "on_duty",
                    "hours": PRE_TRIP_TIME,
                    "duty_kind": "pretrip",
                }
            )
            clock14 += PRE_TRIP_TIME
            cycle_day += PRE_TRIP_TIME

        place_pickup_if_due()

        break_taken = False

        while (
            drive_today < MAX_DRIVE_HOURS
            and clock14 < MAX_DUTY_HOURS
            and (pending_leg1 > 1e-9 or pending_leg2 > 1e-9)
        ):
            # Do not drive toward drop-off until pickup on-duty is logged (leg-1 complete).
            if not pickup_placed and pending_leg1 <= 1e-9:
                break

            pool = pending_leg1 if pending_leg1 > 1e-9 else pending_leg2

            available_drive = min(
                MAX_DRIVE_HOURS - drive_today,
                pool,
                MAX_DUTY_HOURS - clock14,
            )

            if drive_today >= BREAK_AFTER_HOURS and not break_taken:
                segments.append({"type": "off_duty", "hours": MANDATORY_BREAK_HOURS})
                clock14 += MANDATORY_BREAK_HOURS
                break_taken = True
                continue

            drive_chunk = min(
                available_drive,
                (BREAK_AFTER_HOURS - drive_today) if not break_taken else available_drive,
            )
            if drive_chunk <= 0:
                break

            segments.append({"type": "driving", "hours": drive_chunk})

            drive_today += drive_chunk
            clock14 += drive_chunk
            cycle_day += drive_chunk
            if pending_leg1 > 1e-9:
                pending_leg1 -= drive_chunk
            else:
                pending_leg2 -= drive_chunk

            try_place_pickup_after_leg1_drive()

        if pending_leg1 <= 1e-9 and pending_leg2 <= 1e-9:
            segments.append(
                {
                    "type": "on_duty",
                    "hours": PICKUP_DROPOFF_TIME,
                    "duty_kind": "unload",
                }
            )
            clock14 += PICKUP_DROPOFF_TIME
            cycle_day += PICKUP_DROPOFF_TIME

        off_duty = max(0.0, 24 - clock14)

        ds = max(0.0, float(duty_start_hours)) if day == 1 else 0.0

        if day == 1 and ds > off_duty + 1e-6:
            raise ValueError(
                "duty_start leaves no room before midnight for this day's HOS totals"
            )

        segments.append({"type": "off_duty", "hours": off_duty})

        if day == 1 and ds > 1e-9:
            segments.insert(0, {"type": "off_duty", "hours": ds})
            terminal = segments[-1]
            if terminal.get("type") == "off_duty":
                terminal["hours"] = max(0.0, terminal["hours"] - ds)

        cycle_history.append(cycle_day)

        if len(cycle_history) > CYCLE_DAYS:
            cycle_history.pop(0)

        current_cycle_total = sum(cycle_history) + cycle_used

        logs.append(
            {
                "day": day,
                "segments": segments,
                "summary": {
                    "drive_hours": ceil_half_hour(drive_today),
                    "duty_hours": ceil_half_hour(clock14),
                    "cycle_total": ceil_half_hour(current_cycle_total),
                },
            }
        )

        if current_cycle_total >= CYCLE_LIMIT:
            cycle_history = []
            cycle_used = 0
            day += 1
            logs.append(
                {
                    "day": day,
                    "segments": [{"type": "off_duty", "hours": RESET_DAY1_HOURS}],
                    "note": "34-hour reset",
                }
            )
            day += 1
            logs.append(
                {
                    "day": day,
                    "segments": [{"type": "off_duty", "hours": RESET_DAY2_HOURS}],
                    "note": "34-hour reset (continued)",
                }
            )

        day += 1

    return logs
