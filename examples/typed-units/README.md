# Typed Units

This example demonstrates that series values are not limited to plain numbers. Domain-specific value types can make invalid financial operations visible to a static type checker and fail clearly at runtime.

## How It Works

`USD` and `EUR` are distinct immutable value types whose addition methods accept only the same currency. Two `PeriodSeries` objects carry those types. The example deliberately combines them with a USD addition function, illustrating that a type checker rejects the EUR operand instead of allowing a silent cross-currency sum.

Running the example prints each valid currency series and then intentionally raises `TypeError` when the invalid total is evaluated. That final error is the expected result.

## Run

From the repository root:

```sh
uv run python examples/typed-units/main.py
```

## Layout

| File | Role |
| --- | --- |
| [`main.py`](main.py) | Defines the currency types and series, then demonstrates the rejected cross-currency operation. |
