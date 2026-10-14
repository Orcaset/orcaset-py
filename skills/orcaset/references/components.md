# Repeated components and lazy chains of them

Use these patterns when a model has many instances of the same kind of thing, each with several line items built from one set of terms, and each instance may be followed by successors decided by assumptions: contracts that renew, instruments that refinance, assets that are replaced at end of life, customers that churn or expand. Read [core.md](core.md) and the joining and clipping sections of [patterns.md](patterns.md) first.

The code blocks below form one runnable model, in order.

## When constructors are the right tool

[core.md](core.md) forbids helper and builder functions for line items. That rule targets one-off line items defined at module level, which should stay individually editable. It does not apply when:

- the same structure is instantiated many times from data rows (one instance per row), or
- instances are created lazily inside a chain because their dates or existence depend on assumptions.

In those cases write a small set of constructors that build a component record. Each constructor builds every line from one set of terms, so instances are consistent by construction. Keep module-level aggregates (totals, statement lines, returns) as named module-level definitions as usual.

## A component is a record of independent lines

```py
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Chain,
    Context,
    Effect,
    Maybe,
    Period,
    QueryFn,
    Rule,
    Series,
    Thunk,
    Val,
    clip_periods,
    flat_map_cells,
    get,
    get_at,
    maybe,
    ops,
    period_union,
    query,
    unfold_cells,
)

type Line = Series[Period, Maybe[float], Maybe[float]]
type Cells = list[tuple[Period, Maybe[float] | Thunk[Maybe[float]]]]

month = relativedelta(months=1, day=31)
year = relativedelta(years=1, day=31)
opening = date(2025, 12, 31)


@dataclass(frozen=True)
class Contract:
    name: str
    term: Period  # Structure: a successor starts at term.end.
    units: Line  # A level, averaged over a query.
    revenue: Line  # A flow, accrued over a query.
    discount: Line  # A negative flow.
```

- Each line is its own `Series` with its own cell grid and query, so a level and a flow on the same component need not share keys.
- Fields that determine structure (dates, terms, which successor comes next) are plain Python values, not rules. A successor reads `prior.term.end` directly.
- The record holds only what the instance is. Assumptions about what happens after it belong to the succession policy, not the record.
- A component that has no line of some kind still gets that field, as an empty series: `Series[K, V, W].empty(name, query)`. Give the type parameters explicitly, since there are no cells to infer from. Choose its query so aggregation treats it correctly (usually `accrue_drop` for a flow, so it answers `0.0`).

## Shared assumptions are a bundle of rules

```py
@dataclass(frozen=True)
class Terms:
    """Resolved structural assumptions; they set a contract's dates."""

    term_years: int
    discount_months: int


@dataclass(frozen=True)
class Pricing:
    annual_price: Series[Period, float, Maybe[float]]  # Price per unit, a level.
    escalator: Val[float]
    discount_share: Val[float]
    renews: Val[bool]
    term_years: Val[int]
    discount_months: Val[int]

    def terms(self) -> Effect[Terms]:
        return Terms(
            term_years=(yield from get(self.term_years)),
            discount_months=(yield from get(self.discount_months)),
        )


price_year_one = Val("Price / unit, year one", 120.0)
price_growth = Val("Price growth", 0.03)


@Series.define("Price / unit", query.avg(YF.cmonthly), seed=Period(opening, opening + year))
def price(period: Period) -> Effect[tuple[Period, float, Period]]:
    years = YF.cmonthly(opening, period.start)
    base = yield from get(price_year_one)
    growth = yield from get(price_growth)
    return period, base * math.pow(1.0 + growth, years), period.from_end(year)


pricing = Pricing(
    annual_price=price,
    escalator=Val("Annual escalator", 0.02),
    discount_share=Val("Renewal discount share", 1.0),
    renews=Val("Contracts renew", True),
    term_years=Val("Renewal term years", 3),
    discount_months=Val("Renewal discount months", 2),
)
```

- Group assumptions shared by many instances in a frozen dataclass of `Val`s and series, defined once at module level so scenarios can change them.
- Separate **structural** assumptions (those that set dates, terms, or counts) from value assumptions. A method such as `terms()` resolves the structural ones together as an `Effect`, so it can only be called inside a rule, where the read is recorded as a dependency of the structure it shapes.
- Value assumptions (prices, rates, shares) stay as rules and are read inside cell `Thunk`s, so they never force structure.
- Do not create sensitizable `Val`s inside constructors. A `Val` created per instance can only be reached through the record; put the assumption in the bundle or the data row instead.

## Constructors build every line from one set of terms

