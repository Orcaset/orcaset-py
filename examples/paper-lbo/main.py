from collections.abc import Iterable
from datetime import date
from itertools import pairwise, repeat

import numpy_financial as npf
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    CellFactory,
    CellStream,
    Context,
    DateSeries,
    Group,
    Period,
    PeriodSeries,
    Rule,
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
    maybe_abs_distance,
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


annual_revenue_growth = Rule("Revenue growth rate", lambda: 0.1)
exit_multiple = Rule("Exit multiple", lambda: 5.0)


@PeriodSeries.define("Revenue", accrual(YF.cmonthly))
def revenue() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    periods = Period.seq(acquisition_date, year_offset)
    yield next(periods), initial_revenue
    for k in periods:

        def cell(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.from_start(-year_offset))
            if isna(prior):
                raise ValueError(f"missing prior revenue for {p}")
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
            beginning_debt = yield from get_at(debt_balance, p.start)
            sweep = yield from get_at(cash_sweep, p, seed=0.0, distance=maybe_abs_distance)
            if isna(beginning_debt) or isna(sweep):
                return 0.0
            ending_debt = beginning_debt - sweep
            return (beginning_debt + ending_debt) / 2 * -interest_rate

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
@DateSeries.define("Debt", last)
def debt_balance() -> CellStream[date, float]:
    dt = acquisition_date

    ntm_purchase_ebitda = yield from get_at(ebitda, Period(dt, dt + year_offset))
    if isna(ntm_purchase_ebitda):
        raise ValueError(f"missing EBITDA for {Period(dt, dt + year_offset)}")
    opening = ntm_purchase_ebitda * purchase_multiple * ltv
    yield dt, opening
    for p in Period.seq(dt, year_offset, dt + hold_period):

        def factory(period: Period = p) -> Step[float]:
            begin = yield from get_at(debt_balance, period.start)
            if isna(begin):
                raise ValueError(f"missing beginning debt for {period.start}")
            sweep = yield from get_at(cash_sweep, period)
            if isna(sweep):
                raise ValueError(f"missing cash sweep for {period}")
            balloon = yield from get_at(balloon_payment, period)
            if isna(balloon):
                raise ValueError(f"missing balloon payment for {period}")
            return begin - sweep - balloon

        yield p.end, factory


@PeriodSeries.define("Cash sweep", accrual(YF.cmonthly))
def cash_sweep() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    hold_end = acquisition_date + hold_period
    for period in Period.seq(acquisition_date, year_offset, hold_end):

        def cell(p: Period = period) -> Step[float]:
            db = yield from get_at(debt_balance, p.start)
            if isna(db):
                return 0.0
            fcf_sweep = yield from get_at(fcf, p)
            if isna(fcf_sweep):
                return 0.0
            return min(db, fcf_sweep)

        yield period, cell


@PeriodSeries.define("Balloon payment", accrual(YF.cmonthly))
def balloon_payment() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    hold_end = acquisition_date + hold_period
    for period in Period.seq(acquisition_date, year_offset, hold_end):
        if period.end != hold_end:
            yield period, 0.0
            continue

        def cell(p: Period = period) -> Step[float]:
            begin = yield from get_at(debt_balance, p.start)
            if isna(begin):
                return 0.0
            sweep = yield from get_at(cash_sweep, p)
            if isna(sweep):
                return begin
            return begin - sweep

        yield period, cell


# Levered cash flow
exact_or_zero = exact_or(0.0)


@DateSeries.define("Purchase price", exact_or_zero)
def purchase_price() -> CellStream[date, float]:
    entry_ebitda = yield from get_at(
        ebitda, Period(acquisition_date, acquisition_date + year_offset)
    )
    if isna(entry_ebitda):
        raise ValueError(
            f"missing EBITDA for {Period(acquisition_date, acquisition_date + year_offset)}"
        )
    yield acquisition_date, entry_ebitda * -purchase_multiple


@DateSeries.define("Exit value", exact_or_zero)
def exit_value() -> CellStream[date, float]:
    def factory() -> Step[float]:
        exit_ebitda = yield from get_at(
            ebitda,
            Period(
                acquisition_date + hold_period,
                acquisition_date + hold_period + year_offset,
            ),
        )
        if isna(exit_ebitda):
            raise ValueError(f"missing EBITDA for {acquisition_date + hold_period}")
        multiple = yield from get(exit_multiple)
        return exit_ebitda * multiple

    yield acquisition_date + hold_period, factory


@DateSeries.define("Year end fcf payment", exact_or_zero)
def year_end_fcf_payment() -> CellStream[date, float]:
    for p in Period.seq(acquisition_date, year_offset, acquisition_date + hold_period):

        def cell(p: Period = p) -> Step[float]:
            fcf_pmt = yield from get_at(fcf, p)
            if isna(fcf_pmt):
                return 0.0
            return fcf_pmt

        yield p.end, cell


@DateSeries.define("Debt cash flows", exact_or_zero)
def debt_cash_flows() -> CellStream[date, float]:
    """Yield changes in debt balance as a DateSeries to show debt cash flows."""
    dates = list((yield from get(debt_balance.keys())))
    if not dates:
        return

    def opening(d: date = dates[0]) -> Step[float]:
        end = yield from get_at(debt_balance, d)
        if isna(end):
            raise ValueError(f"missing debt balance for {d}")
        return end

    yield dates[0], opening
    for prev, curr in pairwise(dates):

        def cell(d: date = curr, prior: date = prev) -> Step[float]:
            begin = yield from get_at(debt_balance, prior)
            end = yield from get_at(debt_balance, d)
            if isna(begin):
                raise ValueError(f"missing debt balance for {prior}")
            if isna(end):
                raise ValueError(f"missing debt balance for {d}")
            return end - begin

        yield curr, cell


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
            debt_balance,
            cash_sweep,
            balloon_payment,
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
equity = -ctx.get_at(levered_cash_flow, acquisition_date)
pp = -ctx.get_at(purchase_price, acquisition_date)

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
