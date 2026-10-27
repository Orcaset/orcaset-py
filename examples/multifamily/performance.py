"""Annual, pre-tax investment returns for the case's acquisition and exit dates.

Cash flows occur at acquisition and each anniversary. Exit proceeds capitalize
next-year NOI and return unused reserves. IRR uses the annual investment cash flows.
"""

from datetime import date
from itertools import pairwise
from math import isfinite

import numpy_financial as npf
from orcaset import (
    Context,
    Effect,
    Fn,
    Maybe,
    Na,
    Period,
    Series,
    Thunk,
    Val,
    date_union,
    formatter,
    get,
    get_at,
    isna,
    maybe,
    ops,
    period_union,
    query,
    stmt,
)

from model import (
    acquisition_date,
    acquisition_price,
    adjusted_noi,
    debt_pi,
    debt_service,
    interest_expense,
    loan_balance,
    loan_maturity_years,
    noi,
    principal_paid,
    reserve_balance,
    senior_debt,
    upfront_reserve_funding,
    year_offset,
)


def _debt_yield_value(value: Maybe[float]) -> Effect[Maybe[float]]:
    debt = yield from get(senior_debt)
    return Na if debt == 0.0 else maybe.div_some(value, debt)


debt_yield = ops.map(noi, fn=_debt_yield_value, name="Debt yield")
interest_coverage = ops.map2(
    noi,
    interest_expense,
    fn=lambda l, r: Na if r == 0.0 else maybe.div_some(l, r),
    merge_keys=period_union,
    name="Interest coverage",
)
dscr = ops.map2(
    noi,
    debt_pi,
    fn=lambda l, r: Na if r == 0.0 else maybe.div_some(l, r),
    merge_keys=period_union,
    name="DSCR",
)


# Acquisition and exit assumptions from arcadia-gardens-outline.md.
exit_date = Val(date(2022, 12, 31), name="Exit date")
exit_cap_rate = Val(0.06, name="Exit capitalization rate")
selling_cost_pct = Val(0.02, name="Selling costs %")
acquisition_cost_pct = Val(0.01, name="Acquisition costs %")
loan_issuance_fee_pct = Val(0.01, name="Loan issuance fees %")


@Fn.define(name="Investment dates")
def investment_dates() -> Effect[tuple[date, ...]]:
    end = yield from get(exit_date)
    periods: list[Period] = Period.list(acquisition_date, year_offset, end) if end > acquisition_date else []
    if not periods or periods[-1].start + year_offset != end:
        raise ValueError("Exit must be an annual acquisition anniversary after acquisition for numpy_financial.irr")
    return (acquisition_date, *(p.end for p in periods))


@Fn.define(name="Gross sale price")
def gross_sale_price() -> Effect[Maybe[float]]:
    end = yield from get(exit_date)
    cap_rate = yield from get(exit_cap_rate)
    if cap_rate <= 0.0:
        raise ValueError("Exit capitalization rate must be positive")
    forward_noi = yield from get_at(noi, Period(end, end + year_offset))
    return maybe.div_some(forward_noi, cap_rate)


buying_costs = Fn(lambda: -(yield from get(acquisition_price)) * (yield from get(acquisition_cost_pct)), name="Buying costs")
selling_costs = Fn(
    lambda: maybe.neg_some(maybe.mul_some((yield from get(gross_sale_price)), (yield from get(selling_cost_pct)))),
    name="Selling costs",
)
reserve_release = Fn(lambda: (yield from get_at(reserve_balance, (yield from get(exit_date)))), name="Reserve release")
loan_fees = Fn(lambda: -(yield from get(senior_debt)) * (yield from get(loan_issuance_fee_pct)), name="Loan issuance fees")


@Fn.define(name="Net sale proceeds including reserve release")
def sale_proceeds() -> Effect[Maybe[float]]:
    return maybe.sum_some(
        (yield from get(gross_sale_price)), (yield from get(selling_costs)), (yield from get(reserve_release))
    )


def _year_end_flows[V](name: str, source: Series[Period, V, Maybe[float]]) -> Series[date, Maybe[float], Maybe[float]]:
    @Series[date, Maybe[float], Maybe[float]].define(query.exact, seed=0, name=name)
    def flows(index: int) -> Effect[tuple[date, Maybe[float], int] | None]:
        dates = yield from get(investment_dates)
        if index >= len(dates):
            return None
        amount = 0.0 if index == 0 else (yield from get_at(source, Period(dates[index - 1], dates[index])))
        return dates[index], amount, index + 1

    return flows


@Fn.define(name="Debt payoff date")
def debt_payoff_date() -> Effect[date]:
    end = yield from get(exit_date)
    maturity = yield from get(loan_maturity_years)
    return min(end, acquisition_date + maturity * year_offset)


