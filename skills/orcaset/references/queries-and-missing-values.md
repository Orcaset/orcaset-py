# Queries and missing values

## Timeline and key domain

Use `Period` for interval flows and `date` for point-in-time balances or dated events. `Period(start, end)` is bounded by two dates with `start < end`. Keep a consistent convention; when financial periods roll on month end, preserve it:

```python
MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
periods = Period.seq(MODEL_START, MONTH)
```

If reporting boundaries are supplied, build periods from those exact dates. Do not replace a transaction date or fiscal boundary with a calendar boundary because the labels appear equivalent. Use `p.start` and `p.end` when linking period flows to dated balances.

`Period` uses a partial order: `a < b` only when `a` ends at or before `b` starts. Avoid `sorted`, `min`, and `max` over potentially overlapping periods. Every cell chain must nevertheless emit strictly ascending, non-overlapping keys.

## Query choice

| Desired behavior | Query |
| --- | --- |
| Exact key only; miss remains visible | `exact` |
| Latest value at or before a key | `last` |
| Adjacent period cells must exactly tile the query | `covered` |
| Overlapping period cells are weighted by a day-count function | `accrue(yf)` |
| Exact miss has a defined value | `exact_or(default)` |
| Pre-domain as-of miss has a defined value | `last_or(default)` |
| Accrual miss or any missing contributor has a defined value | `accrue_or(yf, fill)` |

`exact` and `last` work for any supported key type. `accrue`, `accrue_or`, and `covered` are for `Period` keys and float-like flows. An exact accrual hit returns the cell unchanged; otherwise each overlap is weighted by `yf(overlap) / yf(cell)`.

`YF.cmonthly` is appropriate for calendar-month interpolation. Use `YF.act360`, `YF.thirty360`, or a stated custom measure only when the model's convention calls for it. For actual-day weighting:

```python
by_days = accrue(lambda start, end: (end - start).days)
```

Do not aggregate ratios, rates, prices, or per-share measures as additive flows. Resolve the reporting-period numerator and denominator first, then calculate the ratio using the intended weighting convention.

## `Na` versus zero

`Na` means the model has no answer. `0.0` means the model has an answer and it is economically zero. Preserve `Na` by default.

Use `Na` for a missing required input, a gap in sourced history, an unsupported partial query, or any result whose prerequisites are incomplete. Use zero for an inactive flow, a known absent event, or an empty eligible aggregate whose economic identity is zero.

Apply defaults at the narrowest justified layer:

- `exact_or(0.0)` for dated event series where no event means zero;
- `last_or(opening)` when dates before the first observation have a defined opening value;
- `accrue_or(yf, 0.0)` when every failed accrual answer is defined as zero;
- `value_or(value, 0.0)` only at a formula edge where that contribution is explicitly optional;
- `isna(value)` plus a descriptive error when an input is required.

`ops.add`, `mul`, `sub`, and `div` propagate `Na` by default. Their `fill=` is per-source substitution and also applies outside every source domain; use it only when that exact behavior is intended. `add_some(())` and `multiply_some(())` return `Na` because no value seeds the fold.

Never replace `Na` with zero just to avoid an exception, satisfy a type checker, hide a broken dependency, or make a cycle converge.

## Boundaries and lazy walks

Query functions walk the chain only until ordering proves later nodes cannot matter. `last` retains only the latest candidate and does not force a superseded value. `accrue` and `covered` do not force cells outside the query. Preserve these properties in custom queries.

For each public series, test:

- an exact key;
- a supported partial or combined key;
- the first and last modeled boundary;
- a miss before and after the domain;
- any historical/forecast seam;
- both the value and whether it should be `Na`.

Record the accepted key type and query behavior for every export. A reporting adapter must not silently replace a date-keyed or period-keyed public contract. For terminal calculations, distinguish the final projected period, trailing twelve months, and next twelve months rather than reusing whichever value is convenient.
