# Orcaset Examples

This directory holds orcaset examples that demonstrate common modeling patterns and library capabilities.

## Index

- [`circular.py`](circular.py) — Payment-in-kind interest on average debt, solved as a typed `get_at(..., seed=, distance=)` demand cycle rather than broken with timing.
- [`projection.py`](projection.py) — Extends quarterly historicals (`covered`) with a monthly growth forecast (`accrual`) via `PeriodExtendSeries`, and uses `Stmt` to materialize a quarterly view.
- [`units.py`](units.py) — Uses distinct USD/EUR value types so a ``map2`` sum across currencies is a static type error rather than a silent numeric bug.
- [`income.py`](income.py) — Builds a simple income statement from derived series (`*`, `+`), nested `Total`s, and a fixed-width quarterly table.
- [`capex.py`](capex.py) — Turns annual capex into per-spend cohort depreciation schedules via `MapItemsSeries`, then aggregates them into total depreciation. Demonstrates nested series-in-series value structure.
- [`balance.py`](balance.py) — Models a point-in-time balance that compounds from period-domain interest, with balance keys derived from the interest series.
- [`web-scraping/`](web-scraping/) — Standalone example project that inlines a TSA checkpoint scrape into a Southwest (LUV) quarterly revenue estimate. See [`web-scraping/README.md`](web-scraping/README.md).
- [`citations/`](citations/) — Wraps a SpaceX 10-Q revenue fact as a `Cited` float so printing and `ctx.dependencies(...)` show the EDGAR accession, frame, and source URL. See [`citations/README.md`](citations/README.md).
