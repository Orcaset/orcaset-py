"""Type inference for plain and deferred unfold seeds."""

from collections.abc import Callable
from datetime import date

from orcaset import Cells, Rule, Series, Thunk, UnfoldStep, scan_cells, unfold_cells
from orcaset.maybe import Maybe
from orcaset.query import exact

D = date(2026, 1, 31)


def init() -> int:
    return 0


def step(index: int) -> tuple[date, float, int] | None:
    if index > 0:
        return None
    return D, 1.0, index + 1


deferred: Series[date, float, Maybe[float]] = Series.unfold(
    "deferred", exact, seed=Thunk(init), step=step
)

plain: Series[date, float, Maybe[float]] = Series.unfold("plain", exact, seed=0, step=step)

deferred_cells: Cells[date, float] = unfold_cells("deferred cells", seed=Thunk(init), step=step)
plain_cells: Cells[date, float] = unfold_cells("plain cells", seed=0, step=step)


def scan(index: int, _key: date, _cell: Rule[float]) -> tuple[float, int]:
    return float(index), index + 1


scanned_deferred: Cells[date, float] = scan_cells(
    "scanned deferred", deferred_cells, seed=Thunk(init), fn=scan
)
scanned_plain: Cells[date, float] = scan_cells("scanned plain", plain_cells, seed=0, fn=scan)

define: Callable[[UnfoldStep[int, date, float]], Series[date, float, Maybe[float]]] = Series.define(
    "defined", exact, seed=Thunk(init)
)
defined = define(step)
