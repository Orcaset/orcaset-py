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
initial_monthly_market_rent = Val("Market rent", 1.777777778)
initial_annual_market_rent_psf = Fn(
    "Initial annual market rent PSF",
    lambda: (yield from get(initial_monthly_market_rent)) * 12,
)
initial_monthly_in_place_rent = Val("In-place rent", 1.60)
units = Val("Units", 76.0)
avg_rsf_per_unit = Val("Average RSF per unit", 573.0)
rsf = Fn("RSF", lambda: (yield from get(units)) * (yield from get(avg_rsf_per_unit)))
parking_spaces_per_unit = Val("Parking spaces per unit", 1.13)
monthly_parking_fee = Val("Monthly parking fee", 50.0)
monthly_utility_cost_per_unit = Val("Monthly utility cost per unit", 85.0)

acquisition_price = Val("Acquisition price", 9_775_000.0)
rentable_to_gross_ratio = Val("Rentable to gross ratio", 0.80)
gsf = Fn(
    "Gross square feet",
    lambda: (yield from get(rsf)) / (yield from get(rentable_to_gross_ratio)),
)
annual_insurance_rate_per_gsf = Val("Annual insurance rate per GSF", 0.40)
initial_annual_insurance = Fn(
    "Initial annual insurance",
    lambda: (yield from get(gsf)) * (yield from get(annual_insurance_rate_per_gsf)),
)
annual_replacement_reserve_per_unit = Val("Replacement reserve per unit", 250.0)
initial_annual_replacement_reserves = Fn(
    "Initial annual replacement reserves",
    lambda: (yield from get(units)) * (yield from get(annual_replacement_reserve_per_unit)),
)
property_tax_rate = Val("Property tax rate", 0.0068)
initial_annual_property_taxes = Fn(
    "Initial annual property taxes",
    lambda: (yield from get(acquisition_price)) * (yield from get(property_tax_rate)),
)
property_management_fee_pct = Val("Property management fee %", 0.03)


growth_assumptions = Val(
    "Rent growth assumptions",
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.035),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.035),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.035),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.03),
        (Period(date(2022, 12, 31), date.max), 0.03),
    ),
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


pct_loss_to_lease_assumption = Fn("Pct loss to lease", _pct_loss_to_lease_pairs)

bad_debt_concessions_assumption = Val(
    "Bad debt and concessions",
    (
        (initial_period, -0.03),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), -0.03),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), -0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), -0.02),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), -0.01),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), -0.01),
        (Period(date(2022, 12, 31), date.max), -0.01),
    ),
)

utility_reimbursement_assumption = Val(
    "Utility reimbursement percentage",
    (
        (initial_period, 0.80),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.83),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.86),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.89),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.92),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.95),
        (Period(date(2022, 12, 31), date.max), 0.95),
    ),
)

vacancy_assumption = Val(
    "General vacancy",
    (
        (initial_period, 0.0),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), -0.01),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), -0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), -0.03),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), -0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), -0.03),
        (Period(date(2022, 12, 31), date.max), -0.03),
    ),
)


rent_growth = Series[Period, float, Maybe[float]].of("Rent growth", query.avg(YF.cmonthly), growth_assumptions)
bad_debt_concessions = Series.of(
    "Bad debt and concessions", query.avg(YF.cmonthly), bad_debt_concessions_assumption
)
utility_reimbursement_pct = Series.of(
    "Utility reimbursement percentage", query.avg(YF.cmonthly), utility_reimbursement_assumption
)
vacancy = Series.of("General vacancy", query.avg(YF.cmonthly), vacancy_assumption)

operating_expense_growth = Val(
    "Operating expense growth",
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.03),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.03),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.03),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.03),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.03),
        (Period(date(2022, 12, 31), date.max), 0.03),
    ),
)

opex_growth = Series.of("Operating expense growth", query.avg(YF.cmonthly), operating_expense_growth)

property_tax_growth_assumption = Val(
    "Property tax growth",
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.02),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.02),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.02),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.02),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.02),
        (Period(date(2022, 12, 31), date.max), 0.02),
    ),
)
property_tax_growth = Series.of("Property tax growth", query.avg(YF.cmonthly), property_tax_growth_assumption)

