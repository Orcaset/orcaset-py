# Orcaset modeling patterns

Each section is an independent model example. Keep evaluation, report horizons, and outputs separate as described in [core.md](core.md). Read assumptions through `get` and other line items through `get_at` so their dependencies remain visible. Use [verification.md](verification.md) to check values, boundaries, and dependency paths.

## Constant periodic value

Use this pattern to define a series with a constant value at periodic keys.

Keep the amount in a `Val` so scenarios can change it without rewriting the series. The step returns the current key, its value, and the next state. The query function determines how those cells answer other intervals.

Use variable names that make the time period associated with a value clear (e.g. `monthly_amt`, `annual_amt`, etc).

Define periods based on their natural model frequency and let the series' `query` function handle partial period interpolation and aggregation.

```py
from datetime import date
from dateutil.relativedelta import relativedelta
from orcaset import YF, Effect, Period, Series, Val, get, query

opening = date(2025, 12, 31)
month = relativedelta(months=1, day=31)
first_month = Period(opening, opening + month)
monthly_amt = Val(2.0, name="Monthly amount")


@Series.define(query.accrue(YF.cmonthly), seed=first_month, name="Line A")
def line_a(period: Period) -> Effect[tuple[Period, float, Period]]:
    amount = yield from get(monthly_amt)
    return period, amount, period.from_end(month)
```

Do not end an ongoing series at the report horizon. A genuine contractual end belongs in the model; a finite list of reporting periods belongs in the output code.

## Recursively growing value

Use this pattern to define a series that grows periodically at some rate.

This example uses an annualized initial value, but it is not necessary to annualize initial values if they are naturally defined by a different period.

```py
import math
from datetime import date
from dateutil.relativedelta import relativedelta
from orcaset import YF, Effect, Period, Series, Val, get, get_at, isna, query

opening = date(2025, 12, 31)
quarter = relativedelta(months=3, day=31)
first_quarter = Period(opening, opening + quarter)
initial_annualized_amt = Val(200.0, name="Initial annualized amount")
annual_growth = Val(0.01, name="Annual growth")


@Series.define(query.accrue(YF.cmonthly), seed=first_quarter, name="Line A")
def line_a(period: Period) -> Effect[tuple[Period, float, Period]]:
    if period == first_quarter:
        annual = yield from get(initial_annualized_amt)
        amount = annual * YF.cmonthly(*period)
    else:
        prior = yield from get_at(line_a, period.from_start(-quarter))
        if isna(prior):
            raise ValueError(f"Missing prior-quarter amount for {period}")
        rate = yield from get(annual_growth)
        amount = prior * math.pow(1.0 + rate, YF.cmonthly(*period))
    return period, amount, period.from_end(quarter)
```

- The initial branch matches equality on the full period (not period end or period ordering).
- Use `math.pow` rather than the `**` operator to preserve strong value typing; `**` explicitly returns `Any` which erases the return type.
- Normalize the growth rate with `YF` rather than explicit division or multiplication against a scalar so that new period durations automatically get the right year fraction. Use `YF.cmonthly` to model 12 equal calendar months.

## Extending a series

Use `Series.flatten` when joining segments that have their own query policies, such as non-interpolated actuals followed by interpolated projections. The outer chain contains **series**, keyed by integer position; its keys specify component order, not dates.

```py
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Chain,
    Cons,
    Effect,
    Maybe,
    Na,
    Period,
    Series,
    Val,
    continue_series,
    get,
    get_at,
    maybe,
    of_cells,
    period_split,
    query,
)

month = relativedelta(months=1, day=31)
q3 = Period(date(2025, 6, 30), date(2025, 9, 30))
october = q3.from_end(month)
november = october.from_end(month)
december = november.from_end(month)
annual_terminal_growth = Val(0.02, name="Annual terminal growth")

actuals = Series.of(query.covered, pairs=[(q3, 300.0)], name="Actuals")
projections = Series.of(
    query.accrue(YF.cmonthly),
    pairs=[(q3, 0.0), (october, 110.0), (november, Na), (december, 121.0)],
    name="Projections",
)

type Segment = Series[Period, Any, Maybe[float]]

components: Chain[int, Segment] = of_cells(
    [(0, actuals), (1, projections)], name="Revenue components"
)
base = Series.flatten(
    components,
    query=query.covered,
    split_keys=period_split,
    name="Actuals and projections",
)
```

