"""Statement presentation: one output statement per scenario."""

from orcaset import Group, Stmt, Total

from .assumptions import SCENARIOS, customer_growth, ndr
from .data import group_keys
from .metrics import customer_groups, total_customers
from .revenue import revenue_groups, total_revenue


def _scenario_stmt(scenario: str) -> Stmt:
    return Stmt(
        # Assumptions
        Group(
            [customer_growth[scenario][group] for group in group_keys]
            + [ndr[scenario][group] for group in group_keys]
        ),
        # Metrics
        Total(total_customers[scenario], [customer_groups[scenario]]),
        # Revenue detail
        Total(total_revenue[scenario], [revenue_groups[scenario]]),
    )


statements: dict[str, Stmt] = {scenario: _scenario_stmt(scenario) for scenario in SCENARIOS}
