# Capex Cohorts

This example complex series values by nesting `Series` in `Series`. Every annual capex cell creates its own two-year depreciation schedule, and a second mapping aggregates all active schedules into total depreciation.

## How It Works

The model has three layers:

1. `capex` produces one spend value for each annual period.
2. `cohort_schedules` maps every spend period to a child `Series`. Each child re-fetches its source capex and depreciates it evenly over two years.
3. `total_depreciation` visits the eligible child schedules and sums their answers for the requested period.

The `cohort_schedules` series nests the cohort depreciation detail as its values.

```txt
cohort_schedules: [
   2026 capex depreciation detail: [(2027, 50), (2028, 50)],
   2027 capex depreciation detail: [(2028, 50), (2029, 50)],
   ...
]
```

Because the cohort is itself a series value, orcaset retains the dependencies from total depreciation through the child schedule to the originating capex cell. The example prints those dependency graphs as well as annual and partial-period values.

## Run

From the repository root:

```sh
uv run python examples/capex-cohorts/main.py
```

The script prints the output below which includes the line items structured in a tabular format, value queries, and calculation dependency tree detail.

```txt
Period end              2026-12-31  2027-12-31  2028-12-31  2029-12-31

Capex                        100.0       100.0       100.0       100.0

Depreciation@2026-12-31        0.0        50.0        50.0         0.0
Depreciation@2027-12-31        0.0         0.0        50.0        50.0
Depreciation@2028-12-31        0.0         0.0         0.0        50.0

Total depreciation             0.0        50.0       100.0       100.0

Capex @ partial Period(2025-12-31, 2027-06-30): 149.58904109589042
Total dep @ partial Period(2025-12-31, 2027-06-30): 24.794520547945208

Deps: Depreciation@2026-12-31 @ Period(2026-12-31, 2027-12-31)

Depreciation@2026-12-31@Period(2026-12-31, 2027-12-31) = 50.0
  Depreciation@2026-12-31.cells = <orcaset.series.Replayable object at 0x105c9da90>
  Depreciation@2026-12-31@Period(2026-12-31, 2027-12-31) = 50.0
    capex@Period(2025-12-31, 2026-12-31) = 100.0
      capex.cells = <orcaset.series.Replayable object at 0x105c5d7f0>
      capex@Period(2025-12-31, 2026-12-31) = 100.0

Deps: total_depreciation @ Period(2027-12-31, 2028-12-31)

total_depreciation@Period(2027-12-31, 2028-12-31) = 100.0
  total_depreciation.cells = <orcaset.series.Replayable object at 0x105c95d90>
    capex.keys = <orcaset.series._KeyProj object at 0x105c5d940>
      capex.cells = <orcaset.series.Replayable object at 0x105c5d7f0>
      ...
```

## Layout

| File | Role |
| --- | --- |
| [`main.py`](main.py) | Defines capex, builds per-spend depreciation cohorts, rolls them up, and inspects their dependencies. |
