"""Type inference for plain and deferred unfold seeds."""

from collections.abc import Callable
from datetime import date

from orcaset import Chain, Rule, Series, Thunk, UnfoldStep, scan_cells, unfold_cells
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
    exact, seed=Thunk(init), step=step, name="deferred"
)

plain: Series[date, float, Maybe[float]] = Series.unfold(exact, seed=0, step=step, name="plain")

deferred_cells: Chain[date, float] = unfold_cells(
    seed=Thunk(init), step=step, name="deferred cells"
)
plain_cells: Chain[date, float] = unfold_cells(seed=0, step=step, name="plain cells")


def scan(index: int, _key: date, _cell: Rule[float]) -> tuple[float, int]:
    return float(index), index + 1


scanned_deferred: Chain[date, float] = scan_cells(
    deferred_cells, seed=Thunk(init), fn=scan, name="scanned deferred"
)
scanned_plain: Chain[date, float] = scan_cells(plain_cells, seed=0, fn=scan, name="scanned plain")

define: Callable[[UnfoldStep[int, date, float]], Series[date, float, Maybe[float]]] = Series.define(
    exact, seed=Thunk(init), name="defined"
)
defined = define(step)
