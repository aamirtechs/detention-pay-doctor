# Changelog

## 1.0.0 - 2026-11-04

Initial release.

* Detention pay per load: time beyond free time, rounded up to the
  billing increment, capped when a cap is given.
* Overnight waits handled naturally through timestamps, including
  departures on the next calendar day.
* ISO timestamps plus date+time pairs (arrival_date with
  arrival_time, departure_date with departure_time).
* Per-load overrides for free hours, rate, billing increment, and
  cap, with CLI defaults via --free-hours, --rate, --increment,
  and --cap.
* Decimal money math with cents rounding (half up).
* Text and --json output, --out file output, and a --check CI gate
  that exits 1 when any load has missing or invalid data.
* Zero dependencies, Python 3.10 or newer.