`Any` here acts as an existential type, as permitted by [core.md](core.md): each component is a `Series[Period, V, Maybe[float]]` for some hidden raw cell type `V`, which may differ between components. Python's `Any` approximates that existential type; it is not a native existential type construct. Keep it confined to this hidden cell-type parameter: component keys remain `Period`, and query answers remain `Maybe[float]`. Flattening consumes those typed **query answers**, not the hidden raw values, so its output cells need no `Any`.

Flattening delegates a query wholly within a segment to that segment. For a query crossing a seam, it splits the interval with `period_split` and uses the supplied `query` to combine the segment answers. `query.covered` sums those answers and propagates `Na`.

- Earlier components retain their domain through their last key. The overlapping Q3 projection is clipped, so Q3 actuals remain `300.0`.
- Partial actuals remain `Na`, even if the interval also crosses into an interpolating projection segment.
- November remains missing. Flattening supplies no zero-fill or fallback for missing cells; queries in gaps follow the owning component's query policy.
- An infinite component prevents later components from being reached.

To add a forecast that starts after the finite base ends, continue the same example with `continue_series`. Its callback receives the last node of `base.walk()`, whose value is the base's answer at its last key, or `None` for an empty base, and constructs the next segment only when needed. It returns the next segment, or `None` to end the chain after the base.

```py
def terminal_revenue(
    last_node: Cons[Period, Maybe[float]] | None,
) -> Series[Period, Maybe[float], Maybe[float]] | None:
    if last_node is None:
        return None  # Nothing to grow from: end after the empty base.

    @Series.define(query.accrue(YF.cmonthly), seed=last_node.key, name="Terminal growth")
    def growth(prior_period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
        period = prior_period.from_end(month)
        prior = yield from get_at(revenue, prior_period)
        rate = yield from get(annual_terminal_growth)
        amount = maybe.mul_some(prior, 1.0 + rate * YF.cmonthly(*period))
        return period, amount, period

    return growth


revenue = Series.flatten(
    continue_series(base, terminal_revenue, name="Revenue continuation"),
    query=query.covered,
    split_keys=period_split,
    name="Revenue",
)
```

The continuation's state is the prior period; its emitted key is the next period. This avoids duplicating the terminal base key. Its reference to the combined `revenue` is resolved lazily, so January can depend on December's projection. This example follows the extend-series example's simple prorated growth: January is `121 * (1 + 0.02 / 12)`. The callback and nested series are part of the lazy continuation mechanism, not a generic builder for unrelated line items.

Pass several continuations to build several segments in one call: `continue_series(base, renewal, reabsorption)`. Each receives the last walk node of the segments before it (an empty segment passes on the node before it), and a continuation returning `None` ends the chain there, so later ones are never called.

Do not exhaust the base to find its last value before constructing the combined series. `continue_series` discovers the frontier lazily; an infinite base never invokes its continuation. Handle an empty base according to the model's intended behavior: return `None` when nothing should follow, rather than an empty series, so code walking the components sees the chain end. Let a missing terminal amount propagate unless an explicit replacement is justified.

For segments sharing one query policy, `Series.extend(query, base=base.walk(), cont=...)` is a lower-level alternative. Its callback returns a cell chain, and the first continuation key must be strictly after the base's final key. It applies one query to the combined chain; it does not preserve separate segment query policies like `Series.flatten` does.

## Joining chains of chains

`concat_cells(outer)` joins a chain whose values are cell chains into one chain, in outer order; the outer keys are discarded. `flat_map_cells(outer, fn)` maps each outer value to a chain first (`concat_cells` after a map); `fn` receives the resolved value because the resulting structure depends on it. Put one query over the result with `Series(cells, query, name=...)`.

