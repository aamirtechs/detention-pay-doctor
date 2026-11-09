# Good first issues

Seeded issues for new contributors. File each one on GitHub with the
`good first issue` and `help wanted` labels.

## 1. Support CSV input

Title: Accept a CSV file of loads

Description: Accept a CSV file with columns id, arrival, departure,
free_hours, rate_per_hour, billing_increment_minutes, cap_amount, so
dispatchers can feed a spreadsheet export directly. Empty cells mean
the field is absent and the CLI default applies.

Difficulty: Easy

Acceptance criteria: a CSV example file under examples/ computes the
same amounts as the equivalent JSON file; a test covers CSV input;
README documents the CSV columns.

## 2. Add a per-load detention summary table

Title: Print a compact summary table in text output

Description: After the per-load lines, print a compact table with
one row per load (id, wait, billable, amount) aligned in columns, so
the report is easy to paste into a broker email.

Difficulty: Easy

Acceptance criteria: text output contains the table with all loads;
amounts match the existing lines; JSON output is unchanged; a test
checks the table rows.

## 3. Support business-day free time windows

Title: Exclude nights and weekends from free time

Description: Add an optional flag (for example --free-window
09:00-17:00) so free time only counts inside a daily window, for
shippers whose docks close overnight. Time outside the window still
counts toward total wait, but free time is consumed only inside it.

Difficulty: Medium

Acceptance criteria: an overnight load with a daytime window computes
different billable hours than the wall-clock default; a test covers a
load spanning a closed night; README documents the flag and the rule.

## 4. Add invoice export

Title: Export a per-load invoice as CSV

Description: Add a --invoice-out flag that writes one CSV row per
load (id, arrival, departure, total wait, free time, billable hours,
rate, amount, capped) plus a totals row, ready to attach to an
invoice.

Difficulty: Easy

Acceptance criteria: the CSV rows match the text report amounts to
the cent; capped loads are marked; a test round-trips the export;
README documents the flag.
