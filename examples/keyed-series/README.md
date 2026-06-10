# Build Revenue Scenarios

This example builds quarterly revenue scenarios for [monday.com](https://monday.com) (MNDY), a publicly traded SaaS company, by projecting revenue separately for each customer size cohort and rolling the cohorts up to total revenue.

It highlight using keyed series to build efficiently build series for each client segment.

## Size cohorts

Reported metrics are de-cumulated into five size groups which are interpred to be mutually exclusive:

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

Revenue per size group is not reported by MNDY. The model estimates revenue per group using the reported percent of total ARR as proxies.

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

## Output

Running the `main.py` file prints out assumptions and revenue detail for each segment for each of the three scenarios.

Example base case output:

```txt
BASE CASE

Start                                            2024-12-31  2025-03-31  2025-06-30  2025-09-30  2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30
End                                  2024-12-31  2025-03-31  2025-06-30  2025-09-30  2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30  2027-12-31

  Customer growth % YoY | <10 users                    1.50        1.50        1.50        1.50        1.50        1.50        1.50        1.50        1.25        1.25        1.25        1.25
  Customer growth % YoY | 10+ users                    7.50        7.50        7.50        7.50        7.50        7.50        7.50        7.50        7.00        7.00        7.00        7.00
  Customer growth % YoY | 50k+ ARR                    25.00       25.00       25.00       25.00       25.00       25.00       25.00       25.00       21.00       21.00       21.00       21.00
  Customer growth % YoY | 100k+ ARR                   40.00       40.00       40.00       40.00       40.00       40.00       40.00       40.00       33.00       33.00       33.00       33.00
  Customer growth % YoY | 500k+ ARR                   70.00       70.00       70.00       70.00       70.00       70.00       70.00       70.00       52.00       52.00       52.00       52.00
  NDR % | <10 users                                  104.00      104.00      104.00      104.00      104.00      104.00      104.00      104.00      103.00      103.00      103.00      103.00
  NDR % | 10+ users                                  114.00      114.00      114.00      114.00      114.00      114.00      114.00      114.00      113.00      113.00      113.00      113.00
  NDR % | 50k+ ARR                                   116.00      116.00      116.00      116.00      116.00      116.00      116.00      116.00      115.00      115.00      115.00      115.00
  NDR % | 100k+ ARR                                  116.00      116.00      116.00      116.00      116.00      116.00      116.00      116.00      115.00      115.00      115.00      115.00
  NDR % | 500k+ ARR                                  116.00      116.00      116.00      116.00      116.00      116.00      116.00      116.00      115.50      115.50      115.50      115.50


    Customers | <10 users                        186,184.00  186,697.00  187,175.00  188,086.00  186,984.00  187,681.28  188,381.16  189,083.65  189,671.79  190,261.75  190,853.55  191,447.20
    Customers | 10+ users                         57,122.00   58,101.00   59,082.00   59,633.00   60,469.00   61,572.23   62,695.59   63,839.45   64,928.46   66,036.04   67,162.52   68,308.21
    Customers | 50k+ ARR                           2,116.00    2,230.00    2,390.00    2,525.00    2,703.00    2,858.07    3,022.05    3,195.42    3,351.39    3,514.97    3,686.53    3,866.46
    Customers | 100k+ ARR                          1,271.00    1,404.00    1,525.00    1,669.00    1,745.00    1,898.14    2,064.71    2,245.91    2,411.87    2,590.10    2,781.51    2,987.05
    Customers | 500k+ ARR                             57.00       68.00       78.00       87.00       99.00      113.04      129.08      147.39      163.66      181.72      201.77      224.03

-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Total Customers                                  246,750.00  248,500.00  250,250.00  252,000.00  252,000.00  254,122.77  256,292.59  258,511.82  260,527.16  262,584.58  264,685.88  266,832.96

    Revenue | <10 users                               56.4m       59.8m       60.2m       63.4m       63.2m       64.0m       64.7m       65.5m       66.1m       66.6m       67.2m       67.8m
    Revenue | 10+ users                              121.4m      125.6m      129.9m      133.6m      140.5m      146.5m      152.6m      159.1m      165.3m      171.7m      178.3m      185.2m
    Revenue | 50k+ ARR                                36.7m       35.9m       41.2m       43.4m       45.7m       48.7m       51.9m       55.4m       58.6m       62.1m       65.8m       69.6m
    Revenue | 100k+ ARR                               53.6m       62.8m       66.5m       73.5m       80.8m       87.4m       94.5m      102.3m      109.8m      117.8m      126.4m      135.7m
    Revenue | 500k+ ARR                               14.1m       15.0m       19.0m       20.0m       21.1m       23.4m       26.0m       28.9m       31.7m       34.8m       38.2m       41.9m

-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Total Revenue                                        282.2m      299.0m      316.9m      333.9m      351.3m      369.9m      389.8m      411.1m      431.4m      453.0m      475.9m      500.3m
```
