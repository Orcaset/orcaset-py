from datetime import date

from dateutil.relativedelta import relativedelta
from model.assumptions import SCENARIOS
from model.statements import scenario_stmt

from orcaset import Context, Period, fixed_width_table

# Display the last year of historicals plus the forecast through 2028, quarterly.
query_periods = Period.list(date(2024, 12, 31), relativedelta(months=3, day=31), date(2027, 12, 31))


def format_value(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f}m"
    return f"{value:,.2f}"


# for scenario in SCENARIOS:
for scenario in SCENARIOS:
    ctx = Context()
    print(f"\n{scenario.upper()} CASE\n")
    result = scenario_stmt(scenario).values(ctx, query_periods)
    print(fixed_width_table(result, value_formatter=format_value))
    print()
