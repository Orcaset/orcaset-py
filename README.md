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

The block below builds a simple model with revenue, costs, and profit in ten lines of code.

```py
from datetime import date
from itertools import islice
from dateutil.relativedelta import relativedelta
from orcaset import YF, Period, Series, accrue, get_at, multiply_some, ops, period_union

initial_period = Period(date(2026, 1, 1), date(2026, 2, 1))

@Series.define("Revenue", accrue(YF.cmonthly), seed=initial_period)
def revenue(period: Period):
    if period == initial_period:
        value = 100.0
    else:
        prior_value = yield from get_at(revenue, period.shift(-relativedelta(months=1)))
        value = multiply_some((prior_value, 1.10))
    
    return period, value, period.from_end(relativedelta(months=1))


costs = ops.scale("Costs", revenue, -0.50)
profit = ops.add("Profit", revenue, costs, merge_keys=period_union)
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