```py
from datetime import date

from orcaset import YF, Chain, Maybe, Period, Series, concat_cells, of_cells, query

opening = date(2025, 12, 31)
midyear = date(2026, 6, 30)
year_end = date(2026, 12, 31)

first: Series[Period, float, Maybe[float]] = Series.of(
    query.accrue(YF.cmonthly), [(Period(opening, midyear), 1.0)], name="First"
)
second: Series[Period, float, Maybe[float]] = Series.of(
    query.accrue(YF.cmonthly), [(Period(midyear, year_end), 2.0)], name="Second"
)
segments: Chain[int, Chain[Period, Maybe[float]]] = of_cells(
    [(0, first.walk()), (1, second.walk())], name="Segments"
)
joined = Series(concat_cells(segments, name="Joined"), query.accrue_drop(YF.cmonthly), name="Joined")
# Context().get_at(joined, Period(opening, year_end)) == 3.0
```

- Inner cells pass through with their own value rules; walked segments contribute their answers at their own keys. The segments' own queries are dropped for every other key; the joined series' query answers everything, including gaps between segments.
- Keys must be strictly ascending across the join. Nothing is clipped: an overlap raises `ValueError` when the walk reaches it.
- An outer value is read only when the walk exhausts the chain before it, so an infinite inner chain leaves later outer values unbuilt, and the outer chain may itself be lazy and infinite.

Choose the join by how the pieces relate:

| Pieces | Use |
| --- | --- |
| Sequential, non-overlapping, one query policy for the whole line (e.g. successive contracts) | `flat_map_cells` / `concat_cells` |
| Sequential segments that keep their own query policies (e.g. actuals then projections) | `Series.flatten` |
| A base followed by a continuation built from its last node | `continue_series` or `Series.extend` |
| Concurrent, overlapping (e.g. cohorts, many independent instances) | `ops.add`, or a scan rollup |

[components.md](components.md) uses `flat_map_cells` to join one line across a lazy chain of component records.

## Clipping a series to a window

`clip_periods(series, start, end)` restricts a period-keyed series to `(start, end]`; `clip_dates` does the same for a date-keyed series. Either bound may be `None`. Use them to take part of an existing line, such as a share of a flow over an abatement, waiver, or ramp window, instead of rebuilding its cells.

```py
from orcaset import Val, clip_dates, clip_periods, ops

fee = Series.of(
    query.accrue(YF.cmonthly),
    [(Period(opening, midyear), 600.0), (Period(midyear, year_end), 900.0)],
    name="Fee",
)
waiver_share = Val(0.5, name="Waiver share")
waived = clip_periods(fee, date(2026, 3, 31), date(2026, 9, 30), name="Waived fee basis")
waiver = ops.neg(ops.scale(waived, waiver_share, name="Waived fee"), name="Fee waiver")
# Year: -(300 * 0.5 + 450 * 0.5) == -375.0

balance = Series.of(query.last, [(opening, 10.0), (midyear, 20.0)], name="Balance")
balance_after_close = clip_dates(balance, start=date(2026, 3, 31), name="Balance after close")
# 2026-04-30: Na, since the earlier cell is outside the window; 2026-07-31: 20.0
```

