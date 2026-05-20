# Orcaset — Financial Models for Computers

> *This library is in experimental status and the API is likely to change.*

Orcaset is built for financial analysis by agents. It uses type annotations and runtime safety checks to prevent users and agents from accidentally creating malformed models. Strong protections give end users confidence that large-scale modifications do not cause hidden errors.

* Build and Update with Confidence - Strong typing prevents invalid models and helps agents navigate deep formula dependencies. Confidently modify models without breaking them.
* Transparent and Deterministic - Calculations are open and transparent. Materialize and inspect query-specific traces to audit model calculations. No black boxes.
* Efficient Construction - Faster insight. Reuse components across models and scenarios. Save tokens by writing formulas once per line item, not once per cell.

## Installation

Install from GitHub with `uv` or `pip`:

```sh
uv add git+https://github.com/orcaset/orcaset-py
```

```sh
pip install git+https://github.com/orcaset/orcaset-py
```

Requires Python 3.14 or later.

## Orcaset at a glance

Orcaset models are constructed by defining and combining line item classes. Values are materialized by querying over dates, with caching and circular references handled by the evaluation context.

This code snippet creates a simple model with revenue, expenses, and income.

```py
# Define Assumptions
start_date = date(2025, 12, 31)
initial_revenue = 100.0
revenue_growth_rate = 0.05


# Define Model
class Revenue(SpanSeries):
    def spans(self) -> Iterable[Span]:
        value = initial_revenue
        for period in Period.seq(start_date, relativedelta(months=1, day=31)):
            yield Span(period, Formula.pure(value), split_daily)
            value *= 1 + revenue_growth_rate / 12


Expenses = Revenue * -0.7
Income = Revenue + Expenses
```

Values can be queried over any range of dates. This snippet queries the model for total 2026 income.

```py
# Query Model
ctx = Context()
cy_2026 = Period(start_date, date(2026, 12, 31))

print(ctx.get(Income).query(cy_2026).map(sum_spans(0.0)).eval())
# 368.36566474847893
```

See the [quickstart example](./examples/quickstart/README.md) for a more detailed guide to using Orcaset.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
