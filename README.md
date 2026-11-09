# detention-pay-doctor
**Live tool:** https://aamirtechs.github.io/detention-pay-doctor/ (runs in your browser, no install)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/detention-pay-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/detention-pay-doctor/issues)

A zero-dependency Python CLI that computes detention pay for truck
loads from arrival and departure timestamps: time beyond free time,
rounded up to the billing increment, capped when a cap is given.

Detention disputes usually come down to arithmetic: how long the
truck waited, how much of that was free, and how the remainder was
rounded. This tool makes that arithmetic explicit, per load, with
totals a dispatcher can paste into an invoice or a broker email.

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard
library.

```bash
pip install detention-pay-doctor
```

Or run it straight from the source checkout:

```bash
python3 detention_pay_doctor.py examples/loads.json
```

## Input format

A JSON list, or an object with a `loads` list. Each load needs an
`id` (or `load_id`), an arrival time, and a departure time.
Optional per-load fields: `free_hours` (also accepted as
`free_time_hours`), `rate_per_hour` (also accepted as `rate`),
`billing_increment_minutes` (also accepted as `billing_increment`
or `increment_minutes`), and `cap_amount` (also accepted as `cap`).
Per-load values win over the CLI defaults.

Times accept ISO timestamps, with or without a trailing `Z` or an
offset:

```json
[
  {"id": "L-101", "arrival": "2026-11-02T08:00:00",
   "departure": "2026-11-02T09:30:00", "free_hours": 2,
   "rate_per_hour": 75, "billing_increment_minutes": 15},
  {"id": "L-102", "arrival": "2026-11-02T08:00:00",
   "departure": "2026-11-02T11:10:00", "free_hours": 2,
   "rate_per_hour": 75, "billing_increment_minutes": 15}
]
```

Date+time pairs work too, for exports that split the columns:

```json
[
  {"id": "L-301", "arrival_date": "2026-11-02", "arrival_time": "08:00",
   "departure_date": "2026-11-03", "departure_time": "02:00"}
]
```

## How the math works

1. Total wait is departure minus arrival, in minutes.
2. Billable time is the wait beyond free time. At or under free
   time, billable time is zero.
3. Billable time rounds UP to the billing increment. A 70 minute
   excess at a 15 minute increment bills as 75 minutes.
4. Amount is billable hours times rate, rounded to cents (half up).
5. If a cap is given and the amount exceeds it, the amount is the
   cap, and the load is marked `(capped)`. Billable hours still show
   the uncapped figure, so the cap is visible, not hidden.

Overnight waits need no special flag: a departure on the next
calendar day is just a later timestamp, so the same subtraction
covers it.

## Usage

```bash
python3 detention_pay_doctor.py examples/loads.json
```

Captured output:

```
L-101: arrival 2026-11-02T08:00:00, departure 2026-11-02T09:30:00, wait 1.50 h, free 2.00 h, billable 0.00 h, $0.00
L-102: arrival 2026-11-02T08:00:00, departure 2026-11-02T11:10:00, wait 3.17 h, free 2.00 h, billable 1.25 h, $93.75
L-103: arrival 2026-11-02T22:00:00, departure 2026-11-03T06:30:00, wait 8.50 h, free 2.00 h, billable 6.50 h, $487.50
L-104: arrival 2026-11-02T07:00:00, departure 2026-11-02T19:00:00, wait 12.00 h, free 2.00 h, billable 10.00 h, $300.00 (capped)

Loads: 4, total wait 25.17 h, total billable 17.75 h, total amount $881.25
```

L-101 waited 1.50 hours, inside its 2 free hours, so it pays
nothing. L-102 waited 3 hours 10 minutes, 70 minutes past free time,
rounded up to 75 minutes (1.25 hours at $75, $93.75). L-103 is the
overnight case: 22:00 to 06:30 the next day is 8.50 hours, 6.50
billable, $487.50. L-104 would bill 10 hours at $75 ($750) but its
$300 cap applies, so it pays $300.00 and is marked capped.

CLI defaults apply to loads that omit the matching field:

```bash
python3 detention_pay_doctor.py examples/minimal.json
```

Captured output:

```
L-301: arrival 2026-11-02T08:00:00, departure 2026-11-02T11:10:00, wait 3.17 h, free 2.00 h, billable 1.25 h, $93.75

Loads: 1, total wait 3.17 h, total billable 1.25 h, total amount $93.75
```

Overriding the defaults changes the same load:

```bash
python3 detention_pay_doctor.py examples/minimal.json --free-hours 1 --rate 100 --increment 30
```

Captured output:

```
L-301: arrival 2026-11-02T08:00:00, departure 2026-11-02T11:10:00, wait 3.17 h, free 1.00 h, billable 2.50 h, $250.00

Loads: 1, total wait 3.17 h, total billable 2.50 h, total amount $250.00
```

And a CLI cap caps the same load:

```bash
python3 detention_pay_doctor.py examples/minimal.json --cap 50
```

Captured output:

```
L-301: arrival 2026-11-02T08:00:00, departure 2026-11-02T11:10:00, wait 3.17 h, free 2.00 h, billable 1.25 h, $50.00 (capped)

Loads: 1, total wait 3.17 h, total billable 1.25 h, total amount $50.00
```

Use it as a CI gate: `--check` exits 1 when any load has missing or
invalid data, and 0 otherwise. On the clean example it exits 0:

```bash
python3 detention_pay_doctor.py examples/loads.json --check
```

On `examples/bad-loads.json`, which has one load missing its
departure and one load departing before it arrives, it exits 1:

```
Loads: 0, total wait 0.00 h, total billable 0.00 h, total amount $0.00
ERROR: load L-201: missing departure time
ERROR: load L-202: departure 2026-11-02T07:00:00 is before arrival 2026-11-02T08:00:00
```

Bad loads never stop the report: valid loads still compute, and
every problem is listed as an ERROR line. `--json` emits the full
report (per-load records, totals, and errors) as JSON, and `--out`
writes the report to a file.

## Options

| Flag | Meaning |
| --- | --- |
| `--free-hours` | Default free time in hours (default: 2) |
| `--rate` | Default rate per hour in dollars (default: 75) |
| `--increment` | Default billing increment in minutes (default: 15) |
| `--cap` | Default cap amount in dollars (default: none) |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any load has missing or invalid data |
| `--out` | Write the report to a file |

## Edge cases

* Wait exactly equal to free time pays $0.00. Only time beyond
  free time bills.
* An excess that lands exactly on an increment boundary is not
  rounded up further. 60 minutes past free time at a 15 minute
  increment bills as 60 minutes.
* Departure before arrival, a missing id, arrival, or departure, an
  unparseable timestamp, or a negative free time, rate, or cap is an
  error for that load, not a crash. See the `--check` example above.
* Money uses Decimal math and rounds to cents half up, so a $33.335
  hourly rate over one billable hour yields $33.34.
* Timezone offsets are accepted, but arrival and departure should
  use the same convention within a file. A `Z` suffix and a plain
  local time mix only if that is what the export actually contains.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

26 tests, all passing: free time not exceeded, partial increment
rounding up, cap applied, overnight waits, date+time pairs, cents
rounding, invalid and missing data handling, JSON output shape, and
`--check` exit codes.

## License

MIT. See [LICENSE](LICENSE).
