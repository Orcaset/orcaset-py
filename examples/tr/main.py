from datetime import date

from dateutil.relativedelta import relativedelta
from model import total_assets, bs_stmt, total_liabilities_and_equity, cf_stmt, income_stmt
from orcaset import Context, Group, Period, Stmt, Total, fixed_width_table, point

query_periods = Period.list(date(2024, 12, 31), relativedelta(months=3, day=31), date(2026, 12, 31))


def number_format(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1000:,.0f}"


# Statement ouput
ctx = Context()
stmt = Stmt(Group([income_stmt, cf_stmt, bs_stmt]))
print(fixed_width_table(stmt.values(ctx, query_periods), value_formatter=number_format))

# Balance sheet check
print("BALANCE SHEET CHECK" + "\n" + "-" * 20)
assets_less_liabilities = point.sub(
    total_assets,
    total_liabilities_and_equity,
    label="Assets less liabilities and equity",
)
check = Stmt(Total(assets_less_liabilities, [total_assets, total_liabilities_and_equity]))
print(fixed_width_table(check.values(ctx, query_periods), value_formatter=number_format))
