# Cohort schedules

Use this pattern when each source item opens its own schedule: depreciation by capex vintage, amortization by issuance, customer cohorts, waterfalls, or other nested time profiles.

## Required shape

1. A source `Series` exposes origin items by key.
2. `map_cells` maps each source key to a child `Series` without forcing the source amount.
3. Child values re-fetch the originating source through `get_at` inside a `Thunk`.
4. An aggregate series walks eligible cohort cells, demands each child, and queries it at the reporting key.

The cohort collection should itself remain a `Series[K, Cohort, Maybe[Cohort]]`. Do not replace it with a dictionary, list, prebuilt output table, or cache.

## Build child schedules

Construct a child's domain from the source key, but defer its amounts:

```python
type Cohort = Series[Period, float, Maybe[float]]

def build_cohort(source_key: Period) -> Cohort:
    periods = Period.list(source_key.end, YEAR, source_key.end + YEAR * LIFE)

    def allocation() -> Effect[float]:
        amount = yield from get_at(capex, source_key)
        if isna(amount):
            raise ValueError(f"missing capex for {source_key}")
        return amount / LIFE

    return Series.of(
        f"Depreciation@{source_key.end}",
        exact,
        [(period, Thunk(allocation)) for period in periods],
    )

cohorts: Series[Period, Cohort, Maybe[Cohort]] = Series(
    "Depreciation cohorts",
    map_cells(
        "Depreciation cohorts",
        capex.cells,
        lambda source_key, _source_cell: build_cohort(source_key),
    ),
    exact,
)
```

The schedule convention, useful life, residual value, timing, and units must come from the requested economics. The child uses the source key to build structure, but retrieves the source amount only when a child value is queried.

## Aggregate cohorts

Walk the cohort chain only as far as the reporting key requires:

```python
def sum_cohorts(period: Period) -> Effect[float]:
    total = 0.0
    node = yield from get(cohorts.cells)
    while node is not None:
        if period < node.key:
            break
        cohort = yield from get(node.cell)
        amount = yield from get_at(cohort, period)
        if not isna(amount):
            total += amount
        node = yield from get(node.tail)
    return total
```

Create aggregate cells on the reporting spine with `map_cells`, returning a `Thunk(lambda: sum_cohorts(period))`. If the aggregate must be queryable before the first source cohort, choose a reporting chain that includes those keys; mapping only the cohort chain cannot advertise an earlier domain.

Returning `0.0` for no active cohorts is normally correct. An individual child should usually use `exact` and return `Na` outside its active schedule. Use an accrual query on the aggregate only when partial or combined reporting periods should interpolate its cells.

## Validation

Query the cohort collection at a source key and confirm that the answer is a child `Series`. Query a child before, during, and after its life. Query the aggregate with zero, one, and multiple active cohorts plus any supported partial period. Trace the aggregate to a child and from the child back to the originating source value. Walk keys separately to ensure doing so does not force source values.
