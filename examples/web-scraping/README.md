# Web scraping

This example inlines a live web scrape into an orcaset model. Daily [TSA checkpoint travel numbers](https://www.tsa.gov/travel/passenger-volumes) nowcast the current quarter of Southwest Airlines (LUV) passenger revenue; later quarters follow last year's seasonal quarter-on-quarter path.

It is a standalone uv project so scraping libraries stay out of the orcaset package. orcaset is pinned to `0.7.1` and resolved from the repo checkout.

## Run

Requires Python 3.14+ and a network path to `tsa.gov`.

```sh
uv run python main.py
```

The run prints the TSA QTD factor, then a fixed-width operating-revenue table in $ millions from Q1 2025 through Q4 of the next calendar year (Southwest's fiscal year is the calendar year).

Typecheck from this directory:

```sh
uvx pyrefly check
```

## Layout

| File | Role |
| --- | --- |
| [`scrape.py`](scrape.py) | Download and parse the TSA table; expose `tsa_passengers` as a daily `PeriodSeries` |
| [`data/luv_operating_revenue.csv`](data/luv_operating_revenue.csv) | Reported quarterly revenue ($ millions), loaded at runtime |
| [`model.py`](model.py) | History, current-quarter nowcast, seasonal forecast, and nested `Stmt` layout |
| [`main.py`](main.py) | Evaluate in a `Context` and print the table |

The scrape is not a pre-step. `tsa_passengers` cells run on first demand in a `Context`. Revenue cells `yield from get(tsa_passengers.keys())` before emitting the grid, then `get_at` QTD passenger counts the same way they read any other series.

## Nowcast

- **History.** CSV through the last reported quarter.
- **Current quarter.** Passenger lines = prior quarter × (TSA QTD / the same elapsed days of the prior quarter). Freight and other hold last reported values.
- **Later quarters.** Last year's corresponding QoQ seasonal ratio applied to that nowcast.
