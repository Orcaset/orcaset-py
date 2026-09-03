# Embedded Web Scraping

This standalone project scrapes daily TSA checkpoint volumes and uses current versus
prior-quarter-to-date traffic to nowcast Southwest Airlines passenger revenue. Freight
and other revenue are held at their last reported values.

The scrape is part of the model rather than a preprocessing step. `tsa_passengers` uses
`Series.from_rule` with a `Cell` that downloads all rows on first structural demand.
The context caches those rows, so later tails reuse them. A separate
`Cell` walks to the final observed date, and the passenger nowcast depends on that cell.

Values and chain nodes are cached within a `Context`. A fresh context evaluates the
model again and therefore performs a fresh scrape.

## Run

Python 3.14+ and network access to `tsa.gov` are required.

```sh
cd examples/web-scraping
uv run python main.py
```

## Layout

| File | Role |
| --- | --- |
| [`scrape.py`](scrape.py) | Download TSA data and expose the daily linked series and final-date cell. |
| [`data/luv_operating_revenue.csv`](data/luv_operating_revenue.csv) | Reported quarterly revenue. |
| [`model.py`](model.py) | History, nowcast, held forecasts, and statement layout. |
| [`main.py`](main.py) | Evaluate and print the model. |
