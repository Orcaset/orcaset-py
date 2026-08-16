# Citations and Data Provenance

This example shows how values in an orcaset model can carry lineage information, allowing users to trace values all the way through to their originating source.

The example model fetchings SpaceX's Q2 2026 revenue from the SEC API (EDGAR) and creates a simple revenue model projection revenue at 10% quarterly growth. The Q2 2026 revenue value carries filling and URL metadata allow users to trace and verify its value back to the source document.

## Custom Values

Orcaset models can carry any value type, not just regular numerical types. In this case, we want a numerical type that is similar to a regular `float` but carries additional metadata related to the value's source. We'll define two types.

### `EdgarCitation`

Carries the data provenance information, specifically the filing identifier, period info (or "frame" in XBRL terms), and the source SEC URL.

```py
class EdgarCitation:
    accn: str  # Filing accession number
    frame: str  # XBRL frame (e.g. CY2026Q2)
    url: str  # Source EDGAR URL

    def __str__(self) -> str:
        return str({"accn": self.accn, "frame": self.frame, "url": self.url})
```

### `CitedFloat`



```py
class CitedFloat(float):
    """A floating point number that carries EDGAR provenance. Arithmetic returns a plain float."""

    citation: EdgarCitation
    __slots__ = ("citation",)

    def __new__(cls, value: float, citation: EdgarCitation) -> Self:
        obj = super().__new__(cls, value)
        obj.citation = citation
        return obj

    def __str__(self) -> str:
        return f"{float(self)} {self.citation}"

    def __repr__(self) -> str:
        return f"CitedFloat({float(self)!r}, {self.citation!r})"

    def __format__(self, spec: str) -> str:
        if spec == "":
            return str(self)
        return format(float(self), spec)
```


## Fetching Data from EDGAR

The model pulls revenue from the SEC uisng the `companyconcept` endpoint. You can visit the URL in a browser here: [https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json](https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json).

The URL returns data in JSON format.

```json
{
  "cik": 1181412,
  "taxonomy": "us-gaap",
  "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
  "label": "Revenue from Contract with Customer, Excluding Assessed Tax",
  "description": "Amount, excluding tax collected from customer, of revenue from satisfaction of performance obligation by transferring promised good or service to customer. Tax collected from customer is tax assessed by governmental authority that is both imposed on and concurrent with specific revenue-producing transaction, including, but not limited to, sales, use, value added and excise.",
  "entityName": "SPACE EXPLORATION TECHNOLOGIES CORP.",
  "units": {
    "USD": [
      ...,
      {
        "start": "2026-04-01",
        "end": "2026-06-30",
        "val": 7814000000,
        "accn": "0001628280-26-052535",
        "fy": 2026,
        "fp": "Q2",
        "form": "10-Q",
        "filed": "2026-08-04",
        "frame": "CY2026Q2"
      }
    ]
  }
}
```

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
  type: CitedFloat

Revenue by quarter-end (10% growth after the cited seed)
  2026-06-30  7,814,000,000  CitedFloat
  2026-09-30  8,595,400,000  float
  2026-12-31  9,454,940,000  float
  2027-03-31  10,400,434,000  float
  2027-06-30  11,440,477,400  float

Dependency tree for the first forecast quarter:
SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
  SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
  SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
    SpaceX revenue@Period(2026-03-31, 2026-06-30) = CitedFloat(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
      SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
      SpaceX revenue@Period(2026-03-31, 2026-06-30) = CitedFloat(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
```

The Q2 2026 line should match the JSON you opened. Each later quarter is the prior quarter times 1.10.

## What to notice

1. **The sourced cell is a `CitedFloat`.** That type is a `float` with extra fields: accession number, frame, and the URL you just visited. Printing it shows the number and the citation together.
2. **Forecast cells are plain `float`s.** `prior * 1.10` is ordinary arithmetic, so the extra filing info does not stick to the result. That is deliberate: only the leaf (the number that came from the filing) is `CitedFloat`.
3. **The dependency tree is how you get the citation back.** `ctx.dependencies(revenue, forecast_quarter)` shows that Q3 2026 came from the `CitedFloat` Q2 seed. Growth goes through `get_at`, so provenance lives in the graph rather than on every intermediate value.

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

`CitedFloat` is a `float` subclass. You can multiply it like a number; the product is a regular `float`. Override `__str__` / `__repr__` so printouts and the dependency tree show the citation.

```py
class CitedFloat(float):
    def __new__(cls, value: float, citation: EdgarCitation) -> Self: ...
```

The series seeds one `exact` cell from the filing, then each later quarter reads the prior period:

```py
prior = yield from get_at(revenue, p.shift(-QUARTER))
return prior * 1.10
```
