# Web scraping

This example embeds a live web scrape into an orcaset model. It scrapes the daily [TSA checkpoint travel numbers](https://www.tsa.gov/travel/passenger-volumes) to build the current quarter's estimate of passenger revenue for Southwest Airlines (LUV).

## Model Structure

Southwest reports revenue in three segments: passenger, freight, and other. This projects builds a basic revenue model with the following structure:

* **Passenger:** Current quarter estimated using relative QTD change in checkpoint volume against the prior quarter (i.e. `(current QTD / prior QTD) * total prior quarter`). Constant dollar value thereafter.
* **Freight:** Held constant at last quarterly value.
* **Other:** Held constant at last quarterly value.

The models is meant to highlight inline data retrieval and manipulation rather than a thoughtful revenue forecast.

## Data Scraping

The scraping process is not a pre-calculation step. The model fetches data on-demand from `tsa.gov` whenever a cell is evaluated that depends on TSA volume. Values are cached within a `Context`, so re-evaluating values with an existing `Context` will not trigger the scrape again.

```mermaid
flowchart TD
  A[1. Evaluate current-quarter passenger revenue] --> B[2. Scrape daily TSA volumes from tsa.gov]
  B --> C[3. Create a daily series of passenger flows]
  C --> D[4. "Growth = current QTD / prior QTD"]
  D --> E[5. "Passenger = prior quarter revenue × growth"]
```

The model embeds the data retrieval, extraction, and aggregation directly into the cell values. New values are automatically incorporated into the model as they become available. No copy-paste required.

The scraping process uses well-known libraries from Python's open ecosystem. They are robust, actively maintained, and come for free by simply using Python.

* **`requests`:** Simple, synchronous http client used to retrieve the webpage from tsa.gov. Maintained by the Python Software Foundation.
* **`beautifulsoup4`:** HTML parsing library that finds and extracts the passenger data from the table in the webpage.  Mature library with over twenty years of development.

## Run

This is a standalone uv project with its own library dependencies. orcaset is pinned to `0.8.0` and resolved from the repo checkout.

Requires Python 3.14+ and a network path to `tsa.gov`.

```sh
cd examples/web-scraping
uv run python main.py
```

Output:

```txt
Southwest Airlines (LUV) operating revenue
Revenue in $ millions; TSA checkpoint passengers in travelers

Estimate Q3 2026 passenger revenue from TSA checkpoint QTD vs the prior quarter (1.0796).
Source: https://www.tsa.gov/travel/passenger-volumes
TSA QTD 2026-06-30 → 2026-08-13: 117,161,822
TSA QTD 2026-03-31 → 2026-05-14: 108,524,502

                                 Q1 2026      Q2 2026      Q3 2026  Q4 2026
TSA checkpoint passengers    208,660,296  233,763,292  117,161,822
  Passenger                        6,591        7,745        8,361    8,361
  Freight                             44           50           50       50
  Other                              614          637          637      637
---------------------------------------------------------------------------
Total operating revenue            7,249        8,432        9,048    9,048
```

## Layout

| File | Role |
| --- | --- |
| [`scrape.py`](scrape.py) | Download and parse the TSA table; expose `tsa_passengers` as a daily `PeriodSeries` |
| [`data/luv_operating_revenue.csv`](data/luv_operating_revenue.csv) | Reported quarterly revenue ($ millions), loaded at runtime |
| [`model.py`](model.py) | History, current-quarter passenger estimate, held freight/other, and `Stmt` layout |
| [`main.py`](main.py) | Reporting dates, evaluate in a `Context`, and print the table |
