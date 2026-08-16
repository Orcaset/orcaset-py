# Citations

This example shows how an orcaset model can carry a **citation** on a sourced number: where the figure came from, not just what it equals.

It pulls one revenue figure from SpaceX’s Q2 2026 10-Q (the quarterly report public companies file with the SEC), wraps it as a `Cited` float, then grows that seed at 10% per quarter. Forecast quarters are ordinary numbers. To see the filing again, look at the **dependency tree**.

## The public number

Open this URL in a browser. It is a small JSON file from the SEC:

[SpaceX revenue (companyconcept)](https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json)

Find the object whose `"frame"` is `"CY2026Q2"`. That is calendar Q2 2026 (April–June). It looks like:

```json
{
  "start": "2026-04-01",
  "end": "2026-06-30",
  "val": 7814000000,
  "accn": "0001628280-26-052535",
  "form": "10-Q",
  "frame": "CY2026Q2"
}
```

`val` is revenue in US dollars: **$7,814,000,000**. `accn` is the EDGAR accession number — the filing’s ID. `frame` is the SEC’s label for that calendar quarter. The example hard-codes `CY2026Q2` as the seed row.

## Run

From the repository root (Python 3.14+, network access to `data.sec.gov`):

```sh
uv run python examples/citations/main.py
```

Output:

```txt
Reported CY2026Q2 revenue: 7814000000.0 {'accn': '0001628280-26-052535', 'frame': 'CY2026Q2', 'url': 'https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'}
  type: Cited

Revenue by quarter-end (10% growth after the cited seed)
  2026-06-30  7,814,000,000  Cited
  2026-09-30  8,595,400,000  float
  2026-12-31  9,454,940,000  float
  2027-03-31  10,400,434,000  float
  2027-06-30  11,440,477,400  float

Dependency tree for the first forecast quarter:
SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
  SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
  SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
    SpaceX revenue@Period(2026-03-31, 2026-06-30) = Cited(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
      SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
      SpaceX revenue@Period(2026-03-31, 2026-06-30) = Cited(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
```

The Q2 2026 line should match the JSON you opened. Each later quarter is the prior quarter times 1.10.

## What to notice

1. **The sourced cell is a `Cited`.** That type is a `float` with extra fields: accession number, frame, and the URL you just visited. Printing it shows the number and the citation together.
2. **Forecast cells are plain `float`s.** `prior * 1.10` is ordinary arithmetic, so the extra filing info does not stick to the result. That is deliberate: only the leaf (the number that came from the filing) is `Cited`.
3. **The dependency tree is how you get the citation back.** `ctx.dependencies(revenue, forecast_quarter)` shows that Q3 2026 came from the `Cited` Q2 seed. Growth goes through `get_at`, so provenance lives in the graph rather than on every intermediate value.

The fetch runs the first time the seed cell is demanded in a `Context`, then is cached. Re-printing with the same `Context` does not hit the SEC again.

## The types

`EdgarCitation` is the filing pointer:

```py
@dataclass(frozen=True, slots=True)
class EdgarCitation:
    accn: str
    frame: str
    url: str
```

`Cited` is a `float` subclass. You can multiply it like a number; the product is a regular `float`. Override `__str__` / `__repr__` so printouts and the dependency tree show the citation.

```py
class Cited(float):
    def __new__(cls, value: float, citation: EdgarCitation) -> Self: ...
```

The series seeds one `exact` cell from the filing, then each later quarter reads the prior period:

```py
prior = yield from get_at(revenue, p.shift(-QUARTER))
return prior * (1 + GROWTH)
```
