# Cohort schedules

Use this pattern when every source item opens its own schedule: depreciation
by capex vintage, amortization by issuance, customer cohorts, waterfalls, or
other nested time profiles.

## Required shape

1. A source series exposes spend or origin items by key.
2. A `MapItemsSeries` lazily maps each source key to a child Orcaset `Series`.
3. Each child schedule re-fetches its originating source value with `get_at`
   when its cells resolve.
4. A second Orcaset mapping or cell stream queries eligible child schedules and
   aggregates their answers.

The exported cohort collection itself should be the `MapItemsSeries`. Do not
export a dict, list, tuple, `Replayable`, cached function, or module-level cache
of prebuilt child series. Those forms lose the expected series identity,
nested queries, lazy construction, and dependency graph.

## Child construction

The mapping function receives both the source key and source series. Build the
child series structure from the key, but resolve its amount only inside child
factories:

```python
type Cohort = Series[Period, Period, float, Maybe[float]]

def build_schedule(
    source_key: Period,
    source: BaseSeries[Period, Period, Maybe[float]],
) -> Cohort:
    def cells() -> Iterator[tuple[Period, CellFactory[float]]]:
        for period in schedule_periods(source_key):
            def factory(p: Period = period) -> Step[float]:
                amount = yield from get_at(source, source_key)
                if isna(amount):
                    raise ValueError(f"missing source amount for {source_key}")
                return allocate(amount, p)

            yield period, factory

    return Series(f"Schedule@{source_key}", cells, exact)

cohort_schedules = MapItemsSeries(
    "Cohort schedules",
    source_items,
    build_schedule,
    exact,
)
```

The example is intentionally policy-neutral: `schedule_periods` and
`allocate` should reflect useful life, convention, residual value, timing, and
units required by the model.

## Aggregate schedules

An aggregate should demand the cohort domain, each eligible cohort, and each
cohort answer:

```python
def total_at(
    query_period: Period,
    source: BaseSeries[Period, Period, Maybe[Cohort]],
) -> Step[float]:
    total = 0.0
    keys = yield from get(source.keys())
    for source_key in keys:
        if source_key.end > query_period.end:
            break
        schedule = yield from get_at(source, source_key)
        if isna(schedule):
            continue
        amount = yield from get_at(schedule, query_period)
        if not isna(amount):
            total += amount
    return total
```

Returning `0.0` for an empty aggregate is normally correct because no active
cohort contributes. An individual detail schedule should normally use `exact`
and return `Na` outside its active cells. Apply an `accrual` day measure to the
aggregate if combined or partial-period totals must interpolate.

The aggregate's public domain must include every reporting/source period where
the total is queryable, including periods before the first cohort becomes
active. A factory that starts only at the first depreciation or amortization
period will return `Na` instead of the required zero for the initial empty
aggregate. Mapping across the source/reporting spine and initializing each
eligible sum at `0.0` avoids that gap.

## Validation

Query the exported mapping for a source key and confirm the result is a child
series. Query that child inside, before, and after its schedule. Query the
aggregate with zero, one, and overlapping active cohorts plus a partial period.
Trace the aggregate to the child and then to the originating source amount.
