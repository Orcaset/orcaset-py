# Typed Units

This example demonstrates that series values are not limited to plain numbers. Domain-specific value types can make invalid financial operations visible to a static type checker and fail clearly at runtime.

## How It Works

`USD` and `EUR` are distinct immutable value types whose addition methods accept only the same currency. That constraint is both a static type check and a runtime guarantee: `USD.__add__` requires another `USD`, and adding a different type returns `NotImplemented`. The series type parameter carries the unit, so a `Series` of `USD` and a `Series` of `EUR` are different types.

### Permitted Composition

The `usd_total` series sums the two USD revenue sub-series. The `operator.add` function is the standard library function name for the `+` operator. The `ops.map2` combinator, like all the other combinators, uses generic types to confirm that the component series and the value combination function are all compatible. Since adding two `USD` values is permitted, there are no errors.

```py
usd_total = ops.map2(
    "USD total",
    usd_product,  # USD
    usd_services,  # USD
    fn=map2_some(operator.add),
    merge_keys=period_union,
)
```

### Invalid Composition

Attempting to added series with incompatible value types raises errors. 

```py
invalid_total = ops.map2(
    "invalid total",
    usd_product,  # USD
    eur_revenue,  # EUR
    fn=map2_some(operator.add),  # static type error here
    merge_keys=period_union,
)
```
In this example, `pyrefly` will raise an error at the `operator.add` location noting that it USD and EUR are incompatible operands.

```txt
ERROR Overload type was not compatible with solved type variables: A = USD, B = EUR, C = _NaType
```

Orcaset recommends using `pyrefly` for type checking since it has the best type checking coverage and is fast. Other type checkers may not be able to consistently infer the type error. Even if the static type error is not found though, it will fail at runtime.

```py
try:
    print(f"{invalid_total.name}: {ctx.get_at(invalid_total, january)}")
except TypeError:
    print("ERROR: Cannot add USD and EUR.")
# ERROR: Cannot add USD and EUR.
```

The runtime error will be raised when the addition is invoked, not when the `invalid_total` series is created.

## Run

From the repository root:

```sh
uv run python examples/typed-units/main.py
```

Running the script prints the output below.

```txt
USD product revenue: USD(amount=100.0)
USD services revenue: USD(amount=25.0)
USD total: USD(amount=125.0)
EUR revenue: EUR(amount=80.0)
ERROR: Cannot add USD and EUR.
```