sales_marketing_admin_assumption = Val(
    "Sales, marketing, and administrative %",
    (
        (initial_period, 0.19),
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 0.192),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 0.194),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 0.196),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.198),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 0.20),
        (Period(date(2022, 12, 31), date.max), 0.20),
    ),
)
sales_marketing_admin_pct = Series.of(
    "Sales, marketing, and administrative %",
    query.avg(YF.cmonthly),
    sales_marketing_admin_assumption,
)


# Helpers
year_offset = relativedelta(years=1)


def growing_line(
    name: str,
    initial: Rule[float],
    growth: Series[Period, float, Maybe[float]],
    step: relativedelta = year_offset,
) -> Series[Period, Maybe[float], Maybe[float]]:
    @Series[Period, Maybe[float], Maybe[float]].define(name, query.avg(YF.cmonthly), seed=initial_period)
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
market_rent_psf = growing_line("Market rent PSF", initial_annual_market_rent_psf, rent_growth)
market_rent = ops.scale("Market rent", market_rent_psf, rsf)
pct_loss_to_lease = Series.of("Pct loss to lease", query.avg(YF.cmonthly), pct_loss_to_lease_assumption)
loss_to_lease = ops.mul("Loss to lease", market_rent, pct_loss_to_lease, merge_keys=period_union)
total_parking_spaces = Fn(
    "Total parking spaces", lambda: (yield from get(units)) * (yield from get(parking_spaces_per_unit))
)
monthly_parking_income = Fn(
    "Monthly parking income", lambda: (yield from get(total_parking_spaces)) * (yield from get(monthly_parking_fee))
)
initial_annual_parking_income = Fn(
    "Initial annual parking income", lambda: (yield from get(monthly_parking_income)) * 12.0
)
annual_parking_income = growing_line("Annual parking income", initial_annual_parking_income, rent_growth)
monthly_utility_expense = Fn(
    "Monthly utility expense", lambda: (yield from get(units)) * (yield from get(monthly_utility_cost_per_unit))
)
annual_utility_expense_cell = Fn("Annual utility expense", lambda: (yield from get(monthly_utility_expense)) * 12.0)
utility_expense = growing_line("Utility expense", annual_utility_expense_cell, opex_growth)
utility_reimbursements = ops.mul(
    "Utility reimbursements", utility_expense, utility_reimbursement_pct, merge_keys=period_union
)
annual_insurance = growing_line("Insurance", initial_annual_insurance, opex_growth)
annual_replacement_reserves = growing_line("Replacement reserves", initial_annual_replacement_reserves, opex_growth)
property_taxes = growing_line("Property taxes", initial_annual_property_taxes, property_tax_growth)
effective_rent = ops.add("Effective rent", market_rent, loss_to_lease, merge_keys=period_union)
bad_debt_concessions_amount = ops.mul(
    "Bad debt and concessions amount", effective_rent, bad_debt_concessions, merge_keys=period_union
)
pgr = ops.add(
    "Potential Gross Revenue",
    market_rent,
    loss_to_lease,
    bad_debt_concessions_amount,
    annual_parking_income,
    utility_reimbursements,
    merge_keys=period_union,
)
vacancy_amount = ops.mul("Vacancy amount", pgr, vacancy, merge_keys=period_union)
egi = ops.add("Effective Gross Revenue", pgr, vacancy_amount, merge_keys=period_union)
sales_marketing_admin = ops.mul(
    "Sales, marketing, and administrative",
    egi,
    sales_marketing_admin_pct,
    merge_keys=period_union,
)
management_fee = ops.scale("Property management fee", egi, property_management_fee_pct)
total_operating_expenses = ops.add(
    "Total operating expenses",
    annual_insurance,
    utility_expense,
    annual_replacement_reserves,
    sales_marketing_admin,
    property_taxes,
    management_fee,
    merge_keys=period_union,
)
noi = ops.sub("Net Operating Income", egi, total_operating_expenses, merge_keys=period_union)
noi_margin = ops.div("NOI margin", noi, egi, merge_keys=period_union)


# Acquisition, reserves, and debt assumptions
acquisition_date = date(2017, 12, 31)
acquisition_period = Period(acquisition_date, acquisition_date + year_offset)
loan_to_value = Val("Acquisition LTV", 0.65)
senior_debt = Fn(
    "Senior debt",
    lambda: (yield from get(acquisition_price)) * (yield from get(loan_to_value)),
)
loan_interest_rate = Val("Loan interest rate", 0.05)
loan_amortization_years = Val("Loan amortization years", 30.0)
loan_maturity_years = Val("Loan maturity years", 5)
upfront_reserve_funding = Val("Upfront reserve funding", 19_000.0)

