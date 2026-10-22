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

# Assumptions
initial_period = Period(date(2016, 12, 31), date(2017, 12, 31))
initial_monthly_market_rent = Val(1.777777778, name="Market rent")
initial_annual_market_rent_psf = Fn(
    lambda: (yield from get(initial_monthly_market_rent)) * 12,
    name="Initial annual market rent PSF",
)
initial_monthly_in_place_rent = Val(1.60, name="In-place rent")
units = Val(76.0, name="Units")
avg_rsf_per_unit = Val(573.0, name="Average RSF per unit")
rsf = Fn(lambda: (yield from get(units)) * (yield from get(avg_rsf_per_unit)), name="RSF")
parking_spaces_per_unit = Val(1.13, name="Parking spaces per unit")
monthly_parking_fee = Val(50.0, name="Monthly parking fee")
monthly_utility_cost_per_unit = Val(85.0, name="Monthly utility cost per unit")

acquisition_price = Val(9_775_000.0, name="Acquisition price")
rentable_to_gross_ratio = Val(0.80, name="Rentable to gross ratio")
gsf = Fn(
    lambda: (yield from get(rsf)) / (yield from get(rentable_to_gross_ratio)),
    name="Gross square feet",
)
annual_insurance_rate_per_gsf = Val(0.40, name="Annual insurance rate per GSF")
initial_annual_insurance = Fn(
    lambda: (yield from get(gsf)) * (yield from get(annual_insurance_rate_per_gsf)),
    name="Initial annual insurance",
)
annual_replacement_reserve_per_unit = Val(250.0, name="Replacement reserve per unit")
initial_annual_replacement_reserves = Fn(
    lambda: (yield from get(units)) * (yield from get(annual_replacement_reserve_per_unit)),
    name="Initial annual replacement reserves",
)
property_tax_rate = Val(0.0068, name="Property tax rate")
initial_annual_property_taxes = Fn(
    lambda: (yield from get(acquisition_price)) * (yield from get(property_tax_rate)),
    name="Initial annual property taxes",
)
property_management_fee_pct = Val(0.03, name="Property management fee %")


growth_assumptions = Val(
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.035),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.035),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.035),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.03),
        (Period(date(2022, 12, 31), date.max), 0.03),
    ),
    name="Rent growth assumptions",
)


def _pct_loss_to_lease_pairs() -> Effect[tuple[tuple[Period, float], ...]]:
    in_place = yield from get(initial_monthly_in_place_rent)
    market = yield from get(initial_monthly_market_rent)
    return (
        (initial_period, in_place / market - 1.0),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), -0.075),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), -0.05),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), -0.025),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), -0.01),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), -0.01),
        (Period(date(2022, 12, 31), date.max), -0.01),
    )


pct_loss_to_lease_assumption = Fn(_pct_loss_to_lease_pairs, name="Pct loss to lease")

bad_debt_concessions_assumption = Val(
    (
        (initial_period, -0.03),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), -0.03),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), -0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), -0.02),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), -0.01),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), -0.01),
        (Period(date(2022, 12, 31), date.max), -0.01),
    ),
    name="Bad debt and concessions",
)

utility_reimbursement_assumption = Val(
    (
        (initial_period, 0.80),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.83),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.86),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.89),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.92),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.95),
        (Period(date(2022, 12, 31), date.max), 0.95),
    ),
    name="Utility reimbursement percentage",
)

vacancy_assumption = Val(
    (
        (initial_period, 0.0),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), -0.01),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), -0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), -0.03),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), -0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), -0.03),
        (Period(date(2022, 12, 31), date.max), -0.03),
    ),
    name="General vacancy",
)


rent_growth = Series[Period, float, Maybe[float]].of(query.avg(YF.cmonthly), growth_assumptions, name="Rent growth")
bad_debt_concessions = Series.of(
    query.avg(YF.cmonthly), bad_debt_concessions_assumption, name="Bad debt and concessions"
)
utility_reimbursement_pct = Series.of(
    query.avg(YF.cmonthly), utility_reimbursement_assumption, name="Utility reimbursement percentage"
)
vacancy = Series.of(query.avg(YF.cmonthly), vacancy_assumption, name="General vacancy")

operating_expense_growth = Val(
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.03),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.03),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.03),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.03),
        (Period(date(2022, 12, 31), date.max), 0.03),
    ),
    name="Operating expense growth",
)

opex_growth = Series.of(query.avg(YF.cmonthly), operating_expense_growth, name="Operating expense growth")

property_tax_growth_assumption = Val(
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.02),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.02),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.02),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.02),
        (Period(date(2022, 12, 31), date.max), 0.02),
    ),
    name="Property tax growth",
)
property_tax_growth = Series.of(query.avg(YF.cmonthly), property_tax_growth_assumption, name="Property tax growth")

sales_marketing_admin_assumption = Val(
    (
        (initial_period, 0.19),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.192),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.194),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.196),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.198),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.20),
        (Period(date(2022, 12, 31), date.max), 0.20),
    ),
    name="Sales, marketing, and administrative %",
)
sales_marketing_admin_pct = Series.of(
    query.avg(YF.cmonthly),
    sales_marketing_admin_assumption,
    name="Sales, marketing, and administrative %",
)


