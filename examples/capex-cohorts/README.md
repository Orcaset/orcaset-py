# Capex Cohorts

This example nests `Series` values. Each annual capex node maps to a two-year
depreciation series, and a second structural cell mapping rolls all eligible cohorts
into total depreciation.

The three layers are:

1. `capex`, an infinite annual series.
2. `cohort_schedules`, a `map_cells` transform over `capex.cells`.
3. `total_depreciation`, another `map_cells` transform that queries active schedules.

The child cells use `Thunk` to re-fetch their source capex. As a result, dependency
inspection retains the path from total depreciation through the cohort to source spend.

## Run

```sh
uv run python examples/capex-cohorts/main.py
```

The script prints annual and partial-period values plus representative dependency trees.
