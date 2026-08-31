# Queries and missing values

## Timeline and key domain

`Period(start, end)` represents a half-open economic interval bounded by the
two dates. Use a consistent convention. When financial periods roll on month
end, preserve month end explicitly:

```python
MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
periods = Period.seq(MODEL_START, MONTH)
```

When a task explicitly rolls on another date, preserve that anchor instead.
If reporting dates are provided, construct periods directly from adjacent
dates, such as `Period(dates[i], dates[i + 1])`; do not replace a year-end or
transaction-date boundary with January 1 merely because both describe the
same labeled year.
Use `p.start` and `p.end` to connect period flows to dated balances. Do not
query a `DateSeries` with a `Period` or a `PeriodSeries` with a `date`.
Balances that must answer between roll dates normally use `last`. Use `exact`
for event detail where a non-event date is undefined; use `exact_or(0.0)` for
an event cash-flow line where no event on a queried date economically means
zero.

## Query choice

| Desired behavior | Query |
| --- | --- |
| Exact period/date only; miss remains visible | `exact` |
| Latest value at or before a date/key | `last` |
| Complete adjacent cells only; partial cell is undefined | `covered` |
| Weight overlapping flow cells by a day-count function | `accrual(yf)` |
| Same behavior but a miss is economically a concrete value | `exact_or(default)` / `accrual_or(yf, default)` |

`YF.cmonthly` is appropriate for calendar-month interpolation. Use
`YF.act360`, `YF.thirty360`, or a stated custom day measure only when the
model's convention requires it. For actual-day weighting:

```python
by_days = accrual(lambda start, end: (end - start).days)
```

Do not model ratios, rates, prices, or per-share measures as additive flows.
Resolve the reporting-period numerator and denominator first, then calculate
the ratio using the intended weighting convention.

## `Na` versus zero

`Na` means the model has no answer for this query. `0.0` means the model has an
answer and that answer is economically zero. Preserve `Na` by default.

Use `Na` for:

- a required input that is absent;
- an unsupported, misaligned, or out-of-domain detail query;
- a gap in sourced history;
- a wrong key type or boundary;
- a calculation whose prerequisites are incomplete.

Use `0.0` for:

- an empty sum whose mathematical and economic identity is zero;
- a flow explicitly defined as inactive outside its schedule;
- an optional event known not to occur at the queried key;
- a series whose contract deliberately answers zero on every miss.

This distinction can differ by layer. A depreciation cohort queried outside
its own active schedule should usually answer `Na`, while total depreciation
with no active cohorts should answer `0.0`.

Choose the policy at the narrowest justified layer:

- `exact_or(0.0)` or `accrual_or(yf, 0.0)` when every miss for that series is
  defined as zero.
- `value_or(value, 0.0)` only at a formula edge where that particular missing
  contribution is explicitly optional.
- `isna(value)` plus a descriptive error when an input is required.
- Initialize an aggregate at `0.0` when an empty eligible set is a valid zero;
  `add_some(())` intentionally returns `Na` because it has no seed value.

Never substitute zero merely to avoid an exception, satisfy a type checker,
hide a broken dependency, or force a circular model to run.

## Boundary probes

For each series, test an exact key, a partial or combined query when supported,
the first and last modeled boundary, a miss before/after the domain, and any
historical/forecast seam. Assert both the value and whether the result should
be `Na`.

Test the public export itself, not only a statement or an internal adapter. A
date-keyed event may have a period-keyed reporting adapter, but that adapter
must not replace an export whose contract accepts `date`. Include a small
contract table or smoke test that records every exported name, accepted key
type, query behavior, and representative answer.

For terminal or forward calculations, state the measurement window explicitly.
The final projected period, trailing-twelve-month value, and next-twelve-month
value are different queries. If a terminal multiple applies to NTM, project or
demand the next period rather than silently reusing the last in-horizon period.
