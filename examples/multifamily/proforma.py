from datetime import date

from dateutil.relativedelta import relativedelta
from orcaset import Context, Period, formatter, ops, stmt

from model import (
    adjusted_noi,
    annual_insurance,
    annual_parking_income,
    annual_replacement_reserves,
    bad_debt_concessions,
    bad_debt_concessions_amount,
    capex,
    capex_funded_by_reserves,
    debt_pi,
    debt_service,
    egi,
    interest_expense,
    levered_cash_flow,
    loan_balance,
    loss_to_lease,
    management_fee,
    market_rent,
    market_rent_psf,
    noi,
    noi_margin,
    opex_growth,
    pct_loss_to_lease,
    pgr,
    principal_paid,
    property_tax_growth,
    property_taxes,
    rent_growth,
    reserve_balance,
    reserve_flows,
    sales_marketing_admin,
    sales_marketing_admin_pct,
    total_operating_expenses,
    utility_expense,
    utility_reimbursement_pct,
    utility_reimbursements,
    vacancy,
    vacancy_amount,
)

assumptions = stmt.Group(
    rent_growth,
    pct_loss_to_lease,
    bad_debt_concessions,
    utility_reimbursement_pct,
    vacancy,
    opex_growth,
    sales_marketing_admin_pct,
    property_tax_growth,
)
details = stmt.Group(
    market_rent_psf,
    reserve_flows,
    reserve_balance,
    stmt.Group(
        stmt.Total(
            debt_pi,
            [
                interest_expense,
                principal_paid,
            ],
        ),
        loan_balance,
    ),
)
pro_forma = stmt.Group(
    stmt.Total(
        egi,
        [
            stmt.Total(
                pgr,
                [
                    market_rent,
                    loss_to_lease,
                    bad_debt_concessions_amount,
                    annual_parking_income,
                    utility_reimbursements,
                ],
            ),
            vacancy_amount,
        ],
    ),
    stmt.Total(
        total_operating_expenses,
        [
            annual_insurance,
            utility_expense,
            annual_replacement_reserves,
            sales_marketing_admin,
            property_taxes,
            management_fee,
        ],
    ),
    stmt.Total(
        noi,
        [
            egi,
            ops.neg("Less: Operating expenses", total_operating_expenses),
        ],
    ),
    noi_margin,
)
capex_and_reserves = stmt.Total(adjusted_noi, [noi, capex, capex_funded_by_reserves])
levered_cf = stmt.Total(
    levered_cash_flow,
    [
        adjusted_noi,
        debt_service,
    ],
)

proforma = stmt.Stmt(
    assumptions,
    details,
    pro_forma,
    capex_and_reserves,
    levered_cf,
)


# Output
periods = Period.list(date(2016, 12, 31), relativedelta(years=1), date(2023, 12, 31))

ctx = Context()
print(formatter.fixed_width_table(proforma.values_for_periods(ctx, periods)))