@Fn.define(name="Debt payoff")
def debt_payoff() -> Effect[Maybe[float]]:
    end = yield from get(debt_payoff_date)
    period = Period(end - year_offset, end)
    beginning = yield from get_at(loan_balance, period.start)
    amortization = yield from get_at(principal_paid, period)
    # Include the balloon even though model.loan_balance resets to zero at maturity.
    return maybe.sub_some(amortization, beginning)


purchase_price_flow = Series.of(
    query.exact, ((acquisition_date, Thunk(lambda: -(yield from get(acquisition_price)))),), name="Purchase price"
)
buying_cost_flow = Series.of(query.exact, ((acquisition_date, Thunk(lambda: get(buying_costs))),), name="Buying costs")
initial_reserve_flow = Series.of(
    query.exact,
    ((acquisition_date, Thunk(lambda: -(yield from get(upfront_reserve_funding)))),),
    name="Initial reserve funding",
)
unlevered_property_cash_flow = _year_end_flows("Unlevered property cash flow", adjusted_noi)
sale_price_flow = Series.of(
    query.exact,
    Fn(lambda: (((yield from get(exit_date)), Thunk(lambda: get(gross_sale_price))),), name="Sale price transaction"),
    name="Sale price",
)
selling_cost_flow = Series.of(
    query.exact,
    Fn(lambda: (((yield from get(exit_date)), Thunk(lambda: get(selling_costs))),), name="Selling costs transaction"),
    name="Selling costs",
)
reserve_release_flow = Series.of(
    query.exact,
    Fn(lambda: (((yield from get(exit_date)), Thunk(lambda: get(reserve_release))),), name="Reserve release transaction"),
    name="Reserve release",
)
debt_draw_flow = Series.of(query.exact, ((acquisition_date, Thunk(lambda: get(senior_debt))),), name="Debt draw")
loan_fee_flow = Series.of(query.exact, ((acquisition_date, Thunk(lambda: get(loan_fees))),), name="Loan issuance fees")
debt_service_flow = _year_end_flows("Debt service", debt_service)
debt_payoff_flow = Series.of(
    query.exact,
    Fn(lambda: (((yield from get(debt_payoff_date)), Thunk(lambda: get(debt_payoff))),), name="Debt payoff transaction"),
    name="Debt payoff",
)

_unlevered_components = (
    purchase_price_flow,
    buying_cost_flow,
    initial_reserve_flow,
    unlevered_property_cash_flow,
    sale_price_flow,
    selling_cost_flow,
    reserve_release_flow,
)
_debt_components = (debt_draw_flow, loan_fee_flow, debt_service_flow, debt_payoff_flow)

unlevered_investment_cash_flow = ops.add(
    *_unlevered_components, merge_keys=date_union, fill=0.0, name="Total unlevered cash flow"
)
levered_investment_cash_flow = ops.add(
    unlevered_investment_cash_flow,
    *_debt_components,
    merge_keys=date_union,
    fill=0.0,
    name="Total levered cash flow to equity",
)


def _irr(name: str, cash_flows: Series[date, Maybe[float], Maybe[float]]) -> Fn[Maybe[float]]:
    def calculate() -> Effect[Maybe[float]]:
        dates = yield from get(investment_dates)
        values: list[float] = []
        for day in dates:
            value = yield from get_at(cash_flows, day)
            if isna(value):
                return Na
            values.append(value)
        result = float(npf.irr(values))
        return result if isfinite(result) else Na

    return Fn(calculate, name=name)


unlevered_irr = _irr("Unlevered IRR", unlevered_investment_cash_flow)
levered_irr = _irr("Levered IRR", levered_investment_cash_flow)


def _cash_flow_sum(
    name: str, cash_flows: Series[date, Maybe[float], Maybe[float]], *, contributions: bool
) -> Fn[Maybe[float]]:
    def calculate() -> Effect[Maybe[float]]:
        total = 0.0
        node = yield from get(cash_flows.walk())
        while node is not None:
            value = yield from get(node.value)
            if isna(value):
                return Na
            total += max(-value if contributions else value, 0.0)
            node = yield from get(node.tail)
        return total

    return Fn(calculate, name=name)


