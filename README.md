# Orcaset — Financial Models for Computers

`orcaset` builds financial statement models as code, making it easy for agents to build verifiable, open, and scalable analysis.

The framework helps agents write correct models quickly. Strong typing surfaces incorrect relationships at write time rather than silently failing or raising exceptions at runtime. It also gives formulas clear semantic meaning by building dependencies from named `get_at(line_item, period)` effect handlers rather than anonymous `A1:B2` address references.

Install with `uv` or `pip`:

```sh
uv add git+https://github.com/orcaset/orcaset-py
```

```sh
pip install git+https://github.com/orcaset/orcaset-py
```

*This library has experimental status and the API is subject to breaking changes.*

## Overview

The code block below builds a simple model with revenue, costs, and profit.

> *This code block is complete and can be run standalone.*

<!-- fmt: off -->
```py
from datetime import date
from dateutil.relativedelta import relativedelta
from itertools import islice
from orcaset import (
    YF, Context, GridSeries, Map2Series, Maybe, Period, accrual, get_at, isna, map2_some, period_union,
)

# MODEL DEFINITION
@GridSeries.define("revenue", accrual(YF.cmonthly))
def revenue():
    # Define a generator of (Period, value) pairs over time
    def cells():
        for k in Period.seq(date(2026, 1, 1), relativedelta(months=1)):

            def factory(p: Period = k):
                # Get the prior month's revenue
                prior = yield from get_at(revenue, p.shift(-relativedelta(months=1)))
                # Return the prior month's revenue * 10% growth rate, or initial revenue of 100 if prior is Na
                return prior * 1.10 if not isna(prior) else 100.0

            yield k, factory

    return cells()

costs = revenue.map("Costs", lambda r: r * -0.50 if not isna(r) else r)
profit = Map2Series(
    "Profit", revenue, costs, map2_some(lambda r, c: r + c), merge_keys=period_union
)

# MATERIALIZE AND PRINT OUTPUTS
ctx = Context()

def maybe_fmt(val: Maybe[float]) -> str:
    return "Na" if isna(val) else f"{val:.2f}"


for p in islice(Period.seq(date(2026, 1, 1), relativedelta(months=1)), 4):
    rev = ctx.get_at(revenue, p)
    cst = ctx.get_at(costs, p)
    prf = ctx.get_at(profit, p)
    print(f"{p}: revenue={maybe_fmt(rev)}, costs={maybe_fmt(cst)}, profit={maybe_fmt(prf)}")

# Period(2026-01-01, 2026-02-01): revenue=100.00, costs=-50.00, profit=50.00
# Period(2026-02-01, 2026-03-01): revenue=110.00, costs=-55.00, profit=55.00
# Period(2026-03-01, 2026-04-01): revenue=121.00, costs=-60.50, profit=60.50
# Period(2026-04-01, 2026-05-01): revenue=133.10, costs=-66.55, profit=66.55
```
<!-- fmt: on -->

`orcaset` uses effect handlers to trace calculation dependencies and memoize values.

```py
# Print the dependency tree for January 2026 costs
print(ctx.dependencies(costs, Period(date(2026, 1, 1), date(2026, 2, 1))))

# Costs@Period(2026-01-01, 2026-02-01) = -50.0
#   revenue@Period(2026-01-01, 2026-02-01) = 100.0
#     revenue.cells = <orcaset.series.Replayable object at 0x1017bcec0>
#     revenue@Period(2026-01-01, 2026-02-01) = 100.0
#       revenue@Period(2025-12-01, 2026-01-01) = Na
#         revenue.cells = <orcaset.series.Replayable object at 0x1017bcec0>
```

See the demo scripts in the [examples](./examples) folder.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