capex_per_unit_assumption = Val(
    "Capital expenditures per unit",
    (
        (Period(date(2017, 12, 31), date(2018, 12, 31)), 500.0),
        (Period(date(2018, 12, 31), date(2019, 12, 31)), 1_000.0),
        (Period(date(2019, 12, 31), date(2020, 12, 31)), 750.0),
        (Period(date(2020, 12, 31), date(2021, 12, 31)), 0.0),
        (Period(date(2021, 12, 31), date(2022, 12, 31)), 200.0),
        (Period(date(2022, 12, 31), date.max), 0.0),
    ),
)
capex_per_unit = Series.of("Capital expenditures per unit", query.accrue(YF.cmonthly), capex_per_unit_assumption)
capex = ops.neg("Capital expenditures", ops.scale("Gross capital expenditures", capex_per_unit, units))


@Series.define("Capex funded by reserves", query.accrue(YF.cmonthly), seed=acquisition_period)
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
    "Upfront reserve funding",
    query.exact_or(0.0),
    [(acquisition_date, Thunk(lambda: get(upfront_reserve_funding)))],
)


@Series.define("Reserve draws", query.exact_or(maybe.some(0.0)), seed=acquisition_period)
def reserve_draws(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post each period's reserve-funded capex as a negative flow on the period end."""
    funded = yield from get_at(capex_funded_by_reserves, period)
    return period.end, maybe.neg_some(funded), period.from_end(year_offset)


reserve_flows = ops.add("Reserve flows", reserve_funding, reserve_draws, merge_keys=date_union)


@Series.define("Replacement reserve balance", accrued_balance(annual_replacement_reserves), seed=acquisition_period)
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


adjusted_noi = ops.add("Adjusted NOI", noi, capex, capex_funded_by_reserves, merge_keys=period_union)


# Debt schedule and levered cash flow
@Fn.define("Annual debt service")
def annual_debt_service() -> Effect[float]:
    principal = yield from get(senior_debt)
    rate = yield from get(loan_interest_rate)
    years = yield from get(loan_amortization_years)
    return principal * rate / (1.0 - (1.0 + rate) ** -years)


@Series.define("Loan balance", query.last, seed=acquisition_period)
def loan_balance(period: Period) -> Effect[tuple[date, Maybe[float], Period]]:
    """Post the balance at ``period.start``; carry it until payment, with zero at maturity."""
    maturity = yield from get(loan_maturity_years)
    if period.start >= acquisition_date + relativedelta(years=maturity):
        return period.start, maybe.some(0.0), period.from_end(year_offset)
    if period == acquisition_period:
        return period.start, (yield from get(senior_debt)), period.from_end(year_offset)
    prior = yield from get_at(loan_balance, period.from_start(-year_offset).start)
    service = yield from get(annual_debt_service)
    rate = yield from get(loan_interest_rate)

    def amortize(b: float) -> float:
        return b - (service - b * rate)

    return period.start, maybe.map_some(amortize)(prior), period.from_end(year_offset)


@Series.define("Debt service", query.accrue(YF.cmonthly), seed=acquisition_period)
def debt_service(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """Annual P&I paid while the loan is outstanding, as a negative cash flow."""
    balance = yield from get_at(loan_balance, period.start)
    service = yield from get(annual_debt_service)

    def payment(b: float) -> float:
        return -service if b > 0.0 else 0.0

    return period, maybe.map_some(payment)(balance), period.from_end(year_offset)


@Series.define("Interest expense", query.accrue(YF.cmonthly), seed=acquisition_period)
def interest_expense(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    """Accrue annual interest on the beginning-of-period loan balance."""
    balance = yield from get_at(loan_balance, period.start)
    rate = yield from get(loan_interest_rate)
    return period, maybe.mul_some(balance, rate), period.from_end(year_offset)


debt_pi = ops.neg("Debt P&I", debt_service)
principal_paid = ops.sub("Principal payments", debt_pi, interest_expense, merge_keys=period_union)
levered_cash_flow = ops.add(
    "Levered cash flow", adjusted_noi, debt_service, merge_keys=period_union
)
