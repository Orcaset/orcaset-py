# Assumptions and value types

## Adjustable assumptions

Use `Cell` for any scalar that must be adjustable between context runs: a
sensitivity axis, scenario input, user-entered value, or assumption explicitly
required to change without rebuilding the graph. Growth, margins, tax rates,
multiples, interest rates, and opening balances commonly meet that test.

A literal fixed by the requested specification and not exposed for scenarios
may remain a plain module constant. Do not reflexively wrap every number in a
`Cell`: doing so can replace a simple same-query series expression with an
unnecessary custom cell stream. If the fixed literal later becomes adjustable,
refactor it deliberately and add a fresh-context scenario test.

```python
growth = Cell("Revenue growth", lambda: 0.08)

def factory(p: Period = period) -> Step[float]:
    prior = yield from get_at(revenue, p.shift(-YEAR))
    rate = yield from get(growth)
    if isna(prior):
        raise ValueError(f"missing prior revenue for {p}")
    return prior * (1 + rate)
```

Do not read a separate global float when the exported `Cell` is intended to
control the formula. Do not mutate a context cache or create helper functions
that rebuild hard-coded outputs.

For a scenario, replace the cell's public function and resolve the model in a
fresh context:

```python
growth.fn = lambda: scenario_growth
scenario = Context()
answer = scenario.get_at(target, key)
```

A context intentionally preserves values already resolved within that run.
Use a separate context per scenario or sensitivity point.

## Values with units

Series values need not be bare floats. Use explicit immutable value types when
unit errors would be material—for example currency, shares, energy, or rates.
Define only economically valid arithmetic and annotate combiners precisely so
the type checker rejects incompatible operations.

```python
@dataclass(frozen=True, slots=True)
class USD:
    amount: float

    def __add__(self, other: USD) -> USD:
        if not isinstance(other, USD):
            return NotImplemented
        return USD(self.amount + other.amount)
```

Use `map`/`map2` with typed functions for rich values. Do not unwrap to floats
early merely to make series arithmetic convenient; convert deliberately at a
well-defined boundary.

## Values with citations

A sourced value may carry immutable citation metadata such as document,
filing, page, URL, retrieval date, or table coordinates. Arithmetic may either
preserve that metadata in a domain-specific type or produce an ordinary value;
derived provenance still remains inspectable through Orcaset dependency edges.

Keep source fetching or parsing separate from graph construction where
practical. Place the sourced rich value in a leaf cell, then make all derived
formulas demand that cell. Validate both the leaf metadata and a dependency
trace from a representative derived answer back to the source.
