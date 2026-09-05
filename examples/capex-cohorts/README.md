# Capex Cohorts

This example shows how you can model overlapping cohorts by nesting each depreciation schedule in an outer series. Each annual capex period creates its own two-year schedule, and the schedules are summed into total depreciation.

The basic pattern is to use `map_cells` to build one child series per source period, then `scan_cells` to carry the cohort rules forward into a rollup. Both operations preserve lazy evaluation, so the model can start from an infinite capex series.

## Building depreciation schedules

The capex series generates 100.0 of spend each year. Its query function uses day-based accrual to prorate values for partial periods.

```py
capex: Series[Period, float, Maybe[float]] = Series.unfold(
    "capex",
    by_days,
    seed=next(Period.seq(START, YEAR)),
    step=lambda period: (period, 100.0, period.from_end(YEAR)),
)
```
Each cohort starts when its source capex period ends and depreciates half the spend in each of the following two years. `build_cohort` creates the schedule with `Series.of` and uses the same accrual function for partial-period queries.

```py
type Cohort = Series[Period, float, Maybe[float]]
```

```py
def build_cohort(source_key: Period) -> Cohort:
    """Create a two-year depreciation schedule for a given capex period."""

    periods = list(Period.seq(source_key.end, YEAR, source_key.end + YEAR * 2))

    def depreciation() -> Effect[float]:
        spend = yield from get_at(capex, source_key)
        if isna(spend):
            raise ValueError(f"missing capex for {source_key}")
        return spend / 2

    return Series.of(
        f"Depreciation@{source_key.end}",
        by_days,
        [(period, Thunk(depreciation)) for period in periods],
    )
```
The `Thunk` defers reading capex until a depreciation value is requested. The `get_at` call keeps the dependency from each cohort value to its source spend.

The outer `cohort_schedules` series maps each capex key to a child schedule. `map_cells` receives the source key and cell rule without evaluating the spend. The outer series uses `exact` to look up a schedule by its original capex period; each child uses `by_days` to query depreciation amounts.

```py
cohort_schedules: Series[Period, Cohort, Maybe[Cohort]] = Series(
    "cohort_schedules",
    map_cells(
        "cohort_schedules",
        capex.cells,
        lambda source_key, _cell: build_cohort(source_key),
    ),
    exact,
)
```
## Rolling up cohorts

A total for one year needs several cohorts, so the rollup uses `scan_cells` to carry accumulated cohort rules from one period to the next. Its state is a tuple of rules, and each output is a deferred sum over that tuple.

```py
type CohortRules = tuple[Rule[Cohort], ...]
```

```py
def sum_cohorts(cohorts: CohortRules, period: Period) -> Effect[float]:
    total = 0.0
    for cell in cohorts:
        cohort = yield from get(cell)
        value = yield from get_at(cohort, period)
        if not isna(value):
            total += value
    return total


def rollup(
    prior: CohortRules,
    period: Period,
    current: Rule[Cohort],
) -> tuple[Thunk[float], CohortRules]:
    """Carry cohort rules forward without evaluating their schedules."""
    cohorts = (*prior, current)
    return Thunk(lambda: sum_cohorts(cohorts, period)), cohorts


total_depreciation: Series[Period, float, Maybe[float]] = Series(
    "total_depreciation",
    scan_cells(
        "total_depreciation",
        cohort_schedules.cells,
        seed=(),
        fn=rollup,
    ),
    by_days,
)
```
The source connection is explicit: `scan_cells` receives `cohort_schedules.cells`, and `sum_cohorts` receives the accumulated rules. Building the scan does not evaluate the schedules. Querying an annual total resolves each captured cohort and sums its answer, skipping `Na` for periods outside the schedule.

The total inherits the annual capex keys and uses `by_days` for partial-period queries. The first year has no depreciation; the next has 50.0 from one cohort; subsequent years have 100.0 from two overlapping cohorts. Expired cohort rules remain in the accumulator, so the stored history grows with the horizon.

## Querying the model

`Stmt` displays capex alongside the cohort breakdown. `Total` groups the displayed cohorts under the computed total; it does not calculate the sum itself.

```py
statement = Stmt(capex, Total(total_depreciation, cohorts))
print(fixed_width_table(statement.values_for_periods(ctx, years)))
```
Both the individual schedules and total depreciation support partial-period queries. The script queries through June 30, 2027, when only the first cohort has started depreciating, so its contribution equals the total.

## Run

```sh
uv run python examples/capex-cohorts/main.py
```

Output:

```txt
Start                                  2025-12-31  2026-12-31  2027-12-31  2028-12-31
End                        2025-12-31  2026-12-31  2027-12-31  2028-12-31  2029-12-31
capex                                      100.00      100.00      100.00      100.00
  Depreciation@2026-12-31                               50.00       50.00
  Depreciation@2027-12-31                                           50.00       50.00
  Depreciation@2028-12-31                                                       50.00
-------------------------------------------------------------------------------------
total_depreciation                           0.00       50.00      100.00      100.00

Capex @ partial Period(2025-12-31, 2027-06-30): 149.58904109589042
Total dep @ partial Period(2025-12-31, 2027-06-30): 24.794520547945208
First cohort @ partial Period(2025-12-31, 2027-06-30): 24.794520547945208
```
