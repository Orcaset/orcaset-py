from orcaset import Group, point

from .assets import assets_stmt
from .equity import equity_stmt, total_equity
from .liabilities import liabilities_stmt, total_liabilities

total_liabilities_and_equity = point.sum(
    [total_liabilities, total_equity],
    label="Total liabilities and shareholders' equity",
)

bs_stmt = Group(
    [
        *assets_stmt.items,
        *liabilities_stmt.items,
        *equity_stmt.items,
        total_liabilities_and_equity,
    ]
)
