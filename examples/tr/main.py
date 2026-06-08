from dateutil.relativedelta import relativedelta
from datetime import date
from orcaset import Period, fixed_width_table, Context, Stmt, Group
from model.income import income_stmt
from model.cash_flow import cf_stmt


query_periods = Period.list(date(2024, 12, 31), relativedelta(months=3, day=31), date(2026, 12, 31))


def number_format(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1000:,.0f}"


ctx = Context()
stmts = Stmt(Group([income_stmt, cf_stmt]))
print(fixed_width_table(stmts.values(ctx, query_periods), value_formatter=number_format))