```py
def no_amount(name: str) -> Line:
    return Series[Period, Maybe[float], Maybe[float]].empty(name, query.accrue_drop(YF.cmonthly))


def discount(name: str, revenue: Line, start: date, months: int, share: Rule[float]) -> Line:
    """``share`` of ``revenue`` for ``months`` from ``start``, as a negative amount."""
    if months == 0:
        return no_amount(name)
    window = clip_periods(
        f"{name} basis", revenue, start, start + relativedelta(months=months, day=31)
    )
    return ops.neg(name, ops.scale(f"{name} share", window, share))


def signed_contract(name: str, term: Period, units: float, annual_price: float) -> Contract:
    """A contract with fixed terms."""
    revenue_cells: Cells = [(term, annual_price * units * YF.cmonthly(*term))]
    return Contract(
        name=name,
        term=term,
        units=Series.of(f"{name} units", query.avg(YF.cmonthly), [(term, units)]),
        revenue=Series.of(f"{name} revenue", query.accrue(YF.cmonthly), revenue_cells),
        discount=no_amount(f"{name} discount"),
    )


def renewal(name: str, start: date, units: float, pricing: Pricing, terms: Terms) -> Contract:
    """A projected contract at the prevailing price, escalating each year."""
    term = Period(start, start + relativedelta(years=terms.term_years, day=31))

    def year_amount(index: int, period: Period) -> Thunk[Maybe[float]]:
        def amount() -> Effect[Maybe[float]]:
            at_start = yield from get_at(pricing.annual_price, Period(start, start + month))
            growth = math.pow(1.0 + (yield from get(pricing.escalator)), index)
            return maybe.mul_some(at_start, units * growth * YF.cmonthly(*period))

        return Thunk(amount)

    periods = Period.list(start, year, term.end)
    revenue = Series.of(
        f"{name} revenue",
        query.accrue(YF.cmonthly),
        [(period, year_amount(index, period)) for index, period in enumerate(periods)],
    )
    return Contract(
        name=name,
        term=term,
        units=Series.of(f"{name} units", query.avg(YF.cmonthly), [(term, units)]),
        revenue=revenue,
        discount=discount(
            f"{name} discount", revenue, start, terms.discount_months, pricing.discount_share
        ),
    )
```

