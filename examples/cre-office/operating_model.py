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
property_name = Val("Property", "1201 Broadway")
location = Val("Location", "New York, NY")
rsf = Val("Rentable square feet", 25_000.0)
price_psf = Val("Acquisition price / RSF", 1_000.0)
acquisition_price = Fn(
    "Acquisition price", lambda: (yield from get(rsf)) * (yield from get(price_psf))
)
property_tax_rate = Val("Historical property tax rate", 0.04)
management_fee_pct = Val("Property management fee %", 0.03)
upfront_reserve_funding = Val("Upfront reserve funding", 62_500.0)
senior_ltv = Val("Senior acquisition LTV", 0.50)
mezzanine_ltv = Val("Mezzanine acquisition LTV", 0.10)
senior_rate = Val("Senior interest rate", 0.05)
mezzanine_cash_rate = Val("Mezzanine cash interest rate", 0.07)
mezzanine_pik_rate = Val("Mezzanine PIK interest rate", 0.03)
amortization_years = Val("Senior amortization years", 25)
senior_maturity_years = Val("Senior maturity years", 5)
mezzanine_maturity_years = Val("Mezzanine maturity years", 5)
operating_partner_pct = Val("Operating partner equity %", 0.10)
senior_debt = Fn(
    "Senior debt", lambda: (yield from get(acquisition_price)) * (yield from get(senior_ltv))
)
mezzanine_debt = Fn(
    "Mezzanine debt", lambda: (yield from get(acquisition_price)) * (yield from get(mezzanine_ltv))
)
initial_debt = Fn(
    "Initial total debt", lambda: (yield from get(senior_debt)) + (yield from get(mezzanine_debt))
)


def annual(name: str) -> Callable[[Callable[[Period], Effect[Maybe[float]]]], Amount]:
    """Define a finite annual amount series, with calendar-month accrual for queries."""

    def decorate(calculate: Callable[[Period], Effect[Maybe[float]]]) -> Amount:
        @Series[Period, Maybe[float], Maybe[float]].define(name, query.accrue(YF.cmonthly), seed=0)
        def line(index: int) -> Effect[tuple[Period, Maybe[float], int] | None]:
            if index >= len(periods):
                return None
            period = periods[index]
            return period, (yield from calculate(period)), index + 1

        return line

    return decorate


def growth_series(name: str, pairs: tuple[tuple[Period, float], ...]) -> Growth:
    return Series[Period, float, Maybe[float]].of(
        name, query.avg(YF.cmonthly), Val(f"{name} assumptions", pairs)
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
    rate = Val(f"Historical {name} / RSF", initial_psf)
    initial = Fn(f"Historical {name}", lambda: (yield from get(rate)) * (yield from get(rsf)))
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
    "Historical property taxes",
    lambda: (yield from get(acquisition_price)) * (yield from get(property_tax_rate)),
)
property_tax_growth = growth_series(
    "Property tax growth", ((Period(date(2026, 12, 31), date.max), 0.02),)
)
property_taxes = growing_line("Property taxes", initial_taxes, property_tax_growth)
reimbursable_expenses = ops.add(
    "NNN reimbursable expenses",
    cam,
    utilities,
    insurance,
    property_taxes,
    merge_keys=period_union,
)


office_1_rent_growth_assumptions = Val(
    "Office lease #1 rent growth assumptions",
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.04),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.04),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.04),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.03),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
)
office_1_rent_growth = Series[Period, float, Maybe[float]].of(
    "Office lease #1 rent growth", query.avg(YF.cmonthly), office_1_rent_growth_assumptions
)
office_2_rent_growth_assumptions = Val(
    "Office lease #2 rent growth assumptions",
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.05),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.05),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.04),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.04),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
)
office_2_rent_growth = Series[Period, float, Maybe[float]].of(
    "Office lease #2 rent growth", query.avg(YF.cmonthly), office_2_rent_growth_assumptions
)
retail_3_rent_growth_assumptions = Val(
    "Retail lease #3 rent growth assumptions",
    (
        (Period(date(2026, 12, 31), date(2027, 12, 31)), 0.06),
        (Period(date(2027, 12, 31), date(2028, 12, 31)), 0.05),
        (Period(date(2028, 12, 31), date(2029, 12, 31)), 0.045),
        (Period(date(2029, 12, 31), date(2030, 12, 31)), 0.04),
        (Period(date(2030, 12, 31), date(2031, 12, 31)), 0.03),
        (Period(date(2031, 12, 31), date.max), 0.03),
    ),
)
retail_3_rent_growth = Series[Period, float, Maybe[float]].of(
    "Retail lease #3 rent growth", query.avg(YF.cmonthly), retail_3_rent_growth_assumptions
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
    "Occupied RSF",
    *(lease_detail.area for lease_detail in leases),
    merge_keys=period_union,
    fill=0.0,
)


def vacant_from_occupied(occupied: Maybe[float]) -> Effect[Maybe[float]]:
    return maybe.sub_some((yield from get(rsf)), occupied)


