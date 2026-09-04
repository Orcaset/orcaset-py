# Embedded Web Scraping

This standalone project scrapes daily TSA checkpoint volumes and uses current versus
prior-quarter-to-date traffic to nowcast Southwest Airlines passenger revenue. Freight
and other revenue are held at their last reported values.

The scrape is part of the model rather than a preprocessing step. `tsa_passengers` uses
`Series.unfold` to download all rows on first structural demand and carry them through
the remaining unfold states. A separate `Cell` walks to the final observed date, and
the passenger nowcast depends on that cell.

Values and chain nodes are cached within a `Context`. A fresh context evaluates the
model again and therefore performs a fresh scrape.

## Run

Python 3.14+ and network access to `tsa.gov` are required.

```sh
cd examples/web-scraping
uv run python main.py
```

Output:

```txt
Southwest Airlines (LUV) operating revenue
Revenue in $ millions; TSA checkpoint passengers in travelers

Estimate Q3 2026 passenger revenue from TSA checkpoint QTD vs the prior quarter (1.0231).
Source: https://www.tsa.gov/travel/passenger-volumes
TSA QTD 2026-06-30 → 2026-09-02: 164,030,854
TSA QTD 2026-03-31 → 2026-06-03: 160,324,966

                                 Q1 2026      Q2 2026      Q3 2026  Q4 2026
TSA checkpoint passengers    208,660,296  233,763,292  164,030,854
  Passenger                        6,591        7,745        7,924    7,924
  Freight                             44           50           50       50
  Other                              614          637          637      637
---------------------------------------------------------------------------
Total operating revenue            7,249        8,432        8,611    8,611
```

## Layout

| File | Role |
| --- | --- |
| [`scrape.py`](scrape.py) | Download TSA data and expose the daily linked series and final-date cell. |
| [`data/luv_operating_revenue.csv`](data/luv_operating_revenue.csv) | Reported quarterly revenue. |
| [`model.py`](model.py) | History, nowcast, held forecasts, and statement layout. |
| [`main.py`](main.py) | Evaluate and print the model. |
