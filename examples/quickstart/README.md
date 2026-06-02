# Quickstart

This example builds a small recursive model with span series for interest accruals and a point series for ending balance.

Series are immutable definition objects. They do not need `ctx.get(...)`; pass an explicit `Context` to `.query(...)` or `.value(...)`.

```py
@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(start_date, relativedelta(months=3, day=31)):
        yield Span(
            period=period,
            fn=balance.value(ctx, period.start) * interest_rate / 4,
            split=split_daily,
        )


@point.define(label="Balance")
def balance(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < start_date:
        return Formula.pure(None)
    if dt == start_date:
        return Formula.pure(initial_balance)
    return initial_balance + interest.value(ctx, Period(start_date, dt))
```

Resolve values with a context:

```py
ctx = Context()
period = Period(date(2025, 12, 31), date(2026, 3, 31))

interest_value = interest.value(ctx, period).eval()
balance_value = balance.value(ctx, period.end).eval()
interest_spans = interest.query(ctx, period).eval()
balance_cell = balance.query(ctx, period.end)
```

`Context` owns evaluation state, caches, dependency tracking, and recursive cell solving. The series definitions are plain immutable objects and can be combined with helpers:

```py
balance_2 = point.accumulate(start_date, initial_balance, interest, label="Balance 2")

pre_tax_income = span.sum([operating_income, interest], agg=sum_spans(0.0), label="Pre-Tax Income")
taxes = span.scale(pre_tax_income, -0.25, label="Taxes")
net_income = span.sum([pre_tax_income, taxes], agg=sum_spans(0.0), label="Net Income")
```

Run the full example:

```sh
uv run python examples/quickstart/main.py
```