- `clip_periods` trims each query to the window and forwards it to the source, so a window crossing a step in the source values each side at its own amount. Its cells are the source cells trimmed to the window, each valued by the source's query, so they agree with direct queries. A query entirely outside answers `outside`, which defaults to `Na`; the result type is `Series[Period, W, Maybe[W]]`.
- `clip_dates` passes cells inside the window through unchanged and answers queries inside with the source's query over those cells only, so a look-back query like `query.last` cannot reach a cell before `start`. Queries outside answer `outside`, which defaults to `Na`.
- Pass `outside=` only when it states what the window means, such as `outside=0.0` for a flow that stops at the window (a lease's share of an expense pool over its term). Do not re-wrap a clip's cells in another query to change what it answers outside: the source keeps answering inside the window, so a missing value there stays `Na`.
- Clipped series are views: they follow scenario changes to the source and record it as a dependency.
- A zero-length window should be an empty series (`Series[...].empty(query.accrue_drop(yf))`) when the caller expects a flow that answers `0.0`, rather than a clip whose answers are all `Na`.

## Cyclic value dependency

Use a seeded demand for a genuine financial circularity. In a revolver plug, ending debt depends on the cash shortfall including interest, while interest on average debt depends on ending debt. The iterative-solver example uses the same mechanism for capitalized interest.

The simplified model below starts with zero debt and funds a monthly cash deficit plus interest. A negative deficit repays debt down to zero. It omits commitment limits, fees, and the cash balance that would retain any surplus after repayment.

```py
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Effect,
    Maybe,
    Period,
    Series,
    Val,
    get,
    get_at,
    isna,
    maybe_abs_distance,
    query,
)

opening = date(2025, 12, 31)
month = relativedelta(months=1, day=31)
first_month = Period(opening, opening + month)
opening_debt = Val(0.0, name="Opening revolver")
monthly_deficit = Val(100.0, name="Cash deficit before interest")
annual_rate = Val(0.12, name="Annual revolver rate")
seed_date: date | None = None


@Series.define(query.last, seed=seed_date, name="Revolver")
def revolver(prior_date: date | None) -> Effect[tuple[date, float, date]]:
    if prior_date is None:
        return opening, (yield from get(opening_debt)), opening
    end_date = prior_date + month
    begin = yield from get_at(revolver, prior_date)
    interest_amount = yield from get_at(interest, Period(prior_date, end_date))
    if isna(begin) or isna(interest_amount):
        raise ValueError(f"Missing revolver inputs at {end_date}")
    deficit = yield from get(monthly_deficit)
    return end_date, max(0.0, begin + deficit + interest_amount), end_date


@Series.define(query.accrue(YF.cmonthly), seed=first_month, name="Revolver interest")
def interest(period: Period) -> Effect[tuple[Period, float, Period]]:
    begin = yield from get_at(revolver, period.start)
    end: Maybe[float] = yield from get_at(
        revolver,
        period.end,
        seed=0.0,
        distance=maybe_abs_distance,
        tol=1e-9,
        max_iter=1000,
    )
    if isna(begin) or isna(end):
        raise ValueError(f"Missing average revolver balance for {period}")
    rate = yield from get(annual_rate)
    amount = (begin + end) * 0.5 * rate * YF.cmonthly(*period)
    return period, amount, period.from_end(month)
```

Keep one date-keyed debt series and query its start and end dates for average balances. This example's monthly interest fraction is `0.12 / 12`; use the loan's specified day-count convention for a real model. Interest is positive here because it increases the funding requirement.

`seed` is an initial guess for the demanded ending balance, not an opening balance or a replacement for missing data. `distance` compares successive guesses of that same return type. Use `maybe_abs_distance` for `Maybe[float]` demands and `abs_distance` for plain floats. The `tol` and `max_iter` keywords override the context defaults for this seeded demand. A policy on one demand in the cycle is enough, including when evaluation starts from another node in the cycle.

Check the fixed-point equations independently. With beginning debt zero, monthly deficit `100`, and monthly rate `0.01`, ending debt solves `E = 100 + 0.005 * E`, giving approximately `100.50251256`; interest is approximately `0.50251256`. Evaluate both the interest and ending-debt entrypoints in fresh contexts. Without a cycle policy, a demand cycle raises `CycleError`; failure to converge raises `ConvergenceError`. Do not add seeds to hide an accidental self-reference or treat a failed iteration as a solved amount.

## Cohort schedules

Use a series of child schedules when each source period creates an independent cohort, such as depreciation from capex or amortization from loan originations. Overlapping cohorts contribute simultaneously, so roll them up with addition rather than flattening them as sequential segments.

The capex-cohorts pattern uses `map_cells` to create one child schedule per capex key and `scan_cells` to carry the cohort rules forward. The example spends `100` annually, places each cohort in service at the capex period end, and depreciates half its cost in each of the following two years.

```py
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Effect,
    Maybe,
    Period,
    Rule,
    Series,
    Thunk,
    Val,
    get,
    get_at,
    isna,
    map_cells,
    query,
    scan_cells,
)

opening = date(2025, 12, 31)
year = relativedelta(years=1, day=31)
first_year = Period(opening, opening + year)
annual_capex = Val(100.0, name="Annual capex")
by_days = query.accrue(lambda start, end: (end - start).days)


@Series.define(by_days, seed=first_year, name="Capex")
def capex(period: Period) -> Effect[tuple[Period, float, Period]]:
    spend = yield from get(annual_capex)
    return period, spend, period.from_end(year)


type Cohort = Series[Period, float, Maybe[float]]
type CohortRules = tuple[Rule[Cohort], ...]


def build_cohort(source_key: Period) -> Cohort:
    periods = Period.list(source_key.end, year, source_key.end + year * 2)

    def depreciation() -> Effect[float]:
        spend = yield from get_at(capex, source_key)
        if isna(spend):
            raise ValueError(f"Missing capex for {source_key}")
        return spend / 2.0

    return Series.of(
        by_days,
        pairs=[(period, Thunk(depreciation)) for period in periods],
        name=f"Depreciation@{source_key.end}",
    )


cohort_cells = map_cells(
    capex.walk(),
    lambda source_key, _cell: build_cohort(source_key),
    name="Depreciation cohorts",
)
cohort_schedules: Series[Period, Cohort, Maybe[Cohort]] = Series(
    cohort_cells, query.exact, name="Depreciation cohorts"
)


def sum_cohorts(cohorts: CohortRules, period: Period) -> Effect[float]:
    total = 0.0
    for rule in cohorts:
        cohort = yield from get(rule)
        amount = yield from get_at(cohort, period)
        if not isna(amount):
            total += amount
    return total


def rollup(
    prior: CohortRules,
    period: Period,
    current: Rule[Cohort],
) -> tuple[Thunk[float], CohortRules]:
    cohorts = (*prior, current)
    return Thunk(lambda: sum_cohorts(cohorts, period)), cohorts


total_depreciation: Series[Period, float, Maybe[float]] = Series(
    scan_cells(cohort_cells, seed=(), fn=rollup, name="Total depreciation"),
    by_days,
    name="Total depreciation",
)
```

The callbacks construct and query the lazily created child schedules required by this pattern. `map_cells` receives a source key and its walked answer rule without forcing the amount. The cohort chain is built in the model, so the rollup scans it directly rather than reading it back out of `cohort_schedules`. Each depreciation cell uses a `Thunk` so its `get_at(capex, source_key)` runs only when the amount is demanded. The outer `query.exact` locates a cohort by its original capex key; the child query calculates its depreciation for a requested interval.

The scan stores `Rule[Cohort]` objects, not resolved schedules or depreciation amounts. Returning a `Thunk` keeps calculation separate from structural traversal. Querying a total resolves the accumulated cohort rules and their values, retaining dependencies back to capex.

In this example, a child returns `Na` outside its two-year life, which the rollup treats as no contribution. Missing source capex raises an error instead of disappearing from the sum. If adapting the pattern to schedules with missing values inside their active lives, distinguish those gaps from inactive cohorts before treating `Na` as zero.

The first four annual totals are `0`, `50`, `100`, and `100`; each individual cohort depreciates exactly `100` over its life. Partial-period amounts use actual days within each annual cell. The rollup inherits the capex keys, so its aggregation grid must include cohort activation and expiration boundaries. If cohorts start or stop inside those cells, refine the grid before prorating totals. If capex ends, extend the rollup grid through the remaining useful lives rather than dropping still-active cohorts at the last spend period.

The two-year child horizon is an economic lifetime, not a reporting cutoff. The parent capex series remains open-ended. This simple scan retains expired cohort rules, so its accumulated history grows; for large models, prune expired cohorts only when their contributions to all relevant future queries are known to be zero.
