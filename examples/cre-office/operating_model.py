"""1201 Broadway annual acquisition model, built from 1201-broadway-outline.md."""

from collections.abc import Callable
from datetime import date

from dateutil.relativedelta import relativedelta
from orcaset import (
    YF,
    Chain,
    Cons,
    Effect,
    Fn,
    Maybe,
    Na,
    Period,
    QueryFn,
    Rule,
    Series,
    Thunk,
    Val,
    date_union,
    get,
    get_at,
    maybe,
    ops,
    period_union,
    query,
)

from leases import LeaseType, lease

type Amount = Series[Period, Maybe[float], Maybe[float]]
type Growth = Series[Period, float, Maybe[float]]
year_offset = relativedelta(years=1)
acquisition_date = date(2026, 12, 31)
initial_period = Period(date(2025, 12, 31), acquisition_date)
periods = Period.list(initial_period.start, year_offset, date(2032, 12, 31))
property_name = Val("1201 Broadway", name="Property")
location = Val("New York, NY", name="Location")
rsf = Val(25_000.0, name="Rentable square feet")
price_psf = Val(1_000.0, name="Acquisition price / RSF")
acquisition_price = Fn(
    lambda: (yield from get(rsf)) * (yield from get(price_psf)), name="Acquisition price"
)
property_tax_rate = Val(0.04, name="Historical property tax rate")
management_fee_pct = Val(0.03, name="Property management fee %")
upfront_reserve_funding = Val(62_500.0, name="Upfront reserve funding")
senior_ltv = Val(0.50, name="Senior acquisition LTV")
mezzanine_ltv = Val(0.10, name="Mezzanine acquisition LTV")
senior_rate = Val(0.05, name="Senior interest rate")
mezzanine_cash_rate = Val(0.07, name="Mezzanine cash interest rate")
mezzanine_pik_rate = Val(0.03, name="Mezzanine PIK interest rate")
amortization_years = Val(25, name="Senior amortization years")
senior_maturity_years = Val(5, name="Senior maturity years")
mezzanine_maturity_years = Val(5, name="Mezzanine maturity years")
operating_partner_pct = Val(0.10, name="Operating partner equity %")
senior_debt = Fn(
    lambda: (yield from get(acquisition_price)) * (yield from get(senior_ltv)), name="Senior debt"
)
mezzanine_debt = Fn(
    lambda: (yield from get(acquisition_price)) * (yield from get(mezzanine_ltv)), name="Mezzanine debt"
)
initial_debt = Fn(
    lambda: (yield from get(senior_debt)) + (yield from get(mezzanine_debt)), name="Initial total debt"
)


def annual(name: str) -> Callable[[Callable[[Period], Effect[Maybe[float]]]], Amount]:
    """Define a finite annual amount series, with calendar-month accrual for queries."""

    def decorate(calculate: Callable[[Period], Effect[Maybe[float]]]) -> Amount:
        @Series[Period, Maybe[float], Maybe[float]].define(query.accrue(YF.cmonthly), seed=0, name=name)
        def line(index: int) -> Effect[tuple[Period, Maybe[float], int] | None]:
            if index >= len(periods):
                return None
            period = periods[index]
            return period, (yield from calculate(period)), index + 1

        return line

    return decorate


def growth_series(name: str, pairs: tuple[tuple[Period, float], ...]) -> Growth:
    return Series[Period, float, Maybe[float]].of(
        query.avg(YF.cmonthly), Val(pairs, name=f"{name} assumptions"), name=name
    )


def growing_line(name: str, initial: Rule[float], growth: Growth) -> Amount:
    @annual(name)
    def line(period: Period) -> Effect[Maybe[float]]:
        if period == initial_period:
            return (yield from get(initial))
        prior = yield from get_at(line, period.from_start(-year_offset))
        g = yield from get_at(growth, period)
        return maybe.mul_some(prior, maybe.sum_some(1.0, g))

    return line


def accrued_balance[V](
    accrual: Series[Period, V, Maybe[float]],
) -> QueryFn[date, Maybe[float], Maybe[float]]:
    """Build a date query: last posted balance plus ``accrual`` from that boundary through ``q``."""

    def balance_query(q: date, cells: Chain[date, Maybe[float]]) -> Effect[Maybe[float]]:
        posted: Cons[date, Maybe[float]] | None = None
        node = yield from get(cells)
        while node is not None:
            if node.key == q:
                return (yield from get(node.value))
            if q < node.key:
                break
            posted = node
            node = yield from get(node.tail)
        if posted is None:
            return Na
        last = yield from get(posted.value)
        stub = yield from get_at(accrual, Period(posted.key, q))
        return maybe.sum_some(last, stub)

    return balance_query


