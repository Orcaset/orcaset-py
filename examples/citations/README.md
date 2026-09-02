# Citations and Data Provenance

This example fetches SpaceX Q2 2026 revenue from the SEC company-concept API, wraps
the sourced leaf in a `CitedFloat`, and grows it 10% per quarter.

The linked list is built with `Series.unfold`. The first node contains a `Thunk` that
performs the HTTP request only when its value is demanded; later nodes contain thunks
that query the preceding quarter. Arithmetic converts the cited subclass to a normal
`float`, while `Context.dependencies` preserves the path back to the cited leaf.

```py
revenue = Series.unfold(
    "SpaceX revenue",
    accrual(YF.cmonthly),
    seed=Q2_2026,
    step=revenue_step,
)
```

## Run

Python 3.14+ and network access to `data.sec.gov` are required.

```sh
uv run python examples/citations/main.py
```
