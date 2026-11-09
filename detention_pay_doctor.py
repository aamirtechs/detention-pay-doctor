"""Detention pay calculator for truck loads.

Reads a JSON file describing loads, computes billable detention time
beyond free time, rounded up to the billing increment and capped when
a cap is given, and prints a per-load report with totals.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 detention_pay_doctor.py examples/loads.json
    python3 detention_pay_doctor.py loads.json --json --check
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

__version__ = "1.0.0"

CENT = Decimal("0.01")
DEFAULT_FREE_HOURS = Decimal("2")
DEFAULT_RATE = Decimal("75")
DEFAULT_INCREMENT_MINUTES = 15


class LoadError(Exception):
    """A load entry that cannot be computed."""


def parse_timestamp(value):
    """Parse an ISO timestamp string into a datetime.

    Accepts a trailing Z, an explicit offset, and plain
    "YYYY-MM-DD HH:MM" or "YYYY-MM-DDTHH:MM" forms. Naive values are
    used as given, so arrival and departure in the same file compare
    directly. Raises ValueError on anything unparseable.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is empty")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError("unparseable timestamp: %r" % value)


def resolve_time(load, prefix):
    """Resolve one endpoint (arrival or departure) for a load.

    Accepts, in order: a plain ISO string under the prefix key, a
    date+time pair under "<prefix>_date" and "<prefix>_time", or a
    dict under the prefix key with "date" and "time" (or "datetime")
    keys. Returns None when nothing usable is present.
    """
    direct = load.get(prefix)
    if isinstance(direct, str) and direct.strip():
        return parse_timestamp(direct)
    if isinstance(direct, dict):
        if direct.get("datetime"):
            return parse_timestamp(direct["datetime"])
        if direct.get("date") and direct.get("time"):
            return parse_timestamp("%s %s" % (direct["date"], direct["time"]))
        raise ValueError("%s object needs datetime or date plus time" % prefix)
    date_part = load.get(prefix + "_date")
    time_part = load.get(prefix + "_time")
    if date_part and time_part:
        return parse_timestamp("%s %s" % (date_part, time_part))
    return None


def to_decimal(value, field):
    """Convert a JSON number or numeric string to Decimal."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise LoadError("%s is not a number: %r" % (field, value))
    if result.is_nan() or result.is_infinite():
        raise LoadError("%s is not a finite number: %r" % (field, value))
    return result


def compute_load(load, defaults):
    """Compute one load. Returns a dict, or raises LoadError."""
    load_id = load.get("id", load.get("load_id"))
    if not load_id:
        raise LoadError("missing load id")
    if not isinstance(load, dict):
        raise LoadError("load entry is not an object")
    try:
        arrival = resolve_time(load, "arrival")
    except ValueError as exc:
        raise LoadError("load %s: %s" % (load_id, exc))
    try:
        departure = resolve_time(load, "departure")
    except ValueError as exc:
        raise LoadError("load %s: %s" % (load_id, exc))
    if arrival is None:
        raise LoadError("load %s: missing arrival time" % load_id)
    if departure is None:
        raise LoadError("load %s: missing departure time" % load_id)
    if departure < arrival:
        raise LoadError(
            "load %s: departure %s is before arrival %s"
            % (load_id, departure.isoformat(), arrival.isoformat()))

    free_hours = defaults["free_hours"]
    if load.get("free_hours") is not None:
        free_hours = to_decimal(load["free_hours"], "free_hours")
    elif load.get("free_time_hours") is not None:
        free_hours = to_decimal(load["free_time_hours"], "free_time_hours")
    rate = defaults["rate"]
    if load.get("rate") is not None:
        rate = to_decimal(load["rate"], "rate")
    elif load.get("rate_per_hour") is not None:
        rate = to_decimal(load["rate_per_hour"], "rate_per_hour")
    increment = defaults["increment"]
    if load.get("increment_minutes") is not None:
        increment = to_decimal(load["increment_minutes"], "increment_minutes")
    elif load.get("billing_increment") is not None:
        increment = to_decimal(load["billing_increment"], "billing_increment")
    elif load.get("billing_increment_minutes") is not None:
        increment = to_decimal(
            load["billing_increment_minutes"], "billing_increment_minutes")
    cap = defaults["cap"]
    if load.get("cap") is not None:
        cap = to_decimal(load["cap"], "cap")
    elif load.get("cap_amount") is not None:
        cap = to_decimal(load["cap_amount"], "cap_amount")

    if free_hours < 0:
        raise LoadError("load %s: free_hours is negative" % load_id)
    if rate < 0:
        raise LoadError("load %s: rate is negative" % load_id)
    if increment <= 0:
        raise LoadError("load %s: billing increment must be positive" % load_id)
    if cap is not None and cap < 0:
        raise LoadError("load %s: cap is negative" % load_id)

    wait_seconds = Decimal(str((departure - arrival).total_seconds()))
    wait_minutes = wait_seconds / Decimal(60)
    wait_hours = wait_minutes / Decimal(60)
    free_minutes = free_hours * Decimal(60)
    excess_minutes = wait_minutes - free_minutes
    if excess_minutes <= 0:
        billable_minutes = Decimal(0)
    else:
        steps = math.ceil(excess_minutes / increment)
        billable_minutes = Decimal(steps) * increment
    billable_hours = billable_minutes / Decimal(60)
    amount = (billable_hours * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    capped = False
    if cap is not None and amount > cap:
        amount = cap.quantize(CENT, rounding=ROUND_HALF_UP)
        capped = True

    return {
        "id": str(load_id),
        "arrival": arrival.isoformat(),
        "departure": departure.isoformat(),
        "total_wait_hours": float(wait_hours),
        "free_hours": float(free_hours),
        "billable_minutes": float(billable_minutes),
        "billable_hours": float(billable_hours),
        "rate_per_hour": float(rate),
        "amount": float(amount),
        "capped": capped,
    }


def load_entries(path):
    """Load the JSON file. Returns a list of load objects."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("loads", "entries", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    raise LoadError("input must be a JSON list or an object with a loads list")