def expense(name: str, initial_psf: float, growth: float) -> Amount:
    rate = Val(initial_psf, name=f"Historical {name} / RSF")
    initial = Fn(lambda: (yield from get(rate)) * (yield from get(rsf)), name=f"Historical {name}")
    return growing_line(
        name,
        initial,
        growth_series(f"{name} growth", ((Period(date(2026, 12, 31), date.max), growth),)),
    )


cam = expense("CAM", 5.0, 0.035)
utilities = expense("Common area utilities", 3.0, 0.03)
insurance = expense("Insurance", 2.0, 0.025)
reserve_contributions = expense("Replacement reserve contributions", 2.5, 0.03)
initial_taxes = Fn(
    lambda: (yield from get(acquisition_price)) * (yield from get(property_tax_rate)),
    name="Historical property taxes",
)
property_tax_growth = growth_series(
    "Property tax growth", ((Period(date(2026, 12, 31), date.max), 0.02),)
)
property_taxes = growing_line("Property taxes", initial_taxes, property_tax_growth)
reimbursable_expenses = ops.add(
    cam,
    utilities,
    insurance,
    property_taxes,
    merge_keys=period_union,
    name="NNN reimbursable expenses",
)


office_1_rent_growth_assumptions = Val(
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.04),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.04),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.04),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.03),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
    name="Office lease #1 rent growth assumptions",
)
office_1_rent_growth = Series[Period, float, Maybe[float]].of(
    query.avg(YF.cmonthly), office_1_rent_growth_assumptions, name="Office lease #1 rent growth"
)
office_2_rent_growth_assumptions = Val(
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.05),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.05),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.04),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.04),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
    name="Office lease #2 rent growth assumptions",
)
office_2_rent_growth = Series[Period, float, Maybe[float]].of(
    query.avg(YF.cmonthly), office_2_rent_growth_assumptions, name="Office lease #2 rent growth"
)
retail_3_rent_growth_assumptions = Val(
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.06),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.05),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.045),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.04),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
    name="Retail lease #3 rent growth assumptions",
)
retail_3_rent_growth = Series[Period, float, Maybe[float]].of(
    query.avg(YF.cmonthly), retail_3_rent_growth_assumptions, name="Retail lease #3 rent growth"
)
office_1 = lease(
    "Office lease #1",
    LeaseType.FULL_SERVICE,
    10_000.0,
    date(2028, 12, 31),
    120.0,
    office_1_rent_growth,
    start=initial_period.start,
    year_offset=year_offset,
    rsf=rsf,
    property_taxes=property_taxes,
    reimbursable_expenses=reimbursable_expenses,
    growing_line=growing_line,
)
office_2 = lease(
    "Office lease #2",
    LeaseType.SINGLE_NET,
    7_000.0,
    date(2029, 12, 31),
    105.0,
    office_2_rent_growth,
    start=initial_period.start,
    year_offset=year_offset,
    rsf=rsf,
    property_taxes=property_taxes,
    reimbursable_expenses=reimbursable_expenses,
    growing_line=growing_line,
)
retail_3 = lease(
    "Retail lease #3",
    LeaseType.TRIPLE_NET,
    6_000.0,
    date(2033, 12, 31),
    90.0,
    retail_3_rent_growth,
    start=initial_period.start,
    year_offset=year_offset,
    rsf=rsf,
    property_taxes=property_taxes,
    reimbursable_expenses=reimbursable_expenses,
    growing_line=growing_line,
)
leases = (office_1, office_2, retail_3)


occupied_rsf = ops.add(
    *(lease_detail.area for lease_detail in leases),
    merge_keys=period_union,
    fill=0.0,
    name="Occupied RSF",
)


def vacant_from_occupied(occupied: Maybe[float]) -> Effect[Maybe[float]]:
    return maybe.sub_some((yield from get(rsf)), occupied)


