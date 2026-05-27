---
name: orcaset-py-models
description: Build, modify, explain, debug, or validate financial models using the Orcaset Python library. Use when Codex needs to define Orcaset SpanSeries or PointSeries models, structure recursive forecast formulas, combine line items, extend historicals into projections, build statement views with Stmt/Group/Total, query or resolve model values with Context/query/value, inspect dependencies with ctx.deps(...), or implement common financial model patterns such as three-statement models, debt schedules, cohort schedules, depreciation, revenue projections, and external-data-backed historicals.
license: SSPL-1.0. LICENSE.txt has complete terms.
---

# Build Orcaset Financial Models

Use Orcaset as a typed financial-model graph, not as a spreadsheet-cell generator. Define reusable line-item series, then materialize the model only at the requested dates or periods.

The Orcaset Python API is experimental. Before writing version-sensitive code, identify the installed or local Orcaset version and load the matching versioned reference.

## Version Gate

1. Inspect the user's project for its Orcaset source, installed package, lockfile, or dependency pin.
2. Identify the installed or local Orcaset version before relying on bundled API examples.
3. Compare that version against the available `references/api-<version>.md` files using `references/version-policy.md`.

Prefer the user's local signatures over bundled references whenever they conflict.

## Reference Map

- `references/api-0.2.0.md`: Orcaset 0.2.0 public API, constructors, querying, statement output, examples, and pitfalls.
- `references/modeling-patterns.md`: Stable modeling workflow, financial statement structure, validation habits, and design rules.
- `references/version-policy.md`: How to handle version mismatches and update the skill safely.

## Core Workflow

1. Load the matching API reference for the detected version.
2. Read `references/modeling-patterns.md` for nontrivial models, linked statements, dynamic schedules, or audit/debug tasks.
3. Put assumptions at the top: model start date, output cadence, historical values, rates, margins, starting balances, and external data fetches.
4. Use "spans" for flows or levels over periods: revenue, expenses, interest, taxes, capex, depreciation, and cash flow.
5. Use "points" for balances at dates: cash, debt, PPE, equity, retained earnings, shares, and covenant balances.
6. Keep model state in `Context`; do not instantiate series classes directly.
7. Build output views with `Stmt`, `Group`, and `Total`.
8. Use a typechecker to confirm after writing or modifying any code, and use a formatter (e.g. "ruff") to format all written code, in each case if available.
9. Run the model script or focused tests after changes. Verify signs, period boundaries, missing values, partial-period behavior, and balance checks.

## When Editing Models

Preserve the user's existing model organization and sign convention unless it is clearly wrong. Add abstractions only when the model repeats a real pattern, such as a schedule family, roll-forward, historical-plus-projection line, or statement subtotal.

For linked forecasts, prefer formulas that query other model lines through `self.ctx`. Use loop-carried Python values only for exogenous assumptions or simple scaffolding where no model dependency is being hidden.

For external data, fetch and normalize source data outside formula evaluation. Formula resolution should stay deterministic and should not trigger network calls.