def build_report(entries, defaults):
    """Compute every load, collecting errors instead of stopping."""
    loads = []
    errors = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("load entry is not an object: %r" % (entry,))
            continue
        try:
            loads.append(compute_load(entry, defaults))
        except LoadError as exc:
            errors.append(str(exc))
    total_wait = sum(
        (Decimal(str(item["total_wait_hours"])) for item in loads),
        Decimal(0))
    total_billable = sum(
        (Decimal(str(item["billable_hours"])) for item in loads),
        Decimal(0))
    total_amount = sum(
        (Decimal(str(item["amount"])) for item in loads),
        Decimal(0))
    return {
        "loads": loads,
        "totals": {
            "loads": len(loads),
            "total_wait_hours": float(total_wait),
            "total_billable_hours": float(total_billable),
            "total_amount": float(
                total_amount.quantize(CENT, rounding=ROUND_HALF_UP)),
        },
        "errors": errors,
    }


def format_text(report):
    """Render the report as plain text."""
    lines = []
    for item in report["loads"]:
        capped = " (capped)" if item["capped"] else ""
        lines.append(
            "%s: arrival %s, departure %s, wait %.2f h, free %.2f h, "
            "billable %.2f h, $%.2f%s"
            % (item["id"], item["arrival"], item["departure"],
               item["total_wait_hours"], item["free_hours"],
               item["billable_hours"], item["amount"], capped))
    lines.append("")
    totals = report["totals"]
    lines.append(
        "Loads: %d, total wait %.2f h, total billable %.2f h, "
        "total amount $%.2f"
        % (totals["loads"], totals["total_wait_hours"],
           totals["total_billable_hours"], totals["total_amount"]))
    for error in report["errors"]:
        lines.append("ERROR: %s" % error)
    return "\n".join(lines) + "\n"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="detention-pay-doctor",
        description="Compute detention pay for truck loads from "
        "arrival and departure timestamps.")
    parser.add_argument("input", help="JSON file describing loads")
    parser.add_argument("--free-hours", type=Decimal,
                        default=DEFAULT_FREE_HOURS,
                        help="default free time in hours (default: 2)")
    parser.add_argument("--rate", type=Decimal, default=DEFAULT_RATE,
                        help="default rate per hour in dollars (default: 75)")
    parser.add_argument("--increment", type=Decimal,
                        default=Decimal(DEFAULT_INCREMENT_MINUTES),
                        help="default billing increment in minutes (default: 15)")
    parser.add_argument("--cap", type=Decimal, default=None,
                        help="default cap amount in dollars (default: none)")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any load has missing or invalid data")
    parser.add_argument("--out", default=None,
                        help="write the report to a file")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    defaults = {
        "free_hours": args.free_hours,
        "rate": args.rate,
        "increment": args.increment,
        "cap": args.cap,
    }
    try:
        entries = load_entries(args.input)
    except (OSError, ValueError, LoadError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    report = build_report(entries, defaults)
    if args.json:
        text = json.dumps(report, indent=2) + "\n"
    else:
        text = format_text(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")
    if args.check and report["errors"]:
        return 1
    return 0


def main_entry():
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
