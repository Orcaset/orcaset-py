# Citations and Data Provenance

This example shows how values in an orcaset model can carry data provenance information, allowing users to trace values all the way through to their originating source.

The example fetches SpaceX's Q2 2026 revenue from the SEC API (EDGAR) and creates a simple revenue model projecting revenue at 10% quarterly growth. The Q2 2026 revenue value carries filing and URL metadata, allowing users to trace and verify its value back to the source document.

## Custom Values

Orcaset models can carry any value type, not just regular numerical types. In this case, we want a numerical type that is similar to a regular `float` but carries additional metadata related to the value's source. We'll define two types.

### `EdgarCitation`

Holds the filing identifier, period info (or "frame" in XBRL terms), and the source SEC URL.

```py
@dataclass(frozen=True, slots=True)
class EdgarCitation:
    accn: str  # Filing accession number
    frame: str  # XBRL frame (e.g. CY2026Q2)
    url: str  # Source EDGAR URL

    def __str__(self) -> str:
        return str({"accn": self.accn, "frame": self.frame, "url": self.url})
```

### `CitedFloat`

This is the numerical type that holds the value and source metadata. It is a subclass of the built-in `float` type, which means it behaves the same way as any other `float`. Any function that accepts a `float` will also accept a `CitedFloat`. The only difference is that it carries a `citation` field with an `EdgarCitation` object tracking the value's source.

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

> `float` is an immutable type, so subclassing is done by overriding `__new__` rather than the typical `__init__` override.

Note that the result of transforming a `CitedFloat` with standard arithmetic operators (e.g. addition, subtraction, multiplication) is a regular `float`, *not* a `CitedFloat`. Generally that's fine because provenance for derived values can still be traced through the dependency edges tracked by orcaset's effect handlers.

## Fetching Data from EDGAR

The model pulls revenue from the SEC using the `companyconcept` endpoint. You can visit the URL in a browser here: [https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json](https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json).

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

The `load_frame(url: str, frame: str) -> CitedFloat` function fetches the JSON from the URL, finds the USD row whose `frame` matches, and returns a `CitedFloat`.

## Revenue Definition

The example builds a toy revenue model for SpaceX. It starts with Q2 2026 actual revenue from EDGAR and continues by growing 10% quarterly thereafter.

```py
@PeriodSeries.define("SpaceX revenue", accrual(YF.cmonthly))
def revenue() -> Iterator[tuple[Period, float | CellFactory[float]]]:
    # Fetch Q2 2026 revenue from the EDGAR API and return it as a CitedFloat value
    yield Q2_2026, load_frame(CONCEPT_URL, FRAME)

    # Grow the revenue at 10% per quarter thereafter
    for k in Period.seq(Q2_2026.end, QUARTER):

        # Get the prior quarter's value and grow it by 10%
        def factory(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.from_start(-QUARTER))
            if isna(prior):
                raise ValueError(f"missing prior revenue for {p}")
            return prior * 1.10

        yield k, factory
```

Orcaset uses generic types over a series' values to make sure models compose correctly. The revenue line item has type `PeriodSeries[Maybe[float]]`, which captures the common type of the initial and subsequent values. Orcaset will still raise type errors if we try to apply operations on `revenue` that don't work with floats.

## Tracking Data Provenance

`revenue` can be used as if it held regular `float` values. Formatting, arithmetic, and other transformations work and type check correctly.

```py
ctx = Context()

# Print the first three quarters of revenue
for p in Period.seq(Q2_2026.start, QUARTER, date(2026, 12, 31)):
    print(f"{p} revenue: {ctx.get_at(revenue, p):,.0f}")
# Period(2026-03-31, 2026-06-30) revenue: 7,814,000,000
# Period(2026-06-30, 2026-09-30) revenue: 8,595,400,000
# Period(2026-09-30, 2026-12-31) revenue: 9,454,940,000
```

Inspecting the value for Q2 2026 reveals it is indeed a `CitedFloat` object linking its value back to the SEC origin URL.

```py
q2_2026_revenue = ctx.get_at(revenue, Q2_2026)
print(f"\ntype(q2_2026_revenue): {type(q2_2026_revenue)}")
# type(q2_2026_revenue): <class '__main__.CitedFloat'>
if isinstance(q2_2026_revenue, CitedFloat):
    print(f"Q2 2026 revenue citation: {q2_2026_revenue.citation}\n")
# Q2 2026 revenue citation: {'accn': '0001628280-26-052535', 'frame': 'CY2026Q2', 'url': 'https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'}
```

`get_at` is typed as `Maybe[float]` (`float | Na`), so the `isinstance` check both skips misses and narrows to `CitedFloat` before reading `.citation`.

Even though the Q3 2026 value is a regular `float` without source metadata, it is still indirectly linked to the Q2 metadata by tracing the dependency from Q3 to Q2. We can verify this by printing the dependency tree for Q3.

```py
Q3_2026 = Period(date(2026, 6, 30), date(2026, 9, 30))
print(f"Q3 2026 value type: {type(ctx.get_at(revenue, Q3_2026))}")
# Q3 2026 value type: <class 'float'>

print(ctx.dependencies(revenue, Q3_2026))
# SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
#   SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
#   SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
#     SpaceX revenue@Period(2026-03-31, 2026-06-30) = CitedFloat(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
#       SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
#       SpaceX revenue@Period(2026-03-31, 2026-06-30) = CitedFloat(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
```

Reviewing the dependency tree shows the full calculation graph from the SEC origin to the Q3 revenue value.

## Auditability and Reproducibility

Orcaset's openness and flexibility give it strong audit and reproducibility capabilities. Users can define values in any shape, attaching custom metadata, lineage, or validation rules. Unlike spreadsheets, which require special add-ins to link cell values with metadata or validation rules, orcaset incorporates robust custom value types as a core feature. It offers a strongly typed framework for using complex value types that catches incompatible transformations early so users, or their agents, can run analysis with confidence.

## Run the Example

From the repository root (Python 3.14+, network access to `data.sec.gov`):

```sh
uv run python examples/citations/main.py
```
