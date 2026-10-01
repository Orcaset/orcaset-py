# Verify models and trace dependencies

Verify changes and key model relationships before reporting results. Keep checks proportional to the changes.

## Static checks and model structure

Run the skill's `scripts/check.sh`, passing the model directory. Resolve the script path relative to the installed skill, not the model project:

```sh
bash /path/to/orcaset/skills/orcaset/scripts/check.sh /path/to/model
```

The script runs `ruff check --fix` and pyrefly with Python 3.14 and strict callable subtyping. It uses tools on `PATH`, falling back to `uvx`. Ruff lint fixes do not replace `ruff format`; run the project's formatter separately when formatting is needed. If a tool cannot run, report the check as unverified rather than passed.

Fix type errors at the rule, query, or combinator boundary instead of bypassing them with ignores or casts. Review [core.md](core.md)'s layout rules: importable module-level model nodes, named assumptions, output code separated from calculations, and no artificial reporting cutoff in an ongoing series. Inside model computations, request other rules with `yield from get(...)` or `yield from get_at(...)` so dependencies remain visible to the evaluator.

## Evaluate values and financial identities

Query public nodes directly with `Context.get` for unkeyed rules and `Context.get_at` for keyed rules.

Choose relevant reconciliations rather than imposing every check on every model:

| Relationship | Useful check |
|---|---|
| Income statement | Subtotals reconcile to components using the model's expense sign convention |
| Balance rollforward | Closing balance equals opening balance plus signed movements |
| Linked statements | Assets equal liabilities plus equity; cash change reconciles to cash flows |
| Debt schedule | Draws, repayments, interest, and maturity treatment reconcile without accidental negative principal |
| Transaction funding | Independently calculated sources equal uses |
| Investment returns | Cash-flow signs and dates match the investor perspective and the return function's timing convention |

Do not make a check pass by defining its two sides from the same total or by plugging an unexplained residual.

Exercise queries that expose the changed relationship:

- Seed/opening key, a later key, and the actual-to-forecast seam where applicable.
- A combined interval and a partial interval if the query supports them. For exact-only inputs, a nonmatching interval should remain missing.
- Immediately before inception and around a contractual end, payoff, sale, or other boundary.
- Missing prerequisites, zero denominators, and scenario branches relevant to the change. An expected `Na` is different from an unexplained missing result.

Match checks to the query's semantics. For additive flows, compare an aggregate with the sum of its component periods. For balances or averages, check the correct endpoint or weighting instead of summing them. Accrual or averaging of available overlaps should not be used as proof that the source covers every requested date; inspect source coverage separately when full coverage is required. Bound all evaluation of potentially infinite series.

## Dependency inspection

Dependency direction runs from the consuming output to its upstream input. Pass keyed nodes as `(rule, key)` pairs and unkeyed rules directly.

| API | Result |
|---|---|
| `ctx.dependencies(series, key)` | Dependency tree for a keyed result (USE SPARINGLY; OUTPUT CAN BE ENORMOUS AND SLOW) |
| `ctx.rule_dependencies(rule)` | Dependency tree for an unkeyed result (USE SPARINGLY; OUTPUT CAN BE ENORMOUS AND SLOW) |
| `ctx.depends_on(source, target)` | Booliean for whether the evaluated source transitively demands the target |
| `ctx.path_to(source, target)` | Shortest dependency path as a tuple of `DepNode`, or `None` |

These methods resolve nodes if not already present in the context, so inspecting dependencies can trigger model computation and deferred I/O. Trees and paths hide internal chain traversal by default. Pass `structural=True` to the tree or path methods when debugging how cells are reached or a series is joined.

This example checks amounts and both keyed and unkeyed dependencies:

```py
from datetime import date

from orcaset import (
    Effect,
    Fn,
    Maybe,
    Period,
    Series,
    Val,
    get_at,
    ops,
    period_union,
    query,
)

quarter = Period(date(2025, 12, 31), date(2026, 3, 31))
revenue = Series.of("Revenue", query.covered, pairs=[(quarter, 100.0)])
cost_ratio = Val("Signed cost ratio", -0.4)
costs = ops.scale("Costs", revenue, cost_ratio)
profit = ops.add("Profit", revenue, costs, merge_keys=period_union)


@Fn.define("First-quarter profit")
def first_quarter_profit() -> Effect[Maybe[float]]:
    return (yield from get_at(profit, quarter))


if __name__ == "__main__":
    from math import isclose, isfinite

    from orcaset import Context, isna

    ctx = Context()
    value = ctx.get(first_quarter_profit)
    assert not isna(value)
    assert isfinite(value)
    assert isclose(value, 60.0, rel_tol=1e-9, abs_tol=1e-9)
    assert ctx.depends_on((profit, quarter), (revenue, quarter))
    assert ctx.depends_on(first_quarter_profit, cost_ratio)
    path = ctx.path_to(first_quarter_profit, cost_ratio)
    assert path is not None
    print(ctx.dependencies(profit, quarter))
    print(ctx.rule_dependencies(first_quarter_profit))
```

Use targeted dependency assertions for important drivers, then inspect paths when a relationship is missing or unexpected. A path establishes a demanded dependency, not a nonzero numerical sensitivity: an input can be read and then multiplied by zero. Branches only contribute the dependencies actually demanded in that scenario. A node does not count as depending on itself unless there is a demand cycle. For citation-bearing inputs, inspect the source values in the tree; derived arithmetic may have discarded the citation attribute.

## Scenario checks and caching

Use a fresh `Context` after changing an assumption. Resolved values are memoized within a context; changing a `Val.value` does not invalidate downstream cached results. Restore any temporary input changes so checks do not alter the delivered base case.

Add this scenario check inside the example's existing `__main__` block:

```py
    original_ratio = cost_ratio.value
    try:
        cost_ratio.value = -0.5
        scenario_ctx = Context()
        scenario_profit = scenario_ctx.get(first_quarter_profit)
        assert not isna(scenario_profit)
        assert isclose(scenario_profit, 50.0, rel_tol=1e-9, abs_tol=1e-9)
        assert scenario_ctx.depends_on(first_quarter_profit, cost_ratio)
    finally:
        cost_ratio.value = original_ratio
```

Check both the magnitude and direction of the changed output against the formula or an independently calculated expectation. Use a new context for any subsequent base-case run as well. Rebinding a Python variable to a new rule is not a general way to replace references already captured by combinators.

## Diagnose failures

| Symptom | Inspect first |
|---|---|
| Unexpected `Na` | Exact keys, query policy, actual/forecast seam, and the first missing prerequisite in the dependency path |
| Unexpected zero | `fill=0.0`, `value_or`, or other defaults that may hide missing data |
| Ascending-key or overlap error | Repeated keys, period boundaries, and the next state returned by the unfold step |
| A generator appears where a value is expected | A live effect stored as a literal; defer the computation with `Thunk` where required |
| Stale result after an input change | Reuse of a context that already cached the result |
| Missing expected dependency | A hard-coded or eagerly computed intermediate, direct `.value` access inside a formula, or an unexecuted branch |
| `CycleError` | The demand path and whether the circular relationship is intentional |
| `ConvergenceError` | Seeds, distance function, residual history, tolerance, iteration limit, and the underlying equations |

For intentional cycles, verify the converged values against the economic equations, not just the absence of an exception. Report failure to converge; do not present the last iterate as a solved result or relax tolerances solely to suppress the error.

Finally, regenerate the requested outputs and check that they use the verified nodes, dates, units, signs, and scenario. Follow [output.md](output.md) for statement behavior. Report what was checked and any remaining failures or material assumptions; distinguish checks that passed from checks that could not run.
