# Series composition and continuations

## Choose the composition level

- `Series.flatten` joins series while preserving each component's query function. Use it for actuals that reject partial periods followed by projections that permit interpolation.
- `continue_series` builds a base-plus-continuation chain for `flatten` when the next series depends on the base's final node.
- `Series.extend` joins raw cell chains under one query function. Use it when that shared policy is intentional.
- `ops` combines answers at the same query key; it does not select successive timeline segments.

## Join component series

```python
components = Series.of("Revenue components", exact, [(0, actuals), (1, projections)])
base = Series.flatten(
    "Actuals and projections",
    components.cells,
    query=covered,
    split_keys=period_split,
)
```

Outer integer keys specify component order, not dates or domain bounds. Components share key and query-answer types, but their raw cell-value types may differ. Flattened cells store component query answers: components answering `Maybe[float]` produce a `Series[Period, Maybe[float], Maybe[float]]`. Prefer inferred component types rather than adding `Any` annotations to model code.

A query within one component delegates to that series unchanged. A crossing query is split at component seams, and the outer `query` folds the component answers. `covered` sums period answers and propagates `Na`; it does not impose its interpolation policy inside a component. Use `exact` to reject crossing queries. Use `period_split` for period keys and `date_split` for date keys.

Earlier components own their domain through their last key. Later overlapping keys are clipped at the seam, and their values query the original component on the clipped key. Empty or fully clipped components are skipped. A gap after a seam belongs to the next component; its query policy determines the answer. The first and last nonempty components also answer queries outside the combined spine. Flattening does not itself fill gaps or replace missing values.

## Construct a continuation lazily

`continue_series(name, base, cont)` returns two components: `base` and a lazy `cont(last_node)`. The callback receives the last raw base `Cons`, or `None` for an empty base, and returns a `Series`. Its construction is memoized per context. For a flattened base, its raw cells already hold query answers.

This pattern starts terminal growth after the last projected month, with `MONTH` preserving month-end boundaries and `accrue_monthly = accrue(YF.cmonthly)`:

```python
def terminal_revenue(
    last_node: Cons[Period, Maybe[float]] | None,
) -> Series[Period, Maybe[float], Maybe[float]]:
    if last_node is None:
        return Series.of("Terminal growth", accrue_monthly, [])

    @Series.define("Terminal growth", accrue_monthly, seed=last_node.key)
    def growth(prior_period: Period) -> tuple[Period, Thunk[Maybe[float]], Period]:
        next_period = prior_period.from_end(MONTH)

        def value() -> Effect[Maybe[float]]:
            prior = yield from get_at(revenue, prior_period)
            return multiply_some((prior, 1 + 0.02 * YF.cmonthly(*prior_period)))

        return next_period, Thunk(value), next_period

    return growth


revenue = Series.flatten(
    "Revenue",
    continue_series("Revenue components", base, terminal_revenue),
    query=covered,
    split_keys=period_split,
)
```

The self-reference is deferred until `revenue` exists. Each new month reads the previous month, eventually reaching explicit projections. Keep those reads inside `Thunk` when only values, not the generated domain, depend on them. A reference to the same output period would create a cycle.

Flatten walks the base before requesting the next component. An infinite base never constructs its continuation; `Na` is a value, not exhaustion. Do not eagerly request the outer tail returned by `continue_series`: doing so exhausts the base to find its last node. Handle an empty base explicitly according to the model's intended behavior.

## Extend raw cells under one query

```python
combined = Series.extend(
    "Revenue",
    covered,
    base=history.cells,
    cont=forecast_cells,
)
```

`forecast_cells(last)` receives the last base `Cons`, or `None`, and returns `Cells` with the same key and raw value types. Use `last.key` to start the continuation and `yield from get(last.cell)` inside a deferred computation to read its value. A fixed continuation is `cont=lambda _: then.cells`.

The callback runs only when the base chain is exhausted. Keys must remain strictly ascending across the seam; an overlapping continuation raises `ValueError`. Unlike `flatten`, `extend` does not clip overlap or retain the source series' query functions. `extend_cells` exposes the same operation as a raw chain.

## Check the seams

Verify queries within each segment, partial periods on both sides, and a crossing query. To isolate unsupported actuals interpolation, cross into a known projection period rather than one already containing `Na`. Also check overlap precedence, gaps, an empty base, and that an infinite base leaves the continuation untouched. Trace terminal growth back to the last explicit projection.