# Helpers
year_offset = relativedelta(years=1)
month_offset = relativedelta(months=1, day=31)


def growing_line(
    name: str,
    initial: Rule[float],
    growth: Series[Period, float, Maybe[float]],
    q: QueryFn[Period, Maybe[float], Maybe[float]],
    step: relativedelta = year_offset,
) -> Series[Period, Maybe[float], Maybe[float]]:
    @Series[Period, Maybe[float], Maybe[float]].define(q, seed=initial_period, name=name)
    def line(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
        if period == initial_period:
            return period, (yield from get(initial)), period.from_end(step)
        prior = yield from get_at(line, period.from_start(-step))
        g = yield from get_at(growth, period)
        yf = YF.cmonthly(period.start, period.end)
        factor = maybe.sum_some(1.0, maybe.mul_some(g, yf))
        return period, maybe.mul_some(prior, factor), period.from_end(step)

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


# Model definitions
market_rent_psf = growing_line(
    "Market rent PSF", initial_annual_market_rent_psf, rent_growth, query.accrue(YF.cmonthly)
)
market_rent = ops.scale(market_rent_psf, rsf, name="Market rent")
pct_loss_to_lease = Series.of(query.avg(YF.cmonthly), pct_loss_to_lease_assumption, name="Pct loss to lease")
loss_to_lease = ops.mul(market_rent, pct_loss_to_lease, merge_keys=period_union, name="Loss to lease")
total_parking_spaces = Fn(
    lambda: (yield from get(units)) * (yield from get(parking_spaces_per_unit)), name="Total parking spaces"
)
monthly_parking_income = Fn(
    lambda: (yield from get(total_parking_spaces)) * (yield from get(monthly_parking_fee)),
    name="Monthly parking income",
)
initial_annual_parking_income = Fn(
    lambda: (yield from get(monthly_parking_income)) * 12.0, name="Initial annual parking income"
)
annual_parking_income = growing_line(
    "Annual parking income", initial_annual_parking_income, rent_growth, query.accrue(YF.cmonthly)
)
monthly_utility_expense = Fn(
    lambda: (yield from get(units)) * (yield from get(monthly_utility_cost_per_unit)), name="Monthly utility expense"
)
annual_utility_expense_cell = Fn(
    lambda: (yield from get(monthly_utility_expense)) * 12.0, name="Annual utility expense"
)
utility_expense = growing_line("Utility expense", annual_utility_expense_cell, opex_growth, query.accrue(YF.cmonthly))
utility_reimbursements = ops.mul(
    utility_expense, utility_reimbursement_pct, merge_keys=period_union, name="Utility reimbursements"
)
annual_insurance = growing_line("Insurance", initial_annual_insurance, opex_growth, query.accrue(YF.cmonthly))
annual_replacement_reserves = growing_line(
    "Replacement reserves", initial_annual_replacement_reserves, opex_growth, query.accrue(YF.cmonthly)
)
property_taxes = growing_line(
    "Property taxes", initial_annual_property_taxes, property_tax_growth, query.accrue(YF.cmonthly)
)
effective_rent = ops.add(market_rent, loss_to_lease, merge_keys=period_union, name="Effective rent")
bad_debt_concessions_amount = ops.mul(
    effective_rent, bad_debt_concessions, merge_keys=period_union, name="Bad debt and concessions amount"
)
pgr = ops.add(
    market_rent,
    loss_to_lease,
    bad_debt_concessions_amount,
    annual_parking_income,
    utility_reimbursements,
    merge_keys=period_union,
    name="Potential Gross Revenue",
)
vacancy_amount = ops.mul(pgr, vacancy, merge_keys=period_union, name="Vacancy amount")
egi = ops.add(pgr, vacancy_amount, merge_keys=period_union, name="Effective Gross Revenue")
sales_marketing_admin = ops.mul(
    egi,
    sales_marketing_admin_pct,
    merge_keys=period_union,
    name="Sales, marketing, and administrative",
)
management_fee = ops.scale(egi, property_management_fee_pct, name="Property management fee")
total_operating_expenses = ops.add(
    annual_insurance,
    utility_expense,
    annual_replacement_reserves,
    sales_marketing_admin,
    property_taxes,
    management_fee,
    merge_keys=period_union,
    name="Total operating expenses",
)
noi = ops.sub(egi, total_operating_expenses, merge_keys=period_union, name="Net Operating Income")
noi_margin = ops.div(noi, egi, merge_keys=period_union, name="NOI margin")


# Acquisition, reserves, and debt assumptions
acquisition_date = date(2017, 12, 31)
acquisition_period = Period(acquisition_date, acquisition_date + year_offset)
loan_to_value = Val(0.65, name="Acquisition LTV")
senior_debt = Fn(
    lambda: (yield from get(acquisition_price)) * (yield from get(loan_to_value)),
    name="Senior debt",
)
loan_interest_rate = Val(0.05, name="Loan interest rate")
loan_amortization_years = Val(30.0, name="Loan amortization years")
loan_maturity_years = Val(5, name="Loan maturity years")
upfront_reserve_funding = Val(19_000.0, name="Upfront reserve funding")

capex_per_unit_assumption = Val(
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 500.0),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 1_000.0),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 750.0),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.0),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 200.0),
        (Period(date(2022, 12, 31), date.max), 0.0),
    ),
    name="Capital expenditures per unit",
)
capex_per_unit = Series.of(query.accrue(YF.cmonthly), capex_per_unit_assumption, name="Capital expenditures per unit")
capex = ops.neg(ops.scale(capex_per_unit, units, name="Gross capital expenditures"), name="Capital expenditures")


