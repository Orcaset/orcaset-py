# Modeling core

## The graph, not its output

An Orcaset model consists of named `Rule` and `KeyedRule` nodes. `Cell` is an
unkeyed rule; a series is a keyed rule with a lazy domain. A `Context` owns the
resolved-value cache and dependency graph for one run.

Exports that callers must query should therefore remain Orcaset objects. Do
not export a Python container of calculated values or a function that hides a
private context. Do not create a module-level `Context` to build model nodes.

Inside model computation, every upstream read must be an effect:

```python
assumption = yield from get(growth)
prior = yield from get_at(revenue, prior_period)
domain = yield from get(source.keys())
```

Always use `yield from`. Direct iteration is appropriate for constructing a
domain, not for resolving another rule's values. Never add `lru_cache`, a
dictionary cache, or a local running total for values the graph should resolve;
the context already memoizes each rule/key.

## Choose the series surface

- `PeriodSeries`: flows measured over time, such as revenue, expense, capex,
  interest, or cash flow.
- `DateSeries`: stocks measured at a point in time, such as cash, debt, PPE, or
  equity.
- `PeriodExtendSeries` / `DateExtendSeries`: one public series spanning a
  finite base and a later regime.
- `MapItemsSeries`: lazily map every source-domain item to a derived value,
  including a nested series.
- General `Series`: use when query and cell key shapes are not the standard
  period/date surface.

Use ascending, non-duplicated keys. A factory defined inside a loop must bind
its key as a default argument:

```python
for period in periods:
    def factory(p: Period = period) -> Step[float]:
        prior = yield from get_at(revenue, p.shift(-MONTH))
        if isna(prior):
            raise ValueError(f"missing prior revenue for {p}")
        return prior * 1.01

    yield period, factory
```

This is a dependency recurrence. Avoid an imperative `previous` variable or a
closed-form exponent when the economics call for the prior model value: those
approaches bypass the graph and prevent an upstream change from propagating
through the intended edges.

## Compose derived lines

Use Orcaset arithmetic for compatible `Maybe[float]` series:

```python
costs = (revenue * cost_margin).named("Costs")
gross_profit = (revenue + costs).named("Gross profit")
```

This is required whenever the result is the same-query scalar transform or
combination of existing series. A custom `PeriodSeries` whose cells call
`get_at(revenue, p)` merely to multiply by a fixed margin repeats the formula
at every key and is the wrong shape.

Classify each scalar before choosing the graph shape:

- If the specification fixes it, keep it as a plain constant and use series
  arithmetic, as in `costs = (revenue * -0.5).named("Costs")`.
- If callers must vary it between fresh contexts, make it a `Cell`, demand it
  with `get`, and accept the smallest keyed adapter needed to introduce that
  unkeyed dependency. Do not create adjustability that was not requested.

Use `map`, `map2`, `map_some`, or `map2_some` when value types or
missing-value behavior require an explicit function. Create a new cell stream
only when it introduces its own domain, a required `Cell` dependency,
recurrence, cross-key dependency, or genuinely key-specific logic.

Composition must represent an economic dependency. A fixed independent
schedule needs its own cells and domain; do not write `source * 0 + constant`
or `source.map(lambda _: constant)` merely to borrow the source's keys. Such a
shortcut creates a false dependency and can give the independent schedule the
wrong query behavior. Compose that schedule with its peers only downstream.

## Extend a finite base

Use an extension rather than coalescing or manually joining history and
forecast. The base must be finite. A forecast recurrence should normally read
the public extended series, so the same formula crosses the seam naturally:

```python
@PeriodExtendSeries.define("Revenue", historical, map2_some(operator.add))
def revenue(last_base: Period) -> PeriodSeries[Maybe[float]]:
    @PeriodSeries.define("Revenue forecast", accrual(YF.cmonthly))
    def forecast() -> Iterator[tuple[Period, CellFactory[float]]]:
        for period in Period.seq(last_base.end, QUARTER):
            def factory(p: Period = period) -> Step[float]:
                prior = yield from get_at(revenue, p.shift(-QUARTER))
                if isna(prior):
                    raise ValueError(f"missing prior revenue for {p}")
                return prior * (1 + QUARTERLY_GROWTH)

            yield period, factory

    return forecast
```

For additive period flows, `map2_some(operator.add)` is the usual seam
combiner. Test a base query, the first continuation key, and a query crossing
the seam. Date extensions dispatch a point query wholly to one side.
