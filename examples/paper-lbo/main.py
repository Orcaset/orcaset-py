import operator
from datetime import date

import numpy_financial as npf
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cell,
    Cells,
    Context,
    Group,
    Maybe,
    Period,
    Series,
    Step,
    Stmt,
    Thunk,
    Total,
    accrual,
    exact,
    fixed_width_table,
    get,
    get_at,
    isna,
    last,
    map_some,
    maybe_abs_distance,
    multiply_some,
    ops,
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
ACCRUE = accrual(YF.cmonthly)

annual_revenue_growth = Cell("Revenue growth rate", lambda: 0.1)
exit_multiple = Cell("Exit multiple", lambda: 5.0)


@Series.define("Revenue", ACCRUE, seed=next(Period.seq(acquisition_date, year_offset)))
def revenue_step(period: Period) -> tuple[Period, Thunk[float], Period]:
    def value() -> Step[float]:
        prior = yield from get_at(revenue_step, period.from_start(-year_offset))
        if isna(prior):
            return initial_revenue
        growth = yield from get(annual_revenue_growth)
        return prior * (1 + growth)

    return period, Thunk(value), period.from_end(year_offset)


revenue: Series[Period, Maybe[float], Maybe[float]] = revenue_step
ebitda = ops.mul_scalar("EBITDA", revenue, ebitda_margin)
da: Series[Period, float, Maybe[float]] = Series.unfold(
    "D&A",
    ACCRUE,
    seed=next(Period.seq(acquisition_date, year_offset)),
    step=lambda period: (period, annual_da, period.from_end(year_offset)),
)
ebit = ops.period.add("EBIT", ebitda, da)


def interest_step(
    period: Period,
) -> tuple[Period, Thunk[float], Period] | None:
    if period.start >= acquisition_date + hold_period:
        return None

    def value() -> Step[float]:
        beginning = yield from get_at(debt_before_balloon, period.start)
        ending = yield from get_at(
            debt_before_balloon,
            period.end,
            seed=0.0,
            distance=maybe_abs_distance,
        )
        return 0.0 if isna(beginning) or isna(ending) else (beginning + ending) / 2 * -interest_rate

    return period, Thunk(value), period.from_end(year_offset)


interest = Series.unfold(
    "Interest",
    ACCRUE,
    seed=next(Period.seq(acquisition_date, year_offset)),
    step=interest_step,
)
ebt = ops.period.add("EBT", ebit, interest)
taxes = ops.mul_scalar("Taxes", ebt, -tax_rate)
capex = ops.mul_scalar("Capex", revenue, -capex_pct_revenue)
change_in_nwc: Series[Period, float, Maybe[float]] = Series.unfold(
    "Change in NWC",
    ACCRUE,
    seed=next(Period.seq(acquisition_date, year_offset)),
    step=lambda period: (period, -annual_nwc_increase, period.from_end(year_offset)),
)
fcf = ops.period.add(
    "FCF",
    ebitda,
    taxes,
    interest,
    capex,
    change_in_nwc,
)


def exact_or_zero(
    q: date,
    cells: Cells[date, Maybe[float]],
) -> Step[Maybe[float]]:
    return value_or((yield from exact(q, cells)), 0.0)


def draw_value() -> Step[Maybe[float]]:
    ntm_ebitda = yield from get_at(ebitda, Period(acquisition_date, acquisition_date + year_offset))
    return multiply_some((ntm_ebitda, purchase_multiple, ltv))


draws = Series.of(
    "Draws",
    exact_or_zero,
    [(acquisition_date, Thunk(draw_value))],
)


def debt_sweep_step(
    period: Period,
) -> tuple[Period, Thunk[float], Period] | None:
    if period.start >= acquisition_date + hold_period:
        return None

    def value() -> Step[float]:
        beginning = yield from get_at(debt_before_balloon, period.start)
        free_cash_flow = yield from get_at(fcf, period)
        if isna(beginning) or isna(free_cash_flow):
            return 0.0
        return -min(beginning, free_cash_flow)

    return period, Thunk(value), period.from_end(year_offset)


debt_sweep = Series.unfold(
    "Cash sweep",
    ACCRUE,
    seed=next(Period.seq(acquisition_date, year_offset)),
    step=debt_sweep_step,
)


def payment(period: Period) -> Step[float]:
    return value_or((yield from get_at(debt_sweep, period)), 0.0)


sweep_periods = list(Period.seq(acquisition_date, year_offset, acquisition_date + hold_period))
sweep_payments = Series.of(
    "Sweep payments",
    exact_or_zero,
    [(period.end, Thunk(lambda period=period: payment(period))) for period in sweep_periods],
)

type BalanceState[V] = tuple[Cells[date, V], date | None]


