import operator
from collections.abc import Iterable
from datetime import date
from itertools import repeat

import numpy_financial as npf
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cell,
    CellFactory,
    CellStream,
    Context,
    DateSeries,
    DateSeriesBase,
    Group,
    Maybe,
    Period,
    PeriodSeries,
    Step,
    Stmt,
    Total,
    accrual,
    exact_or,
    fixed_width_table,
    get,
    get_at,
    isna,
    last,
    map_some,
    maybe_abs_distance,
    multiply_some,
    some,
    value_or,
)

acquisition_date = date(2022, 12, 31)
hold_period = relativedelta(years=5)
year_offset = relativedelta(years=1)
initial_revenue = 100.0
ebitda_margin = 0.4
annual_da = -20.0
interest_rate = 0.10
capex_pct_revenue = 0.15
annual_nwc_increase = 5.0
tax_rate = 0.4
purchase_multiple = 5.0
ltv = 0.6


annual_revenue_growth = Cell("Revenue growth rate", lambda: 0.1)
exit_multiple = Cell("Exit multiple", lambda: 5.0)


@PeriodSeries.define("Revenue", accrual(YF.cmonthly))
def revenue() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    periods = Period.seq(acquisition_date, year_offset)
    for k in periods:

        def cell(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.from_start(-year_offset))
            if isna(prior):
                return initial_revenue
            growth = yield from get(annual_revenue_growth)
            return prior * (1 + growth)

        yield k, cell


ebitda = (revenue * ebitda_margin).named("EBITDA")
da = PeriodSeries(
    "D&A",
    lambda: zip(Period.seq(acquisition_date, year_offset), repeat(annual_da)),
    accrual(YF.cmonthly),
)
ebit = (ebitda + da).named("EBIT")


@PeriodSeries.define("Interest", accrual(YF.cmonthly))
def interest() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    hold_end = acquisition_date + hold_period
    for period in Period.seq(acquisition_date, year_offset, hold_end):

        def cell(p: Period = period) -> Step[float]:
            beginning = yield from get_at(debt_before_balloon, p.start)
            ending = yield from get_at(
                debt_before_balloon, p.end, seed=0.0, distance=maybe_abs_distance
            )
            if isna(beginning) or isna(ending):
                return 0.0
            return (beginning + ending) / 2 * -interest_rate

        yield period, cell


ebt = (ebit + interest).named("EBT")
taxes = (ebt * -tax_rate).named("Taxes")

# Cash flow
capex = (revenue * -capex_pct_revenue).named("Capex")
change_in_nwc = PeriodSeries(
    "Change in NWC",
    lambda: zip(Period.seq(acquisition_date, year_offset), repeat(-annual_nwc_increase)),
    accrual(YF.cmonthly),
)
fcf = (ebitda + taxes + interest + capex + change_in_nwc).named("FCF")


# Debt
exact_or_zero = exact_or(some(0.0))


@DateSeries.define("Draws", exact_or_zero)
def draws() -> CellStream[date, Maybe[float]]:
    def cell() -> Step[Maybe[float]]:
        entry_period = Period(acquisition_date, acquisition_date + year_offset)
        ntm_purchase_ebitda = yield from get_at(ebitda, entry_period)
        return multiply_some((ntm_purchase_ebitda, purchase_multiple, ltv))

    yield acquisition_date, cell


@PeriodSeries.define("Cash sweep", accrual(YF.cmonthly))
def debt_sweep() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    hold_end = acquisition_date + hold_period
    for period in Period.seq(acquisition_date, year_offset, hold_end):

        def cell(p: Period = period) -> Step[float]:
            db = yield from get_at(debt_before_balloon, p.start)
            if isna(db):
                return 0.0
            fcf_sweep = yield from get_at(fcf, p)
            if isna(fcf_sweep):
                return 0.0
            return -min(db, fcf_sweep)

        yield period, cell


@DateSeries.define("Sweep payments", exact_or_zero)
def sweep_payments() -> CellStream[date, float]:
    keys = yield from get(debt_sweep.keys())
    for p in keys:

        def cell(p: Period = p) -> Step[float]:
            sweep = yield from get_at(debt_sweep, p)
            return value_or(sweep, 0.0)

        yield p.end, cell


def cumulate(name: str, flows: DateSeriesBase[Maybe[float]]) -> DateSeries[Maybe[float]]:
    """Accumulate a date-keyed flow series into a running balance (stock)."""

    @DateSeries.define(name, last)
    def balance() -> CellStream[date, Maybe[float]]:
        prev: date | None = None
        for d in (yield from get(flows.keys())):

            def cell(d: date = d, prev: date | None = prev) -> Step[Maybe[float]]:
                prior = 0.0 if prev is None else (yield from get_at(balance, prev))
                flow = yield from get_at(flows, d)
                if isna(prior):
                    return flow
                return prior + value_or(flow, 0.0)

            yield d, cell
            prev = d

    return balance


