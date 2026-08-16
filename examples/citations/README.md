# Citations

This example shows how an orcaset model can carry a **citation** on a sourced number: where the figure came from, not just what it equals.

It pulls one revenue figure from SpaceX’s Q2 2026 10-Q (the quarterly report public companies file with the SEC), wraps it as a `Cited` float, then annualizes it. The annualized figure is an ordinary number. To see the filing again, look at the **dependency tree**.

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

`val` is revenue in US dollars: **$7,814,000,000**. `accn` is the EDGAR accession number — the filing’s ID. `frame` is the SEC’s label for that calendar quarter. The example hard-codes `CY2026Q2` so it always uses this row.

## Run

From the repository root (Python 3.14+, network access to `data.sec.gov`):

```sh
uv run python examples/citations/main.py
```

Output:

```txt
Reported CY2026Q2 revenue: 7814000000.0 {'accn': '0001628280-26-052535', 'frame': 'CY2026Q2', 'url': 'https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'}
  type: Cited
Annualized (× 4):         31,256,000,000
  type: float

Dependency tree for annualized revenue:
Annualized revenue@Period(2026-03-31, 2026-06-30) = 31256000000.0
  SpaceX revenue@Period(2026-03-31, 2026-06-30) = Cited(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
    SpaceX revenue.cells = <orcaset.series.Replayable object at 0x...>
    SpaceX revenue@Period(2026-03-31, 2026-06-30) = Cited(7814000000.0, EdgarCitation(accn='0001628280-26-052535', frame='CY2026Q2', url='https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json'))
```

The reported line should match the JSON you opened. The annualized line is that amount times four.

## What to notice

1. **The sourced cell is a `Cited`.** That type is a `float` with extra fields: accession number, frame, and the URL you just visited. Printing it shows the number and the citation together.
2. **The derived cell is a plain `float`.** Multiplying by 4 is ordinary arithmetic, so the extra filing info does not stick to the result. That is deliberate: only the leaf (the number that came from the filing) is `Cited`.
3. **The dependency tree is how you get the citation back.** `ctx.dependencies(annualized, q2)` shows that the $31.3B run-rate came from the `Cited` Q2 revenue. Transformations go through orcaset’s `get_at` / `.map` path, so provenance lives in the graph rather than on every intermediate value.

The fetch runs the first time the revenue cell is demanded in a `Context`, then is cached. Re-printing with the same `Context` does not hit the SEC again.

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

The series is one cell, looked up with `exact` (the period must match). Annualizing is a `.map` that multiplies the reported value by 4:

```py
annualized = revenue.map("Annualized revenue", map_some(lambda reported: reported * 4))
```

`map_some` means “if the input is missing (`Na`), stay missing.” Otherwise `reported * 4` uses `Cited`’s inherited float arithmetic and returns `float`.
