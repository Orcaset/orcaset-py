# Typed Units

This example shows that `Series` values can be domain-specific types rather than plain
numbers. `USD` and `EUR` are distinct immutable values whose addition methods accept
only the same currency.

A generic `ops.period.map2` call merges the two linked domains and applies a typed binary
function. The deliberately invalid USD-plus-EUR expression is rejected by
`pyrefly`, and evaluating the final line raises `TypeError`. That error is expected.

## Run

```sh
uv run python examples/typed-units/main.py
```
