# Validation and reporting

Evaluate public nodes directly through `Context.get` / `get_at`. Keep reporting downstream of model construction and bound every materialization. A successful table print does not establish that arbitrary valid queries or scenarios work.

For changed relationships, check representative exact keys, partial/combined intervals where supported, opening and terminal boundaries, missing inputs, and any actual/forecast seam. Reconcile relevant economic identities: revenue less signed expenses, opening balance plus movements, assets versus liabilities and equity, cash change versus cash flows, and sources versus uses. Exercise a changed assumption in a fresh context to verify downstream behavior.

Check dependencies in the context used to compute the result:

```python
assert ctx.depends_on((closing_cash, period.end), (opening_cash, period.start))
assert ctx.depends_on((revenue, period), growth)
path = ctx.path_to((revenue, period), growth)
```

Keyed nodes are `(rule, key)` pairs; unkeyed rules are passed directly. Direction is consuming output to upstream input. Use relationships that exist in the model, not these illustrative names. `path_to(..., structural=True)` includes chain internals for domain/seam debugging. Prefer targeted checks over dumping whole dependency trees. Dependencies describe the executed scenario, so branch-dependent relationships need the corresponding scenario.

For `Na`, check exact boundaries, source query policy, and the first missing prerequisite. For ascending-key errors, inspect repeated or overlapping keys. For live-generator errors, check whether an effect was put in a literal value slot without `Thunk`. For stale values, check context reuse. Run the configured static checker and fix interface mismatches rather than suppressing them.

Statements arrange existing model nodes:

```python
from orcaset import formatter, stmt

statement = stmt.Stmt(stmt.Total(profit, [revenue, expenses]))
values = statement.values_for_periods(ctx, periods)
print(formatter.fixed_width_table(values))
```

`stmt.Group` groups rows. `formatter.markdown_table` and `formatter.csv_table` offer other views. Date-keyed series can appear in period reports as balances; verify the report's date convention and opening column. Give deliverables a reproducible run command, input assumptions and units, and any material limitations appropriate to the user's requested scope.
