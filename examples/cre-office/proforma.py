"""Render the lease, operating, reserve, and debt schedules for CY 2026–CY 2032 as HTML."""

from datetime import date

from dateutil.relativedelta import relativedelta
from orcaset import Context, Period, ops, stmt

import html_formatter
import operating_model as m

assumptions = stmt.Group(*(t.rent_growth for t in m.leases))
lease_schedules = stmt.Group(
    *(
        stmt.Group(
            t.area,
            t.rent_psf,
            t.rent,
            t.turnover_vacancy,
            t.free_rent,
            t.improvements,
            t.commissions,
            t.reimbursements,
        )
        for t in m.leases
    )
)
operating_proforma = stmt.Group(
    m.occupied_rsf,
    m.vacant_rsf,
    stmt.Total(m.base_rent, [*(t.rent for t in m.leases), m.potential_vacant_rent]),
    stmt.Total(
        m.pgr,
        [
            m.base_rent,
            ops.neg("Less: turnover vacancy", m.turnover_vacancy),
            ops.neg("Less: free rent", m.free_rent),
            m.reimbursements,
        ],
    ),
    stmt.Total(m.egi, [m.pgr, ops.neg("Less: general vacancy", m.potential_vacant_rent)]),
    stmt.Total(
        m.operating_expenses,
        [
            m.cam,
            m.utilities,
            m.insurance,
            m.property_taxes,
            m.reserve_contributions,
            m.management_fee,
        ],
    ),
    stmt.Total(m.noi, [m.egi, ops.neg("Less: operating expenses", m.operating_expenses)]),
    ops.scale("NOI margin (%)", m.noi_margin, 100.0),
    stmt.Total(
        m.adjusted_noi,
        [
            m.noi,
            ops.neg("Less: tenant improvements", m.tenant_improvements),
            ops.neg("Less: leasing commissions", m.leasing_commissions),
            m.reserve_funded_capex,
        ],
    ),
    ops.scale("Adjusted NOI margin (%)", m.adjusted_noi_margin, 100.0),
)
reserves = stmt.Group(m.reserve_balance, m.reserve_contributions, m.reserve_funded_capex)
debt = stmt.Group(
    m.senior_balance,
    m.senior_interest,
    m.principal_paid,
    m.senior_ending,
    m.mezzanine_balance,
    m.mezzanine_interest,
    m.mezzanine_pik,
    m.mezzanine_ending,
    m.total_debt_balance,
    stmt.Total(m.levered_cash_flow, [m.adjusted_noi, m.debt_service]),
)
proforma = stmt.Stmt(assumptions, lease_schedules, operating_proforma, reserves, debt)


if __name__ == "__main__":
    title = "1201 Broadway, New York, NY — USD; CY 2026 actual, CY 2027–CY 2031 forecast, CY 2032 stabilized"
    display_periods = Period.list(
        date(2026, 12, 31), relativedelta(years=1, day=31), date(2032, 12, 31)
    )
    ctx = Context()
    html = html_formatter.html_table(proforma.values_for_periods(ctx, display_periods), title=title)
    with open("proforma.html", "w", encoding="utf-8") as f:
        f.write(html)

    from orcaset import formatter

    print(formatter.fixed_width_table(proforma.values_for_periods(ctx, display_periods)))
