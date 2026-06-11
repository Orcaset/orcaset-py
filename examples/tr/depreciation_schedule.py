from datetime import date

from dateutil.relativedelta import relativedelta
from model import ppe
from model.assumptions import ModelContext
from orcaset import Period, Stmt, Total, fixed_width_table, span, sum_spans

query_periods = Period.list(date(2026, 3, 31), relativedelta(months=3, day=31), date(2028, 6, 30))
ctx = ModelContext()


def number_format(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1000:,.0f}"


# Capex split into building and machinery additions
additions = span.sum(
    [ppe.building_capex, ppe.machinery_capex],
    agg=sum_spans(0.0),
    label="Total additions",
)
capex_stmt = Stmt(Total(additions, [ppe.building_capex, ppe.machinery_capex]))

# Depreciation by cohort: the existing-pool runoff plus one line per class
# capex cohort through the last query period
cohort_keys = list(ppe.capex_cohort_keys(query_periods[-1]))
building_cohorts = [ppe.building_depreciation_cohorts.get(ctx, key) for key in cohort_keys]
machinery_cohorts = [ppe.machinery_depreciation_cohorts.get(ctx, key) for key in cohort_keys]

depreciation_stmt = Stmt(
    Total(
        ppe.depreciation,
        [
            ppe.existing_depreciation,
            Total(ppe.building_depreciation, building_cohorts),
            Total(ppe.machinery_depreciation, machinery_cohorts),
        ],
    )
)

print("CAPITAL EXPENDITURES" + "\n" + "-" * 20)
print(fixed_width_table(capex_stmt.values(ctx, query_periods), value_formatter=number_format))
print()
print("DEPRECIATION" + "\n" + "-" * 12)
print(
    fixed_width_table(depreciation_stmt.values(ctx, query_periods), value_formatter=number_format)
)
