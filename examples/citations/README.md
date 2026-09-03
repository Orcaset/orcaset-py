# Citations and Data Provenance

This example shows how values in an orcaset model can carry provenance information, allowing users to trace a value back to its source.

The model fetches SpaceX's Q2 2026 revenue from the SEC's EDGAR API and projects revenue at 10% quarterly growth. The sourced value carries its filing accession number, XBRL frame, and source URL while remaining usable anywhere a `float` is accepted.

## Custom Values

Orcaset series can contain custom value types, not only built-in numeric types. This example defines a citation record and a numeric type that carries one.

### `EdgarCitation`

`EdgarCitation` records the filing identifier, XBRL frame, and SEC URL:

```py
@dataclass(frozen=True, slots=True)
class EdgarCitation:
    accn: str
    frame: str
    url: str

    def __str__(self) -> str:
        return str({"accn": self.accn, "frame": self.frame, "url": self.url})
```

### `CitedFloat`

`CitedFloat` subclasses `float`, so it behaves like a normal number while exposing its source through the `citation` attribute:

```py
class CitedFloat(float):
    """A float carrying EDGAR provenance. Arithmetic operations return a plain float."""

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
        return str(self) if spec == "" else format(float(self), spec)
```

Because `float` is immutable, its value is initialized in `__new__`. Standard arithmetic on a `CitedFloat` returns a plain `float`; orcaset's dependency graph retains the connection from those derived values to the cited input.

## Fetching Data from EDGAR

The example reads the SEC [`companyconcept`](https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json) endpoint and selects the USD fact whose XBRL frame is `CY2026Q2`.

`load_frame` wraps the fact's numeric value and source fields together:

```py
def load_frame(url: str, frame: str) -> CitedFloat:
    with urlopen(Request(url, headers=_HEADERS), timeout=30.0) as response:
        payload: object = json.load(response)
    assert isinstance(payload, dict)
    fact = next(row for row in payload["units"]["USD"] if row.get("frame") == frame)
    return CitedFloat(float(fact["val"]), EdgarCitation(fact["accn"], frame, url))
```

## Revenue Model

`Series.define` is the decorator form of `Series.unfold`. The seed is Q2 2026, and each call returns the current period, its value, and the next period.

```py
@Series.define("SpaceX revenue", accrual(YF.cmonthly), seed=Q2_2026)
def revenue(
    period: Period,
) -> Effect[tuple[Period, Maybe[float] | Thunk[Maybe[float]], Period]]:
    if period == Q2_2026:
        value = Thunk(lambda: load_frame(CONCEPT_URL, FRAME))
    else:
        prior = yield from get_at(revenue, period.from_start(-QUARTER))
        value = multiply_some((prior, 1.10))

    return period, value, period.from_end(QUARTER)
```

The initial `Thunk` defers the HTTP request until Q2's value is demanded. For each forecast quarter, `get_at` requests the prior quarter inside the model's `Effect`, recording that dependency, and `multiply_some` applies 10% growth while propagating `Na` if the prior value is unavailable.

The series' cell values are `Maybe[float]`. A `CitedFloat` satisfies the `float` side of that type, so the cited actual and ordinary forecast values compose in the same series without discarding the actual's metadata.

## Inspecting Provenance

The cited value formats like an ordinary number:

```text
Period(2026-03-31, 2026-06-30) revenue: 7,814,000,000
Period(2026-06-30, 2026-09-30) revenue: 8,595,400,000
Period(2026-09-30, 2026-12-31) revenue: 9,454,940,000
```

It also retains its source metadata:

```py
q2_revenue = ctx.get_at(revenue, Q2_2026)
if isinstance(q2_revenue, CitedFloat):
    print(q2_revenue.citation)
```

```text
{'accn': '0001628280-26-052535', 'frame': 'CY2026Q2', 'url': 'https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'}
```

Q3 is a plain `float`, but `Context.dependencies` shows that it was derived from the cited Q2 value:

```text
SpaceX revenue@Period(2026-06-30, 2026-09-30) = 8595400000.0
  SpaceX revenue@Period(2026-03-31, 2026-06-30) = CitedFloat(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
```

Together, custom values and dependency tracking provide both direct provenance for sourced inputs and lineage for values derived from them.

## Run the Example

From the repository root, using Python 3.14+ with network access to `data.sec.gov`:

```sh
uv run python examples/citations/main.py
```