unlevered_initial_investment = Fn(
    lambda: maybe.neg_some((yield from get_at(unlevered_investment_cash_flow, acquisition_date))),
    name="Unlevered initial investment",
)
levered_initial_investment = Fn(
    lambda: maybe.neg_some((yield from get_at(levered_investment_cash_flow, acquisition_date))),
    name="Levered initial investment",
)
unlevered_total_return = _cash_flow_sum("Unlevered total return", unlevered_investment_cash_flow, contributions=False)
levered_total_return = _cash_flow_sum("Levered total return", levered_investment_cash_flow, contributions=False)
unlevered_total_investment = _cash_flow_sum(
    "Unlevered capital contributed", unlevered_investment_cash_flow, contributions=True
)
levered_total_investment = _cash_flow_sum(
    "Levered capital contributed", levered_investment_cash_flow, contributions=True
)


@Fn.define(name="Unlevered MOIC")
def unlevered_moic() -> Effect[Maybe[float]]:
    returned = yield from get(unlevered_total_return)
    invested = yield from get(unlevered_total_investment)
    return Na if invested == 0.0 else maybe.div_some(returned, invested)


@Fn.define(name="Levered MOIC")
def levered_moic() -> Effect[Maybe[float]]:
    returned = yield from get(levered_total_return)
    invested = yield from get(levered_total_investment)
    return Na if invested == 0.0 else maybe.div_some(returned, invested)


# Use the same components and total series for the calculations and audit tables.
unlevered_cash_flow_table = stmt.Stmt(stmt.Total(unlevered_investment_cash_flow, _unlevered_components))
levered_cash_flow_table = stmt.Stmt(
    stmt.Total(levered_investment_cash_flow, (unlevered_investment_cash_flow, *_debt_components))
)


debt_metrics = stmt.Stmt(ops.scale(debt_yield, 100.0, name="Debt yield (%)"), interest_coverage, dscr)


buying_cost_amount = Fn(lambda: maybe.neg_some((yield from get(buying_costs))), name="Buying costs")
loan_fee_amount = Fn(lambda: maybe.neg_some((yield from get(loan_fees))), name="Loan issuance fees")
total_uses = Fn(
    lambda: maybe.sum_some(
        (yield from get(acquisition_price)),
        maybe.neg_some((yield from get(buying_costs))),
        maybe.neg_some((yield from get(loan_fees))),
        (yield from get(upfront_reserve_funding)),
    ),
    name="Total uses",
)
equity_investment = Fn(
    lambda: maybe.sub_some((yield from get(total_uses)), (yield from get(senior_debt))),
    name="Equity investment",
)
total_sources = Fn(lambda: get(total_uses), name="Total sources")


if __name__ == "__main__":
    ctx = Context()
    dates = ctx.get(investment_dates)
    periods = [Period(start, end) for start, end in pairwise(dates)]
    sections: list[str] = []
    for title, table, irr, initial, total_return, moic in (
        (
            "Unlevered investment performance",
            unlevered_cash_flow_table,
            unlevered_irr,
            unlevered_initial_investment,
            unlevered_total_return,
            unlevered_moic,
        ),
        (
            "Levered equity performance",
            levered_cash_flow_table,
            levered_irr,
            levered_initial_investment,
            levered_total_return,
            levered_moic,
        ),
    ):
        result = ctx.get(irr)
        rate = "N/A" if isna(result) else f"{result:.4%}"
        sections.append(
            f"{title}\n{formatter.fixed_width_table(table.values(ctx, [dates[0], *periods]))}\n{irr.name}: {rate}"
        )
        for label, metric, spec in (
            ("Total initial investment", initial, ",.2f"),
            ("Total return (cash distributions)", total_return, ",.2f"),
            ("MOIC", moic, ".2f"),
        ):
            value = ctx.get(metric)
            formatted = "N/A" if isna(value) else format(value, spec) + ("x" if metric is moic else "")
            sections[-1] += f"\n{label}: {formatted}"

    def sources_uses_line(node: Fn[Maybe[float]] | Val[float], *, indent: bool = True) -> str:
        value = ctx.get(node)
        amount = "N/A" if isna(value) else f"{value:,.2f}"
        return f"  {node.name:<30}{amount:>15}" if indent else f"{node.name:<32}{amount:>15}"

    uses = [
        sources_uses_line(acquisition_price),
        sources_uses_line(buying_cost_amount),
        sources_uses_line(loan_fee_amount),
        sources_uses_line(upfront_reserve_funding),
        sources_uses_line(total_uses, indent=False),
    ]
    sources = [
        sources_uses_line(senior_debt),
        sources_uses_line(equity_investment),
        sources_uses_line(total_sources, indent=False),
    ]
    sections.append("Sources and uses at acquisition\n" + "\n".join(uses) + "\n" + "-" * 47 + "\n" + "\n".join(sources))
    sections.append(
        "Debt metrics (coverage ratios in x)\n"
        + formatter.fixed_width_table(debt_metrics.values(ctx, periods))
    )
    print("\n\n".join(sections))
