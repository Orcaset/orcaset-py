# Orcaset — Financial Models for Computers

`orcaset` builds financial statement models as code, making it easy for agents to build verifiable, open, and scalable analysis.

The framework helps agents write correct models quickly. Strong typing surfaces incorrect relationships at write time rather than silently failing or raising exceptions at runtime. It also gives formulas clear semantic meaning by building dependencies from named `get_at(line_item, period)` effect handlers rather than anonymous `A1:B2` address references.

Install with `uv` or `pip`:

```sh
uv add orcaset
```

```sh
pip install orcaset
```

*This library has experimental status and the API is subject to breaking changes.*
<!-- fmt: off -->

## Orcaset at a glance

The block below builds a simple model with revenue, costs, and profit in nine lines of code.

```py
from datetime import date
from dateutil.relativedelta import relativedelta
from itertools import islice
from orcaset import YF, Context, Period, PeriodSeries, Stmt, Total, accrue, fixed_width_table, get_at, isna

@PeriodSeries.define("Revenue", accrue(YF.cmonthly))
def revenue() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    for k in Period.seq(date(2026, 1, 1), relativedelta(months=1)):
        
        # Cell factory for each period
        def factory(p: Period = k):
            prior = yield from get_at(revenue, p.shift(-relativedelta(months=1)))
            # Return the prior month's revenue * 10% growth rate,
            # or initial revenue amount of 100 if prior is Na
            return prior * 1.10 if not isna(prior) else 100.0

        yield k, factory

costs = (revenue * -0.50).named("Costs")
profit = (revenue + costs).named("Profit")
```

This code block is complete and can be run standalone. It builds a dynamic model with the structure:

```txt
  ┌─ Revenue: Initial revenue of 100, growing at 10% annually and compounding monthly
  ├─ Costs:   Constant 50% expense margin
Profit: Sum of Revenue and Costs
```

Model values are queried and resolved in a `Context` that holds the state for a model run in a bounded, inspectable object.

Orcaset also ships a `Stmt` class which can be used to build structured statements formatted into CSV, markdown, fixed-width, or other custom formats.

```py
ctx = Context()
periods = list(islice(Period.seq(date(2026, 1, 1), relativedelta(months=1)), 4))
statement = Stmt(Total(profit, [revenue, costs])).values_for_periods(ctx, periods)
print(fixed_width_table(statement))

# Start                  2026-01-01  2026-02-01  2026-03-01  2026-04-01
# End        2026-01-01  2026-02-01  2026-03-01  2026-04-01  2026-05-01
#   Revenue                  100.00      110.00      121.00      133.10
#   Costs                    -50.00      -55.00      -60.50      -66.55
# ---------------------------------------------------------------------
# Profit                      50.00       55.00       60.50       66.55
```

`orcaset` uses effect handlers to trace calculation dependencies and memoize values within a run context. Dependencies can be inspected through the context object.

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
<!-- fmt: on -->
See the demo scripts in the [examples](./examples) folder for additional review.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
