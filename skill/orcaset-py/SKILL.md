---
name: orcaset-py
description: Build, modify, explain, debug, or validate financial models using the Orcaset Python library. Use when Codex needs to define Orcaset SpanSeriesDef or PointSeriesDef models, structure recursive forecast formulas, combine line items, extend historicals into projections, build statement views with Stmt/Group/Total, query or resolve model values with Context/query/value, inspect dependencies with ctx.deps(...), or implement common financial model patterns such as three-statement models, debt schedules, cohort schedules, depreciation, revenue projections, and external-data-backed historicals.
license: SSPL-1.0. LICENSE.txt has complete terms.
---

This skill requires the `orcaset` Python library. If the library is not already available, you can install it from `https://github.com/Orcaset/orcaset-py.git`.

# Build Orcaset Financial Models

Use Orcaset as a typed financial-model graph, not as a spreadsheet-cell generator. Define reusable line-item series definitions, then materialize the model only at the requested dates or periods.

## Orcaset Versions

1. Identify the user's active `orcaset` library version.
2. Compare that version against the available `references/api-<version>.md` files using `references/version-policy.md`.

Warn the user if there is a major or minor version difference between the install library and available skill references. 

## Reference Map

- `references/api-0.2.x.md`: Orcaset 0.2.x public API, constructors, querying, statement output, examples, and pitfalls.
- `references/version-policy.md`: How to handle version mismatches and update the skill safely.

## Core Workflow

Use Orcaset models as typed line-item graphs rather than spreadsheet cell grids.

1. Start by planning out the line items needed for the model and which line items are co-dependent on each other.
2. Start every model with calendar assumptions: `date`, `relativedelta`, the first `Period`, and output periods from `Period.list` or `Period.seq`.
3. Use `@span.define(...)` and `SpanSeriesDef` values for flows over periods: revenue, expense, cash flow, capex, depreciation, interest, taxes.
4. Use `@point.define(...)` and `PointSeriesDef` values for point-in-time balances: cash, debt, PPE, equity, retained earnings, shares.
5. Use `span.keyed(...)` or `point.keyed(...)` for query-dependent dynamic rows such as cohorts, tranches, customers, facilities, or schedules.
6. Present output with `Stmt`, `Group`, `Total`, `Stmt.values(...)`, `Stmt.values_for_periods(...)`, `Stmt.values_for_dates(...)`, and formatters such as `fixed_width_table`.
7. Do a final review to check mistakes or issues that should be fixed.

Read `references/api-0.2.x.md` when exact signatures, docstring details, or examples are needed.

## Model Organization

Use a single script for simple one-off models with fewer than roughly 12 line items. For larger models, organize the model as a Python package split by logical model area: for example, revenue, debt, fixed assets, working capital, equity, statement presentation, etc.

Keep model packages focused on definitions:

- Define assumptions, `SpanSeriesDef` / `PointSeriesDef` line items and `Stmt` / `Group` / `Total` statement structure.
- Put querying, value inspection, printing, exports, notebooks, and CLI behavior in a top-level script, notebook, test, or CLI entrypoint. Do not put user queries into the model package.
- Define series at module scope so other modules can import stable definition objects. Do not use model or series builder functions, define series as module-level values.
- Use top-level imports for acyclic model dependencies.
- For cross-file circular model dependencies, use local imports inside the smallest series function that needs the dependency, outside inner loops when possible. Orcaset series are lazy, so function bodies run when a `Context` queries the series, after modules have finished defining their series objects.
- Keep imports one-way: entrypoints may import model modules, but model modules should not import entrypoint scripts, notebooks, or CLI code.

Example multi-file model layout:

```txt
my_model/
  __init__.py
  assumptions.py          # dates, periods, rates, starting balances
  revenue.py              # revenue and related operating line items
  debt.py                 # debt balances, borrowings, repayments
  interest.py             # interest expense/income
  statements.py           # Stmt, Group, and Total presentation structure

scripts/
  print_model.py          # creates Context, defines query periods, prints or saves results
  inspect_model.py        # optional ad hoc value/dependency inspection
```

Make labels legible but concise. Use common financial abbreviations such as `ebit` instead of `earnings_before_interest_and_tax` and `qtr_...` instead of `quarter_...`.

## Code Style & Validation

- Preserve the user's existing model organization and sign convention unless it is clearly wrong. Add abstractions only when the model repeats a real pattern, such as a schedule family, roll-forward, historical-plus-projection line, or statement subtotal.
- Treat series as immutable definition values. Query series directly with explicit contexts, e.g. `revenue.value(ctx, period)` or `cash.query(ctx, dt)`.
- For linked forecasts, prefer formulas that query values through explicit query or value calls rather than carrying value state internally. Use loop-carried Python values only for exogenous assumptions or simple scaffolding where no model dependency is being hidden.
- For dynamic formula lists, use `Formula.sequence(formulas).map(...)` so dependent values remain inside the formula graph.
- To inspect dependencies, first get a concrete cell with `.query(...)`, evaluate or solve it, then call `ctx.deps(cell)`.
- For external data, fetch and normalize source data outside formula evaluation. Formula resolution should stay deterministic and should not trigger network calls.
- DO NOT inline external data into model files unless explicitly directed. Instead, build parsing/loading functions to retrieve data from sources dynamically.
- Group single-file models with short section comments like `# ----- Assumptions -----`, `# ----- Model -----`, and `# ----- Output -----`.
- Python is installed. You can use the interpreter for resolving one-off queries, validating values or code, and other checks. Run it with `uv ...`.
- Run `ruff` over any modified python files.
- All Python files MUST pass type checking. Use `pyrefly check ...`. Continue update code until type checking passes. NEVER use `typing.cast`, `typing.Any`, or any `# type: ignore` or other configurations to supress typing errors.
