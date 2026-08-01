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

## Orcaset at a glance

The code block below builds a simple model with revenue, costs, and profit.

<!-- fmt: off -->
```py
from datetime import date
from dateutil.relativedelta import relativedelta
from itertools import islice
from orcaset import (
    YF, Context, Series, Map2Series, Period, Stmt, Total, 
    accrual, fixed_width_table, get_at, isna, map2_some, period_union,
)

# Define the model
@Series.define("revenue", accrual(YF.cmonthly))
def revenue():
    # Generator of (Period, value_function) pairs over time
    def cells():
        for k in Period.seq(date(2026, 1, 1), relativedelta(months=1)):

            # value_function factory
            def value(p: Period = k):
                # Get the prior month's revenue
                prior = yield from get_at(revenue, p.shift(-relativedelta(months=1)))
                # Return the prior month's revenue * 10% growth rate, 
                # or initial revenue of 100 if prior is Na
                return prior * 1.10 if not isna(prior) else 100.0

            yield k, value

    return cells()

costs = revenue.map("Costs", lambda r: r * -0.50 if not isna(r) else r)
profit = Map2Series(
    "Profit", revenue, costs, map2_some(lambda r, c: r + c), merge_keys=period_union
)

# Materialize, format and print output
ctx = Context()
periods = list(islice(Period.seq(date(2026, 1, 1), relativedelta(months=1)), 4))
statement = Stmt(Total(profit, [revenue, costs])).values_for_periods(ctx, periods)
print(fixed_width_table(statement))

# Start                  2026-01-01  2026-02-01  2026-03-01  2026-04-01
# End        2026-01-01  2026-02-01  2026-03-01  2026-04-01  2026-05-01
#   revenue                  100.00      110.00      121.00      133.10
#   Costs                    -50.00      -55.00      -60.50      -66.55
# ---------------------------------------------------------------------
# Profit                      50.00       55.00       60.50       66.55
```

> *This code block is complete and can be run standalone.*

<br>
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