def cumulate[V](
    name: str,
    flows: Series[date, V, Maybe[float]],
) -> Series[date, Maybe[float], Maybe[float]]:
    def step(
        state: BalanceState[V],
    ) -> Step[tuple[date, Thunk[Maybe[float]], BalanceState[V]] | None]:
        cells, previous = state
        node = yield from get(cells)
        if node is None:
            return None
        day = node.key

        def value() -> Step[Maybe[float]]:
            prior = 0.0 if previous is None else (yield from get_at(balance, previous))
            flow = yield from get_at(flows, day)
            if isna(prior):
                return flow
            return prior + value_or(flow, 0.0)

        return day, Thunk(value), (node.tail, day)

    balance = Series.unfold(name, last, seed=(flows.cells, None), step=step)
    return balance


pre_balloon_debt_flows = ops.date.add(
    "Pre-balloon debt flows",
    draws,
    sweep_payments,
    fill=0.0,
)
debt_before_balloon = cumulate("Debt before balloon", pre_balloon_debt_flows)


def balloon_value() -> Step[float]:
    remaining = yield from get_at(debt_before_balloon, acquisition_date + hold_period)
    return -value_or(remaining, 0.0)


balloon_payment = Series.of(
    "Balloon payment",
    exact_or_zero,
    [(acquisition_date + hold_period, Thunk(balloon_value))],
)
debt_cash_flows = ops.date.add(
    "Debt cash flows",
    pre_balloon_debt_flows,
    balloon_payment,
    fill=0.0,
)
debt_balance = cumulate("Debt balance", debt_cash_flows)


def purchase_price_value() -> Step[Maybe[float]]:
    entry_ebitda = yield from get_at(
        ebitda, Period(acquisition_date, acquisition_date + year_offset)
    )
    return multiply_some((entry_ebitda, -purchase_multiple))


purchase_price = Series.of(
    "Purchase price",
    exact_or_zero,
    [(acquisition_date, Thunk(purchase_price_value))],
)


def exit_value_fn() -> Step[Maybe[float]]:
    exit_ebitda = yield from get_at(
        ebitda,
        Period(
            acquisition_date + hold_period,
            acquisition_date + hold_period + year_offset,
        ),
    )
    multiple: Maybe[float] = yield from get(exit_multiple)
    return multiply_some((exit_ebitda, multiple))


exit_value = Series.of(
    "Exit value",
    exact_or_zero,
    [(acquisition_date + hold_period, Thunk(exit_value_fn))],
)


def fcf_payment(period: Period) -> Step[float]:
    return value_or((yield from get_at(fcf, period)), 0.0)


year_end_fcf_payment = Series.of(
    "Year end fcf payment",
    exact_or_zero,
    [(period.end, Thunk(lambda period=period: fcf_payment(period))) for period in sweep_periods],
)
levered_cash_flow = ops.date.add(
    "Levered cash flow",
    purchase_price,
    exit_value,
    year_end_fcf_payment,
    debt_cash_flows,
    fill=0.0,
)

stmt = Stmt(
    Group([revenue, Total(ebt, [Total(ebit, [ebitda, da]), interest]), taxes]),
    Group([Total(fcf, [ebitda, taxes, interest, capex, change_in_nwc])]),
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

ctx = Context()
display_periods = Period.list(
    acquisition_date, year_offset, acquisition_date + hold_period + year_offset
)
print(fixed_width_table(stmt.values_for_periods(ctx, display_periods)))

cf_dates = [acquisition_date, *[period.end for period in sweep_periods]]
cashflows: list[float] = []
for day in cf_dates:
    value = ctx.get_at(levered_cash_flow, day)
    if isna(value):
        raise ValueError(f"missing levered cash flow for {day}")
    cashflows.append(value)
print(f"MOM: {cashflows[-1] / -cashflows[0]:.2f}")
print(f"IRR: {float(npf.irr(cashflows)):.2%}")

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

print()
print("IRR sensitivity")
print(f"{'':6} " + " ".join(f"{growth:>8.0%}" for growth in (0.06, 0.08, 0.10, 0.12, 0.14)))
for multiple in (3.0, 4.0, 5.0, 6.0, 7.0):
    exit_multiple.fn = lambda multiple=multiple: multiple
    row = [f"{multiple:.1f}x".rjust(6)]
    for growth in (0.06, 0.08, 0.10, 0.12, 0.14):
        annual_revenue_growth.fn = lambda growth=growth: growth
        scenario = Context()
        scenario_cashflows: list[float] = []
        for day in cf_dates:
            value = scenario.get_at(levered_cash_flow, day)
            if isna(value):
                raise ValueError(f"missing levered cash flow for {day}")
            scenario_cashflows.append(value)
        row.append(f"{float(npf.irr(scenario_cashflows)):.2%}".rjust(8))
    print(" ".join(row))
