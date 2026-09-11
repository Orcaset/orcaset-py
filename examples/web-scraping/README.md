# Embedded Web Scraping

This example shows how you can fetch external data as part of an Orcaset model. It scrapes daily TSA checkpoint volumes and uses current versus prior-quarter-to-date traffic to nowcast Southwest Airlines passenger revenue. Freight and other revenue are held at their last reported values.

The basic pattern is to fetch data inside a lazy series, expose shared calculations as named cells, and join reported history to deferred forecasts. A `Context` caches the downloaded series and calculated values for one run; a fresh context performs a fresh scrape when TSA data is demanded.

## Fetching TSA data

The TSA publishes daily checkpoint volume at [https://www.tsa.gov/travel/passenger-volumes](https://www.tsa.gov/travel/passenger-volumes). The example uses the QTD change in volume relative to the prior quarter to create a "nowcast" of estimated current quarter passenger revenue.

In `scrape.py`, `checkpoint_step` is a lazy cell fetches data from `tsa.gov`, parses it, and builds a `Cons[Period, float]` over the daily checkpoint volume when forced. `tsa_passengers` wraps the checkpoint data into a `Series` that can be queried.

```py
@Cell.define("Fetch and parse TSA checkpoints")
def checkpoint_step() -> Effect[Cons[Period, float] | None]:
    """Fetch the current-year page only when the series' first node is demanded."""
    html = fetch_html(TSA_URL)
    rows = parse_checkpoint_rows(html, TSA_URL)

    def step(index: int) -> tuple[Period, float, int] | None:
        if index == len(rows):
            return None
        travel_date, count = rows[index]
        period = Period(travel_date - timedelta(days=1), travel_date)
        return period, count, index + 1

    daily = unfold_cells("TSA checkpoint daily rows", seed=0, step=step)
    return (yield from get(daily))


tsa_passengers = Series("TSA checkpoint passengers", checkpoint_step, _BY_DAYS)
```

The data retrievel is inert until forced. It does not fetch any data when the file is loaded or the series is created. It is only fetched the first time `tsa_passengers` is queried.

## Revenue model

The passenger history is directly incorporated into the revenue forecast.

The first time a passenger revenue forecast period is requested, the series demand the applicable checkpoint volume from `tsa_passengers`. The data retrieval is cached inside the evaluation context, so future queries will not trigger additional data requests to `tsa.gov`.

```py
@Series.define("Passenger forecast", ACCRUE, seed=NOWCAST_QUARTER)
def passenger_forecast(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    # If the current period is the nowcast quarter, calculate the QtQ change in
    # checkpoint traffic volume
    if period == NOWCAST_QUARTER:
        prior_rev = yield from get_at(passenger_history, period.shift(-QUARTER))
        qtd, prior_qtd = yield from get(nowcast_windows)
        current_tsa = yield from get_at(tsa_passengers, qtd)  # Current QTD checkpoint volume
        prior_tsa = yield from get_at(tsa_passengers, prior_qtd)  # Prior QTD checkpoint volume
        if prior_tsa == 0.0 or isna(prior_tsa):
            raise ValueError("prior-quarter TSA QTD is zero or missing")
        traffic_growth = maybe.mul_some(current_tsa, 1 / prior_tsa)
        value = maybe.mul_some(prior_rev, traffic_growth)

    # Otherwise, just use the same estimate as the nowcast quarter
    # (hold future constant, no long term projections)
    else:
        value = yield from get_at(passenger_forecast, NOWCAST_QUARTER)

    return period, value, period.from_end(QUARTER)


# Extend the historical passenger revenue with the forecast
passenger = Series.extend(
    "Passenger", ACCRUE, base=passenger_history.cells, cont=lambda _: passenger_forecast.cells
)
```

While this example fetches data over the web, a similar approach can be used to retrieve data from any other source such as databases or third-party applications.

## Run

Python 3.14+ and network access to `tsa.gov` are required.

```sh
cd examples/web-scraping
uv run python main.py
```

Running the script prints a quarterly statement in the form below. This sample uses TSA observations through September 2, 2026; values depend on the data available when run.

```txt
Southwest Airlines (LUV) operating revenue
Revenue in $ millions; TSA checkpoint passengers in travelers

Estimate Q3 2026 passenger revenue from TSA checkpoint QTD vs the prior quarter (1.0161).
Source: https://www.tsa.gov/travel/passenger-volumes
TSA QTD 2026-06-30 → 2026-09-06: 173,795,381
TSA QTD 2026-03-31 → 2026-06-07: 171,033,697

                                 Q1 2026      Q2 2026      Q3 2026  Q4 2026
TSA checkpoint passengers    208,660,296  233,763,292  173,795,381
  Passenger                        6,591        7,745        7,870    7,870
  Freight                             44           50           50       50
  Other                              614          637          637      637
---------------------------------------------------------------------------
Total operating revenue            7,249        8,432        8,557    8,557
```

## Layout

| File | Role |
| --- | --- |
| [`scrape.py`](scrape.py) | Download TSA data and expose the daily linked series and final-date cell. |
| [`data/luv_operating_revenue.csv`](data/luv_operating_revenue.csv) | Reported quarterly revenue. |
| [`model.py`](model.py) | History, nowcast, held forecasts, and statement layout. |
| [`main.py`](main.py) | Evaluate shared inputs and print the quarterly statement. |