vacant_rsf = ops.map(occupied_rsf, fn=vacant_from_occupied, name="Vacant RSF")
potential_vacant_rent = ops.mul(
    office_1.rent_psf, vacant_rsf, merge_keys=period_union, name="Potential rent on vacant space"
)
base_rent = ops.add(
    *(t.rent for t in leases),
    potential_vacant_rent,
    merge_keys=period_union,
    name="Base rental income",
)
turnover_vacancy = ops.add(
    *(t.turnover_vacancy for t in leases), merge_keys=period_union, name="Turnover vacancy"
)
free_rent = ops.add(*(t.free_rent for t in leases), merge_keys=period_union, name="Free rent")
reimbursements = ops.add(
    *(t.reimbursements for t in leases), merge_keys=period_union, name="Expense reimbursements"
)
pgr = ops.add(
    base_rent,
    ops.neg(turnover_vacancy, name="Less: turnover vacancy"),
    ops.neg(free_rent, name="Less: free rent"),
    reimbursements,
    merge_keys=period_union,
    name="Potential gross revenue",
)
egi = ops.sub(pgr, potential_vacant_rent, merge_keys=period_union, name="Effective gross income")
management_fee = ops.scale(egi, management_fee_pct, name="Property management fee")
operating_expenses = ops.add(
    cam,
    utilities,
    insurance,
    property_taxes,
    reserve_contributions,
    management_fee,
    merge_keys=period_union,
    name="Operating expenses",
)
noi = ops.sub(egi, operating_expenses, merge_keys=period_union, name="NOI")
noi_margin = ops.map2(
    noi,
    egi,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="NOI / EGI",
)
tenant_improvements = ops.add(
    *(t.improvements for t in leases), merge_keys=period_union, name="Tenant improvements"
)
leasing_commissions = ops.add(
    *(t.commissions for t in leases), merge_keys=period_union, name="Leasing commissions"
)
capital_costs = ops.add(
    tenant_improvements, leasing_commissions, merge_keys=period_union, name="Capital costs"
)