@Series.define(query.accrue(YF.cmonthly), seed=acquisition_period, name="Capex funded by reserves")
def capex_funded_by_reserves(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """Capex paid from the reserve, capped at the beginning balance plus the period's contributions."""
    beginning = yield from get_at(reserve_balance, period.start)
    contributions = yield from get_at(annual_replacement_reserves, period)
    spend = yield from get_at(capex, period)

    def fundable(available: float, outflow: float) -> float:
        return max(0.0, min(available, -outflow))

    funded = maybe.map2_some(fundable)(maybe.sum_some(beginning, contributions), spend)
    return period, funded, period.from_end(year_offset)


reserve_funding = Series[date, Maybe[float], Maybe[float]].of(
    query.exact_or(0.0),
    [(acquisition_date, Thunk(lambda: get(upfront_reserve_funding)))],
    name="Upfront reserve funding",
)


@Series.define(query.exact_or(maybe.some(0.0)), seed=acquisition_period, name="Reserve draws")
def reserve_draws(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post each period's reserve-funded capex as a negative flow on the period end."""
    funded = yield from get_at(capex_funded_by_reserves, period)
    return period.end, maybe.neg_some(funded), period.from_end(year_offset)


reserve_flows = ops.add(reserve_funding, reserve_draws, merge_keys=date_union, name="Reserve flows")


@Series.define(
    accrued_balance(annual_replacement_reserves), seed=acquisition_period, name="Replacement reserve balance"
)
def reserve_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``, rolled forward from the prior period."""
    if period == acquisition_period:
        balance = yield from get_at(reserve_funding, acquisition_date)
    else:
        prior = period.from_start(-year_offset)
        beginning = yield from get_at(reserve_balance, prior.start)
        contributions = yield from get_at(annual_replacement_reserves, prior)
        flow = yield from get_at(reserve_flows, period.start)
        balance = maybe.sum_some(beginning, contributions, flow)
    return period.start, balance, period.from_end(year_offset)


adjusted_noi = ops.add(noi, capex, capex_funded_by_reserves, merge_keys=period_union, name="Adjusted NOI")


# Debt schedule and levered cash flow
@Fn.define(name="Monthly debt service")
def monthly_debt_service() -> Effect[float]:
    principal = yield from get(senior_debt)
    annual_rate = yield from get(loan_interest_rate)
    years = yield from get(loan_amortization_years)
    monthly_rate = annual_rate / 12.0
    months = years * 12.0
    return principal * monthly_rate / (1.0 - (1.0 + monthly_rate) ** -months)


first_loan_month = Period(acquisition_date, acquisition_date + month_offset)


@Series.define(query.last, seed=first_loan_month, name="Loan balance")
def loan_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``; carry it until payment, with zero at maturity."""
    maturity = yield from get(loan_maturity_years)
    if period.start >= acquisition_date + relativedelta(years=maturity):
        return period.start, maybe.some(0.0), period.from_end(month_offset)
    if period.start == acquisition_date:
        return period.start, (yield from get(senior_debt)), period.from_end(month_offset)
    prior_period = period.from_start(-month_offset)
    prior = yield from get_at(loan_balance, prior_period.start)
    payment = yield from get(monthly_debt_service)
    interest = yield from get_at(interest_expense, prior_period)

    def amortize(b: float, i: float) -> float:
        return b - (payment - i)

    return period.start, maybe.map2_some(amortize)(prior, interest), period.from_end(month_offset)


@Series.define(query.accrue(YF.cmonthly), seed=first_loan_month, name="Debt service")
def debt_service(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """One monthly P&I payment while the loan is outstanding, as a negative cash flow."""
    balance = yield from get_at(loan_balance, period.start)
    payment = yield from get(monthly_debt_service)

    def cash_flow(b: float) -> float:
        return -payment if b > 0.0 else 0.0

    return period, maybe.map_some(cash_flow)(balance), period.from_end(month_offset)


@Series.define(query.accrue(YF.cmonthly), seed=first_loan_month, name="Interest expense")
def interest_expense(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """One month of 30/360 interest on the beginning balance."""
    balance = yield from get_at(loan_balance, period.start)
    rate = yield from get(loan_interest_rate)
    return period, maybe.mul_some(balance, rate * 1 / 12), period.from_end(month_offset)


debt_pi = ops.neg(debt_service, name="Debt P&I")
principal_paid = ops.sub(debt_pi, interest_expense, merge_keys=period_union, name="Principal payments")
levered_cash_flow = ops.add(adjusted_noi, debt_service, merge_keys=period_union, name="Levered cash flow")
