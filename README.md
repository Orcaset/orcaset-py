# Orcaset — Financial Models for Computers

> *This library is in experimental status and the API is likely to change.*

Orcaset is a Python library for building financial models as code. Type annotations catch malformed models at write time, so humans and AI agents can build, modify, and audit large models with confidence.

* **Build and update with confidence** — Strong typing promotes correct models and surfaces relationship dependencies, so you can modify models without breaking them.
* **Flexible integration** — Connect to any data source and embed in existing workflows by leveraging Python's ecosystem.
* **Transparent and deterministic** — No black boxes. Materialize and inspect query-specific traces to audit every calculation.
* **Efficient construction** — Reusable components and terse definitions mean faster iteration and less context rot for agents.

## Installation

Install from GitHub with `uv` or `pip`:

```sh
uv add git+https://github.com/orcaset/orcaset-py
```

```sh
pip install git+https://github.com/orcaset/orcaset-py
```

Requires Python 3.14 or later.

Add the `orcaset-py` skill to your coding agent by pasting in the following command:

```txt
Install the skill from https://github.com/Orcaset/orcaset-py/tree/main/skill/orcaset-py
```

## Orcaset at a glance

Orcaset models are built by defining and combining line item classes. Values are materialized by querying over dates, with caching and circular references handled by the evaluation context.

The snippet below defines a simple model with revenue, expenses, and income, then queries quarterly values through 2026.

```py
from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    SpanSeries,
    Stmt,
    Total,
    fixed_width_table,
    span,
    split_daily,
    sum_spans,
)

# Assumptions
start_date = date(2025, 12, 31)
initial_revenue = 100.0
revenue_growth_rate = 0.05


# Model
class Revenue(SpanSeries):
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        value = initial_revenue
        for period in Period.seq(start_date, relativedelta(months=1, day=31)):
            yield Span(period, Formula.pure(value), split_daily)
            value *= 1 + revenue_growth_rate / 12

Expenses = span.scale(Revenue, -0.7, name="Expenses")
Income = span.sum([Revenue, Expenses], agg=sum_spans(0.0), name="Income")

# Build a statement view
stmt = Stmt(Total(Income, [Revenue, Expenses]))

# Resolve and print formatted values
ctx = Context()
qtrly_periods = Period.list(start_date, relativedelta(months=3, day=31), date(2026, 12, 31))
print(fixed_width_table(stmt.values(ctx, qtrly_periods)))

# Start                   2025-12-31  2026-03-31  2026-06-30  2026-09-30
# End         2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31
#   Revenue                   301.25      305.03      308.86      312.74
#   Expenses                 -210.88     -213.52     -216.20     -218.92
# ----------------------------------------------------------------------
# Income                       90.38       91.51       92.66       93.82
```

Note that `Revenue` is defined on a monthly basis but queried quarterly. Orcaset automatically aligns, interpolates, and aggregates over partial periods.

See the [quickstart example](./examples/quickstart/README.md) for a step-by-step guide covering cells, series, context, and structured output.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