@Series.define(
    query.accrue(YF.cmonthly), seed=initial_period, name="Capital costs funded by reserves"
)
def reserve_funded_capex(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """Capital costs paid from the reserve, capped at the beginning balance plus contributions."""
    beginning = yield from get_at(reserve_balance, period.start)
    contributions = yield from get_at(reserve_contributions, period)
    spend = yield from get_at(capital_costs, period)

    def fundable(available: float, cost: float) -> float:
        return max(0.0, min(available, cost))

    funded = maybe.map2_some(fundable)(maybe.sum_some(beginning, contributions), spend)
    return period, funded, period.from_end(year_offset)


reserve_funding = Series[date, Maybe[float], Maybe[float]].of(
    query.exact_or(0.0),
    [(acquisition_date, Thunk(lambda: get(upfront_reserve_funding)))],
    name="Upfront reserve funding",
)


@Series.define(query.exact_or(maybe.some(0.0)), seed=initial_period, name="Reserve draws")
def reserve_draws(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post each period's reserve-funded capital costs as a negative flow on the period end."""
    funded = yield from get_at(reserve_funded_capex, period)
    return period.end, maybe.neg_some(funded), period.from_end(year_offset)


reserve_flows = ops.add(reserve_funding, reserve_draws, merge_keys=date_union, name="Reserve flows")


@Series.define(
    accrued_balance(reserve_contributions),
    seed=initial_period,
    name="Replacement reserve balance",
)
def reserve_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``, rolled forward from the prior period."""
    if period == initial_period:
        balance = yield from get_at(reserve_funding, period.start)
    else:
        prior = period.from_start(-year_offset)
        beginning = yield from get_at(reserve_balance, prior.start)
        contributions = yield from get_at(reserve_contributions, prior)
        flow = yield from get_at(reserve_flows, period.start)
        balance = maybe.sum_some(beginning, contributions, flow)
    return period.start, balance, period.from_end(year_offset)


adjusted_noi = ops.add(
    noi,
    ops.neg(capital_costs, name="Less: capital costs"),
    reserve_funded_capex,
    merge_keys=period_union,
    name="Adjusted NOI",
)
adjusted_noi_margin = ops.map2(
    adjusted_noi,
    egi,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="Adjusted NOI / EGI",
)


@Fn.define(name="Annual senior debt service")
def annual_senior_service() -> Effect[float]:
    principal = yield from get(senior_debt)
    rate = yield from get(senior_rate)
    years = yield from get(amortization_years)
    return principal / years if rate == 0.0 else principal * rate / (1.0 - (1.0 + rate) ** -years)


@Series.define(query.last, seed=initial_period, name="Senior loan balance")
def senior_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``; carry it until payoff, with zero after maturity."""
    if period == initial_period:
        return period.start, maybe.some(0.0), period.from_end(year_offset)
    if period.start >= acquisition_date + (yield from get(senior_maturity_years)) * year_offset:
        return period.start, maybe.some(0.0), period.from_end(year_offset)
    if period.start == acquisition_date:
        return period.start, (yield from get(senior_debt)), period.from_end(year_offset)
    prior = yield from get_at(senior_balance, period.from_start(-year_offset).start)
    service = yield from get(annual_senior_service)
    rate = yield from get(senior_rate)

    def amortize(balance: float) -> float:
        return balance - min(balance, max(0.0, service - balance * rate))

    return period.start, maybe.map_some(amortize)(prior), period.from_end(year_offset)


@Series.define(query.last, seed=initial_period, name="Mezzanine loan balance")
def mezzanine_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``, accreting PIK, with zero after maturity."""
    if period == initial_period:
        return period.start, maybe.some(0.0), period.from_end(year_offset)
    if period.start >= acquisition_date + (yield from get(mezzanine_maturity_years)) * year_offset:
        return period.start, maybe.some(0.0), period.from_end(year_offset)
    if period.start == acquisition_date:
        return period.start, (yield from get(mezzanine_debt)), period.from_end(year_offset)
    prior = yield from get_at(mezzanine_balance, period.from_start(-year_offset).start)
    pik = yield from get(mezzanine_pik_rate)
    balance = maybe.mul_some(prior, maybe.sum_some(1.0, pik))
    return period.start, balance, period.from_end(year_offset)


@annual("Senior cash interest")
def senior_interest(period: Period) -> Effect[Maybe[float]]:
    return maybe.mul_some(
        (yield from get_at(senior_balance, period.start)), (yield from get(senior_rate))
    )


@annual("Mezzanine cash interest")
def mezzanine_interest(period: Period) -> Effect[Maybe[float]]:
    return maybe.mul_some(
        (yield from get_at(mezzanine_balance, period.start)),
        (yield from get(mezzanine_cash_rate)),
    )


@annual("Mezzanine PIK interest")
def mezzanine_pik(period: Period) -> Effect[Maybe[float]]:
    return maybe.mul_some(
        (yield from get_at(mezzanine_balance, period.start)),
        (yield from get(mezzanine_pik_rate)),
    )


@annual("Senior principal amortization")
def principal_paid(period: Period) -> Effect[Maybe[float]]:
    balance = yield from get_at(senior_balance, period.start)
    payment = yield from get(annual_senior_service)
    interest = yield from get_at(senior_interest, period)

    def amortize(balance: float, interest: float) -> float:
        return min(balance, max(0.0, payment - interest))

    return maybe.map2_some(amortize)(balance, interest)


# Ending balances are before the balloon repayment, including in the maturity year.
@annual("Ending senior balance before payoff")
def senior_ending(period: Period) -> Effect[Maybe[float]]:
    return maybe.sub_some(
        (yield from get_at(senior_balance, period.start)),
        (yield from get_at(principal_paid, period)),
    )


@annual("Ending mezzanine balance before payoff")
def mezzanine_ending(period: Period) -> Effect[Maybe[float]]:
    return maybe.sum_some(
        (yield from get_at(mezzanine_balance, period.start)),
        (yield from get_at(mezzanine_pik, period)),
    )
total_debt_balance = ops.add(
    senior_ending, mezzanine_ending, merge_keys=period_union, name="Total debt balance before payoff"
)
cash_interest = ops.add(
    senior_interest, mezzanine_interest, merge_keys=period_union, name="Cash interest"
)
total_interest = ops.add(
    cash_interest, mezzanine_pik, merge_keys=period_union, name="Total interest including PIK"
)
debt_pi = ops.add(cash_interest, principal_paid, merge_keys=period_union, name="Cash debt service")
debt_service = ops.neg(debt_pi, name="Debt service cash flow")
levered_cash_flow = ops.sub(adjusted_noi, debt_pi, merge_keys=period_union, name="Cash flow to equity")
debt_yield = ops.scale(
    noi, Fn(lambda: 1.0 / (yield from get(initial_debt)), name="Inverse initial debt"), name="Debt yield"
)
interest_coverage = ops.map2(
    noi,
    total_interest,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="NOI interest coverage",
)
adjusted_interest_coverage = ops.map2(
    adjusted_noi,
    total_interest,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="Adjusted NOI interest coverage",
)
coverage_service = ops.add(
    total_interest, principal_paid, merge_keys=period_union, name="Debt service including PIK"
)
dscr = ops.map2(
    noi,
    coverage_service,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="NOI DSCR",
)
adjusted_dscr = ops.map2(
    adjusted_noi,
    coverage_service,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
    name="Adjusted NOI DSCR",
)