- One constructor per way an instance comes into being (known terms from data, projected from assumptions, and so on). Constructors are plain functions; a hand-built record remains possible for unusual cases.
- Constructors take resolved structural values (`terms`) and rules for everything else. Cell values that read rules are `Thunk`s, so building an instance resolves nothing.
- Derive dependent lines from other lines of the same instance rather than recomputing them. Here the discount is a clipped, scaled view of revenue (see [patterns.md](patterns.md#clipping-a-series-to-a-window)), so it follows every revenue step.
- Use names that identify the instance (`f"{name} revenue"`); they appear in dependency trees and errors.

## Succession is a lazy chain decided by a policy

```py
type Successor = Callable[[Contract, str, float], Effect[Contract | None]]
"""Given an instance, a name for its successor, and fixed attributes, the next instance or ``None``."""


def contract_chain(
    account: str, units: float, first: Contract, successor: Successor
) -> Chain[int, Contract]:
    """``first``, then each contract ``successor`` produces from the one before, until ``None``."""

    def step(
        state: tuple[int, Contract | None],
    ) -> Effect[tuple[int, Contract, tuple[int, Contract | None]] | None]:
        index, prior = state
        if prior is None:
            contract = first
        else:
            contract = yield from successor(prior, f"{account} contract {index}", units)
        if contract is None:
            return None
        return index, contract, (index + 1, contract)

    return unfold_cells(f"{account} contracts", seed=(0, None), step=step)


def renew_at_market(pricing: Pricing) -> Successor:
    """Renew at the prevailing price while contracts renew."""

    def next_contract(prior: Contract, name: str, units: float) -> Effect[Contract | None]:
        if not (yield from get(pricing.renews)):
            return None
        terms = yield from pricing.terms()
        return renewal(name, prior.term.end, units, pricing, terms)

    return next_contract
```

- `unfold_cells` builds a `Chain[int, Component]` keyed by position. The step for index `n` builds instance `n` from instance `n - 1`, so each successor is decided only when its tail is requested, and the chain may be infinite.
- The policy runs inside the chain's structural rule, so it may `yield from get(...)` assumptions. Those reads become dependencies of the chain, and changing them in a new context can change **which** instances exist, not just their values.
- Make policies values: a type alias for the callable and factory functions that close over their assumption bundle (`renew_at_market(pricing)`). Policies compose, for example one that follows a list of known future instances and then hands off to another policy, or one that takes a contractual option when an `exercised` flag is set and otherwise falls back.
- An instance whose first member is itself assumption-driven (for example, an opening created at a modeled date) can take `first: Contract | Opening`, where `Opening` is a callable returning `Effect[Contract]`, resolved in the first step.
- A policy must not read the model's own aggregated outputs (totals built from these chains). That is a dependency cycle. Policies read assumptions; outputs read chains.

### Blend uncertain outcomes into one successor

When a successor has several probabilistic outcomes (renews or is replaced, extends or prepays), prefer one probability-weighted instance whose lines blend the outcomes over branching the chain. A single successor keeps each chain linear and its aggregate an expected value. Build the blend inside the constructor: weight each outcome's line by a rule for its probability (`ops.scale`) and add them, with different windows per outcome where timing differs.

## Instances come from data rows

```py
@dataclass(frozen=True)
class Signed:
    """A row of input data."""

    account: str
    units: float
    annual_price: float
    start: date
    end: date


@dataclass(frozen=True)
class Account:
    name: str
    contracts: Chain[int, Contract]


rows = [
    Signed("Account A", 100.0, 110.0, date(2025, 6, 30), date(2027, 6, 30)),
    Signed("Account B", 40.0, 125.0, date(2025, 12, 31), date(2026, 12, 31)),
]
policy = renew_at_market(pricing)
accounts = [
    Account(
        row.account,
        contract_chain(
            row.account,
            row.units,
            signed_contract(
                f"{row.account} contract 0",
                Period(row.start, row.end),
                row.units,
                row.annual_price,
            ),
            policy,
        ),
    )
    for row in rows
]
```

- Keep source data as a list of frozen dataclass rows that mirror the source's columns, with comments citing where each field came from and marking which fields are assumed.
- Convert rows to instances with one function or comprehension. Keep the list of instances at module level so outputs and aggregates can import it; bind individually named instances by unpacking when specific ones are referenced elsewhere.
- When an input must be solved to reproduce a reported total (a growth rate, a step, an allocation), solve it in plain Python from the rows if it depends only on data, and print the reconciliation against the source in the outputs. If it depends on a `Val`, it must be a rule.

## Aggregate: join each chain, then add across instances

```py
def account_line(
    account: Account,
    name: str,
    line: Callable[[Contract], Line],
    over: QueryFn[Period, Maybe[float], Maybe[float]],
) -> Line:
    """One line joined across every contract on ``account``, under one query."""
    label = f"{account.name} {name}"

    def cells(contract: Contract) -> Chain[Period, Maybe[float]]:
        return line(contract).cells

    return Series(label, flat_map_cells(label, account.contracts, cells), over)


flow = query.accrue_drop(YF.cmonthly)  # Time outside every contract accrues nothing.
revenue_by_account = [account_line(a, "revenue", lambda c: c.revenue, flow) for a in accounts]
gross_revenue = ops.add("Gross revenue", *revenue_by_account, merge_keys=period_union)
discounts = ops.add(
    "Discounts",
    *(account_line(a, "discount", lambda c: c.discount, flow) for a in accounts),
    merge_keys=period_union,
)
net_revenue = ops.add("Net revenue", gross_revenue, discounts, merge_keys=period_union)
active_units = ops.add(
    "Active units",
    *(
        account_line(a, "units", lambda c: c.units, query.avg_fill(YF.cmonthly, fill=0.0))
        for a in accounts
    ),
    merge_keys=period_union,
)
```

- Successive instances in one chain do not overlap, so join a line across them with `flat_map_cells` (one chain of cells) and put a single query over the result. Overlapping keys raise `ValueError` rather than being clipped silently.
- Concurrent instances do overlap, so combine them with `ops.add`.
- The aggregate's query, not each component's, decides what time with no cells means. Choose it per line:

| Line kind | Query | Time outside every cell |
| --- | --- | --- |
| Flow where a gap means missing data | `accrue` | `Na` |
| Flow where a gap means nothing happened | `accrue_drop` | `0.0` |
| Level where a gap means zero | `avg_fill(yf, fill=0.0)` | `0.0` |

- `flat_map_cells`'s callback receives the resolved component; write it as a named function with an annotated parameter if a lambda's parameter type is not inferred.
- A small aggregation function like `account_line` is fine: it is the one way every instance line is joined, and each named module-level aggregate still states which line and query it uses.

## Outputs walk chains to a horizon

Chains may be infinite. Bound any walk over them in output code, never in the model:

```py
if __name__ == "__main__":
    horizon = date(2031, 12, 31)
    ctx = Context()
    for account in accounts:
        node = ctx.get(account.contracts)
        while node is not None and (contract := ctx.get(node.value)).term.start < horizon:
            print(contract.name, contract.term)
            node = ctx.get(node.tail)

    years = Period.list(opening, year, date(2029, 12, 31))
    for period in years:
        print(period, ctx.get_at(net_revenue, period), ctx.get_at(active_units, period))

    # A scenario can change the chain's structure: no renewals means no successors.
    pricing.renews.value = False
    scenario = Context()
    for period in years:
        print(period, scenario.get_at(net_revenue, period), scenario.get_at(active_units, period))
```

Print a listing of projected instances (name, dates, key values) alongside the statements so the succession can be checked.

## Module layout

For a larger model built this way, split modules along these lines, each importing only from those above it:

| Module | Contents |
| --- | --- |
| Assumptions | Assumption bundles and shared curves |
| Components | The record type, line builders, and constructors |
| Succession | The chain builder and policies |
| Data | Source rows, calibration, and the list of instances |
| Aggregates | Lines joined per chain and summed across instances |
| Model | Statements, financing, and returns built on the aggregates |
| Outputs | Contexts, report periods, listings, reconciliations, and scenarios |
