# Build Revenue Scenarios

This example builds quarterly revenue scenarios for [monday.com](https://monday.com) (MNDY), a publicly traded SaaS company, by projecting revenue separately for each customer size cohort and rolling the cohorts up to total revenue.

## Size cohorts

Reported metrics are de-cumulated into five mutually exclusive size groups:

* `<10 users`
* `10+ users` (under $50k ARR)
* `50k+ ARR`
* `100k+ ARR`
* `500k+ ARR`

## Scenarios

There are three scenarios: `downside`, `base`, and `upside`. Each scenario defines two assumption ramps per size group:

* **Customer growth** — annual YoY growth in customer count, compounded quarterly.
* **Net dollar retention (NDR)** — annual NDR applied to the existing revenue base, compounded quarterly.

Per-group quarterly revenue build:

```txt
revenue[q] = revenue[q-1] * NDR^(1/4)              # existing base, net of expansion/churn
           + new_customers[q] * entry_arpc * 0.5   # new logos, half-quarter convention
```

where `entry_arpc` is the group's average quarterly revenue per customer over the last historical quarter.

## Layout

```txt
data/
  MNDY-metrics.csv      # customer counts, % ARR, and NDR by size threshold
  MNDY-revenue.csv      # quarterly revenue
model/
  data.py               # CSV loading, de-cumulation into size groups, historical series
  assumptions.py        # scenario ramps for customer growth and NDR
  metrics.py            # customer count projections by group and scenario
  revenue.py            # revenue projections by group and scenario
  statements.py         # one output statement per scenario
main.py                 # prints assumptions, metrics, and revenue detail per scenario
```

Data notes:

* Revenue by group is estimated from total revenue and percent-of-ARR disclosures.
* Total paying customers is only disclosed annually; missing quarters are interpolated so the `<10 users` slice is meaningful at every quarter end.
* NDR for `<10 users` proxies the all-customer rate, and `500k+ ARR` proxies the `>100k ARR` rate, since neither is disclosed directly.

## Running

```sh
uv run main.py
```
