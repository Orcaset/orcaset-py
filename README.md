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
from orcaset import YF, Period, Series, get_at, maybe, ops, period_union, query

initial_period = Period(date(2026, 1, 1), date(2026, 2, 1))

@Series.define("Revenue", query.accrue(YF.cmonthly), seed=initial_period)
def revenue(period: Period):
    if period == initial_period:
        value = 100.0
    else:
        prior_value = yield from get_at(revenue, period.shift(-relativedelta(months=1)))
        value = maybe.mul_some(prior_value, 1.10)
    
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
from orcaset import Context, Stmt, Total, fixed_width_table

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
# Get a node's full dependency tree
print(ctx.dependencies(costs, Period(date(2026, 1, 1), date(2026, 2, 1))))
# Costs@Period(2026-01-01, 2026-02-01) = -50.0
#   Revenue@Period(2026-01-01, 2026-02-01) = 100.0

# Ask whether one cell reached another
q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
jan = Period(date(2026, 1, 1), date(2026, 2, 1))
print(ctx.depends_on((profit, q1), (revenue, jan)))
# True

# Get the dependency path between to nodes, if any
nodes = [node for node in ctx.path_to((profit, q1), (revenue, jan)) or ()]
print(" > ".join(str(node) for node in nodes))
# Profit@Period(2026-01-01, 2026-04-01) = 165.5 > Revenue@Period(2026-01-01, 2026-04-01) = 331.0 > Revenue@Period(2026-01-01, 2026-02-01) = 100.0

```
<!-- fmt: on -->
See the demo scripts in the [examples](./examples) folder for additional review.

For horizontal composition with different query rules, see
[series of series](./examples/flatten-series). `Series.flatten` preserves
each component's queries and supports infinite domains; `continue_series`
adds terminal growth only if a base series eventually ends.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
