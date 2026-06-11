from dataclasses import dataclass, field

from orcaset import Context


@dataclass(frozen=True)
class IncomeAssumptions:
    product_sales_growth_rate: float = 0.05
    rental_revenue_growth_rate: float = 0.05
    product_cogs_margin: float = 0.50
    rental_cogs_margin: float = 0.50
    sga_growth_rate: float = 0.05
    other_income_growth_rate: float = 0.05
    income_tax_rate: float = 0.25
    nci_net_income_rate: float = -0.005


@dataclass(frozen=True)
class PPEAssumptions:
    # Share of capex allocated to buildings; derived from historical gross
    # balance growth when None.
    building_capex_share: float | None = None
    buildings_useful_life_years: float = 35
    machinery_useful_life_years: float = 12


@dataclass(frozen=True)
class Assumptions:
    income: IncomeAssumptions = field(default_factory=IncomeAssumptions)
    ppe: PPEAssumptions = field(default_factory=PPEAssumptions)


DEFAULT_ASSUMPTIONS = Assumptions()


class ModelContext(Context):
    """Evaluation context carrying the assumption set used to resolve the model.

    Series definitions stay static; formulas read assumptions through the
    context at evaluation time, so each `ModelContext` evaluates the model
    under its own scenario with its own caches.
    """

    def __init__(self, assumptions: Assumptions = DEFAULT_ASSUMPTIONS) -> None:
        super().__init__()
        self.assumptions = assumptions


def get_assumptions(ctx: Context) -> Assumptions:
    """Assumptions for `ctx`, falling back to defaults for a plain `Context`."""
    if isinstance(ctx, ModelContext):
        return ctx.assumptions
    return DEFAULT_ASSUMPTIONS
