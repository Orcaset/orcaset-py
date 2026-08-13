# Orcaset Examples

This directory holds orcaset examples that demonstrate common modeling patterns and library capabilities.

## Index

- [`projection.py`](projection.py) — Extends a quarterly historical series with a monthly growth forecast on one series spine, using `accrual` to bridge period frequencies and `Stmt` to materialize a quarterly view.
- [`units.py`](units.py) — Uses distinct USD/EUR value types so a ``map2`` sum across currencies is a static type error rather than a silent numeric bug.
- [`income.py`](income.py) — Builds a simple income statement from derived series (`*`, `+`), nested `Total`s, and a fixed-width quarterly table.
- [`capex.py`](capex.py) — Turns annual capex into per-spend cohort depreciation schedules via `MapItemsSeries`, then aggregates them into total depreciation. Demonstrates nested series-in-series value structure.
- [`balance.py`](balance.py) — Models a point-in-time balance that compounds from period-domain interest, with balance keys derived from the interest series.
- [`southwest-tsa/`](southwest-tsa/) — Standalone example project that inlines a TSA checkpoint scrape into a Southwest (LUV) quarterly revenue nowcast. See [`southwest-tsa/README.md`](southwest-tsa/README.md).
