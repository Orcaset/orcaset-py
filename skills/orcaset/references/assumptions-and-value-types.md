# Assumptions and value types

## Adjustable assumptions

Use `Cell` when a scalar must change between model runs without rebuilding the graph: a sensitivity axis, scenario input, user-entered value, or explicitly adjustable opening balance. A value fixed by the specification may remain a plain constant.

```python
growth = Cell("Revenue growth", lambda: 0.08)

def value() -> Effect[float]:
    prior = yield from get_at(revenue, prior_period)
    rate = yield from get(growth)
    if isna(prior):
        raise ValueError(f"missing prior revenue for {prior_period}")
    return prior * (1.0 + rate)
```

Do not read a separate global float when the exported `Cell` is intended to control the formula. Do not wrap every numeric literal reflexively: a fixed factor can use `ops.scale`, while an adjustable unkeyed dependency requires a thunk or rule that demands the cell.

`Cell.fn` is public and may be replaced. Resolve each scenario in a fresh context because a context intentionally memoizes one run:

```python
growth.fn = lambda: scenario_growth
scenario = Context()
answer = scenario.get_at(target, key)
```

Use `KeyedCell` for a one-off keyed function that does not need a series domain. Subclass `Rule` or `KeyedRule` only when computation needs additional state or behavior beyond the public function wrappers.

## Values with units

Series cells and answers need not be bare floats. Use immutable value types when unit mistakes would be material—for example currency, shares, energy, or rates. Define only valid arithmetic so the type checker rejects incompatible relationships.

```python
@dataclass(frozen=True, slots=True)
class USD:
    amount: float

    def __add__(self, other: USD) -> USD:
        if not isinstance(other, USD):
            return NotImplemented
        return USD(self.amount + other.amount)
```

The float arithmetic helpers are specialized to `Maybe[float]`. For rich types, use a typed `ops.map_values` or `ops.map2` function when their `Maybe`-answer contracts fit, or construct a dedicated series/query. Do not unwrap to float merely to make an operation convenient.

## Values with provenance

A sourced value may carry immutable citation metadata such as document, filing, page, URL, retrieval date, or table coordinates. Keep fetching and parsing at a leaf where possible, wrap it in `Thunk`, and make derived formulas demand that cell. This preserves lazy I/O and a dependency path back to the source.

Arithmetic may preserve metadata in a domain type or intentionally produce a plain derived value. Validate the leaf metadata separately from the derived number, then trace a representative result to confirm that provenance remains visible through dependencies.

If an unfold step needs external data to decide the domain itself, perform the read effectfully in the step and carry the parsed structural state forward. If only the value depends on external data, keep the step structural and defer the read in a `Thunk`.