vacant_rsf = ops.map("Vacant RSF", occupied_rsf, fn=vacant_from_occupied)
potential_vacant_rent = ops.mul(
    "Potential rent on vacant space", office_1.rent_psf, vacant_rsf, merge_keys=period_union
)
base_rent = ops.add(
    "Base rental income",
    *(t.rent for t in leases),
    potential_vacant_rent,
    merge_keys=period_union,
)
turnover_vacancy = ops.add(
    "Turnover vacancy", *(t.turnover_vacancy for t in leases), merge_keys=period_union
)
free_rent = ops.add("Free rent", *(t.free_rent for t in leases), merge_keys=period_union)
reimbursements = ops.add(
    "Expense reimbursements", *(t.reimbursements for t in leases), merge_keys=period_union
)
pgr = ops.add(
    "Potential gross revenue",
    base_rent,
    ops.neg("Less: turnover vacancy", turnover_vacancy),
    ops.neg("Less: free rent", free_rent),
    reimbursements,
    merge_keys=period_union,
)
egi = ops.sub("Effective gross income", pgr, potential_vacant_rent, merge_keys=period_union)
management_fee = ops.scale("Property management fee", egi, management_fee_pct)
operating_expenses = ops.add(
    "Operating expenses",
    cam,
    utilities,
    insurance,
    property_taxes,
    reserve_contributions,
    management_fee,
    merge_keys=period_union,
)
noi = ops.sub("NOI", egi, operating_expenses, merge_keys=period_union)
noi_margin = ops.map2(
    "NOI / EGI",
    noi,
    egi,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)
tenant_improvements = ops.add(
    "Tenant improvements", *(t.improvements for t in leases), merge_keys=period_union
)
leasing_commissions = ops.add(
    "Leasing commissions", *(t.commissions for t in leases), merge_keys=period_union
)
capital_costs = ops.add(
    "Capital costs", tenant_improvements, leasing_commissions, merge_keys=period_union
)


@Series.define(
    "Capital costs funded by reserves", query.accrue(YF.cmonthly), seed=initial_period
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
    "Upfront reserve funding",
    query.exact_or(0.0),
    [(acquisition_date, Thunk(lambda: get(upfront_reserve_funding)))],
)


@Series.define("Reserve draws", query.exact_or(maybe.some(0.0)), seed=initial_period)
def reserve_draws(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post each period's reserve-funded capital costs as a negative flow on the period end."""
    funded = yield from get_at(reserve_funded_capex, period)
    return period.end, maybe.neg_some(funded), period.from_end(year_offset)


reserve_flows = ops.add("Reserve flows", reserve_funding, reserve_draws, merge_keys=date_union)


@Series.define(
    "Replacement reserve balance",
    accrued_balance(reserve_contributions),
    seed=initial_period,
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
    "Adjusted NOI",
    noi,
    ops.neg("Less: capital costs", capital_costs),
    reserve_funded_capex,
    merge_keys=period_union,
)
adjusted_noi_margin = ops.map2(
    "Adjusted NOI / EGI",
    adjusted_noi,
    egi,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)


@Fn.define("Annual senior debt service")
def annual_senior_service() -> Effect[float]:
    principal = yield from get(senior_debt)
    rate = yield from get(senior_rate)
    years = yield from get(amortization_years)
    return principal / years if rate == 0.0 else principal * rate / (1.0 - (1.0 + rate) ** -years)


@Series.define("Senior loan balance", query.last, seed=initial_period)
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


@Series.define("Mezzanine loan balance", query.last, seed=initial_period)
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
    "Total debt balance before payoff", senior_ending, mezzanine_ending, merge_keys=period_union
)
cash_interest = ops.add(
    "Cash interest", senior_interest, mezzanine_interest, merge_keys=period_union
)
total_interest = ops.add(
    "Total interest including PIK", cash_interest, mezzanine_pik, merge_keys=period_union
)
debt_pi = ops.add("Cash debt service", cash_interest, principal_paid, merge_keys=period_union)
debt_service = ops.neg("Debt service cash flow", debt_pi)
levered_cash_flow = ops.sub("Cash flow to equity", adjusted_noi, debt_pi, merge_keys=period_union)
debt_yield = ops.scale(
    "Debt yield", noi, Fn("Inverse initial debt", lambda: 1.0 / (yield from get(initial_debt)))
)
interest_coverage = ops.map2(
    "NOI interest coverage",
    noi,
    total_interest,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)
adjusted_interest_coverage = ops.map2(
    "Adjusted NOI interest coverage",
    adjusted_noi,
    total_interest,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)
coverage_service = ops.add(
    "Debt service including PIK", total_interest, principal_paid, merge_keys=period_union
)
dscr = ops.map2(
    "NOI DSCR",
    noi,
    coverage_service,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)
adjusted_dscr = ops.map2(
    "Adjusted NOI DSCR",
    adjusted_noi,
    coverage_service,
    fn=lambda n, d: Na if d == 0.0 else maybe.div_some(n, d),
    merge_keys=period_union,
)