pre_balloon_debt_flows = (draws + sweep_payments).named("Pre-balloon debt flows")
debt_before_balloon = cumulate("Debt before balloon", pre_balloon_debt_flows)


@DateSeries.define("Balloon payment", exact_or_zero)
def balloon_payment() -> CellStream[date, float]:
    hold_end = acquisition_date + hold_period

    def cell() -> Step[float]:
        remaining = yield from get_at(debt_before_balloon, hold_end)
        return -value_or(remaining, 0.0)

    yield hold_end, cell


debt_cash_flows = (pre_balloon_debt_flows + balloon_payment).named("Debt cash flows")
debt_balance = cumulate("Debt balance", debt_cash_flows)


# Levered cash flow
@DateSeries.define("Purchase price", exact_or_zero)
def purchase_price() -> CellStream[date, Maybe[float]]:
    entry_ebitda = yield from get_at(
        ebitda, Period(acquisition_date, acquisition_date + year_offset)
    )
    yield acquisition_date, multiply_some((entry_ebitda, -purchase_multiple))


@DateSeries.define("Exit value", exact_or_zero)
def exit_value() -> CellStream[date, Maybe[float]]:
    def factory() -> Step[Maybe[float]]:
        exit_ebitda = yield from get_at(
            ebitda,
            Period(
                acquisition_date + hold_period,
                acquisition_date + hold_period + year_offset,
            ),
        )
        multiple: Maybe[float] = yield from get(exit_multiple)
        return multiply_some((exit_ebitda, multiple))

    yield acquisition_date + hold_period, factory


@DateSeries.define("Year end fcf payment", exact_or_zero)
def year_end_fcf_payment() -> CellStream[date, float]:
    for p in Period.seq(acquisition_date, year_offset, acquisition_date + hold_period):

        def cell(p: Period = p) -> Step[float]:
            fcf_pmt = yield from get_at(fcf, p)
            return value_or(fcf_pmt, 0.0)

        yield p.end, cell


levered_cash_flow = (purchase_price + exit_value + year_end_fcf_payment + debt_cash_flows).named(
    "Levered cash flow"
)


# Statement
stmt = Stmt(
    Group([revenue, Total(ebt, [Total(ebit, [ebitda, da]), interest]), taxes]),
    Group(
        [
            Total(fcf, [ebitda, taxes, interest, capex, change_in_nwc]),
        ]
    ),
    Group(
        [
            draws,
            debt_sweep,
            debt_before_balloon,
            balloon_payment,
            debt_balance,
            debt_cash_flows,
        ]
    ),
    Total(
        levered_cash_flow,
        [purchase_price, exit_value, year_end_fcf_payment, debt_cash_flows],
    ),
)

# Print output
ctx = Context()

## Pro forma
display_periods = Period.list(
    acquisition_date, year_offset, acquisition_date + hold_period + year_offset
)
output = stmt.values_for_periods(ctx, display_periods)
print(fixed_width_table(output))

cf_dates = [
    acquisition_date,
    *[p.end for p in Period.seq(acquisition_date, year_offset, acquisition_date + hold_period)],
]
cashflows: list[float] = []
for d in cf_dates:
    value = ctx.get_at(levered_cash_flow, d)
    if isna(value):
        raise ValueError(f"missing levered cash flow for {d}")
    cashflows.append(value)
print(f"MOM: {cashflows[-1] / -cashflows[0]:.2f}")
print(f"IRR: {float(npf.irr(cashflows)):.2%}")

## Source and uses
loan = ctx.get_at(debt_balance, acquisition_date)
equity = map_some(operator.neg)(ctx.get_at(levered_cash_flow, acquisition_date))
pp = map_some(operator.neg)(ctx.get_at(purchase_price, acquisition_date))

print()
print(
    "Sources",
    f" Loan: {loan}",
    f" Equity: {equity}",
    f"Total sources: {loan + equity if not isna(loan) and not isna(equity) else 'n/a'}",
    sep="\n",
)
print()
print("Uses", f" Purchase price: {pp}", f"Total uses: {pp}", sep="\n")


## IRR sensitivity
print()
print("IRR sensitivity")
print(f"{'':6} " + " ".join(f"{g:>8.0%}" for g in (0.06, 0.08, 0.10, 0.12, 0.14)))
for multiple in (3.0, 4.0, 5.0, 6.0, 7.0):
    exit_multiple.fn = lambda m=multiple: m
    row = [f"{multiple:.1f}x".rjust(6)]
    for growth in (0.06, 0.08, 0.10, 0.12, 0.14):
        annual_revenue_growth.fn = lambda g=growth: g
        scenario = Context()
        cfs: list[float] = []
        for d in cf_dates:
            value = scenario.get_at(levered_cash_flow, d)
            if isna(value):
                raise ValueError(f"missing levered cash flow for {d}")
            cfs.append(value)
        row.append(f"{float(npf.irr(cfs)):.2%}".rjust(8))
    print(" ".join(row))
