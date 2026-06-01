# Quickstart

This example builds a small recursive model with span series for interest accruals and a point series for ending balance.

Series are immutable definition objects. They do not need `ctx.get(...)`; pass an explicit `Context` to `.query(...)` or `.value(...)`.

```py
@span.define(agg=sum_spans(0.0), label="Interest")
def Interest(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(start_date, relativedelta(months=3, day=31)):
        yield Span(
            period=period,
            fn=Balance.value(ctx, period.start) * interest_rate / 4,
            split=split_daily,
        )


@point.define(label="Balance")
def Balance(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < start_date:
        return Formula.pure(None)
    if dt == start_date:
        return Formula.pure(initial_balance)
    return initial_balance + Interest.value(ctx, Period(start_date, dt))
```

Resolve values with a context:

```py
ctx = Context()
period = Period(date(2025, 12, 31), date(2026, 3, 31))

interest_value = Interest.value(ctx, period).eval()
balance_value = Balance.value(ctx, period.end).eval()
interest_spans = Interest.query(ctx, period).eval()
balance_cell = Balance.query(ctx, period.end)
```

`Context` owns evaluation state, caches, dependency tracking, and recursive cell solving. The series definitions are plain immutable objects and can be combined with helpers:

```py
Balance2 = point.accumulate(start_date, initial_balance, Interest, label="Balance 2")

PreTaxIncome = span.sum([OperatingIncome, Interest], agg=sum_spans(0.0), label="Pre-Tax Income")
Taxes = span.scale(PreTaxIncome, -0.25, label="Taxes")
NetIncome = span.sum([PreTaxIncome, Taxes], agg=sum_spans(0.0), label="Net Income")
```

Run the full example:

```sh
uv run python examples/quickstart/main.py
```
