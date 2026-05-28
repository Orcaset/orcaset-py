---
name: orcaset-py
description: Build, modify, explain, debug, or validate financial models using the Orcaset Python library. Use when Codex needs to define Orcaset SpanSeries or PointSeries models, structure recursive forecast formulas, combine line items, extend historicals into projections, build statement views with Stmt/Group/Total, query or resolve model values with Context/query/value, inspect dependencies with ctx.deps(...), or implement common financial model patterns such as three-statement models, debt schedules, cohort schedules, depreciation, revenue projections, and external-data-backed historicals.
license: SSPL-1.0. LICENSE.txt has complete terms.
---

# Build Orcaset Financial Models

Use Orcaset as a typed financial-model graph, not as a spreadsheet-cell generator. Define reusable line-item series, then materialize the model only at the requested dates or periods.

## Orcaset Versions

1. Identify the user's active `orcaset` library version.
2. Compare that version against the available `references/api-<version>.md` files using `references/version-policy.md`.

Warn the user if there is a major or minor version difference between the install library and available skill references. 

## Reference Map

- `references/api-0.2.0.md`: Orcaset 0.2.0 public API, constructors, querying, statement output, examples, and pitfalls.
- `references/modeling-patterns.md`: Stable modeling workflow, financial statement structure, validation habits, and design rules.
- `references/version-policy.md`: How to handle version mismatches and update the skill safely.

## Core Workflow

Use Orcaset models as typed line-item graphs rather than spreadsheet cell grids.

1. Start by planning out the line items needed for the model and which line items are co-dependent on each other.
2. Start every model with calendar assumptions: `Date.make`, `Offset.make`, the first `Period.t`, and output periods from `Period.make_seq`.
3. Use `Series.Spans.t` for flows over periods: revenue, expense, cash flow, capex, depreciation, interest, taxes.
4. Use `Series.Points.t` for point-in-time balances: cash, debt, PPE, equity, retained earnings, shares.
5. Present output with `Stmt.span_total`, `Stmt.point_total`, `Stmt.group`, `Stmt.eval_periods`, and `Stmt.fixed_width`.

Read `references/api-overview.md` when exact signatures, docstring details, or examples are needed.

## Model Organization

Make labels legible but concise. Use common financial abbreviations.

Example:

- `ebit` instead of `earnings_before_interest_and_tax`
- `qtr_...` instead of `quarter_...` 

## Code Style & Validation

- Preserve the user's existing model organization and sign convention unless it is clearly wrong. Add abstractions only when the model repeats a real pattern, such as a schedule family, roll-forward, historical-plus-projection line, or statement subtotal.
- For linked forecasts, prefer formulas that query other model lines through `self.ctx`. Use loop-carried Python values only for exogenous assumptions or simple scaffolding where no model dependency is being hidden.
- For external data, fetch and normalize source data outside formula evaluation. Formula resolution should stay deterministic and should not trigger network calls.
- Group code with short section comments like `(* ----- Assumptions ----- *)`, `(* ----- Model ----- *)`, and `(* ----- Output ----- *)`. For larger projects (greater than ~20 line items), break logical sections into different files.
- Python is installed. You can use the interpreter for resolving one-off queries, validating values or code, and other checks. Run it with `uv ...`.
- Run `ruff` over any modified python files.
- All Python files MUST pass type checking. Use `pyrefly check ...`. Continue update code until type checking passes. NEVER use `typing.cast`, `typing.Any`, or any `# type: ignore` or other configurations to supress typing errors.
