from collections.abc import Iterator
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import Context, Period, Series, Step, exact, get, get_at

MONTHLY = relativedelta(months=1)
START = date(2026, 1, 1)


def test_cells_yield_pairs_directly():
    @Series.define("direct", exact)
    def series() -> Iterator[tuple[Period, float]]:
        yield Period(START, date(2026, 2, 1)), 10.0
        yield Period(date(2026, 2, 1), date(2026, 3, 1)), 20.0

    ctx = Context()
    assert ctx.get_at(series, Period(START, date(2026, 2, 1))) == 10.0
    assert ctx.get_at(series, Period(date(2026, 2, 1), date(2026, 3, 1))) == 20.0


def test_cells_plain_callable_returns_iterable():
    cells = lambda: zip(Period.seq(START, MONTHLY), [1.0, 2.0])
    series = Series("plain", cells, exact)

    ctx = Context()
    assert ctx.get_at(series, Period(START, date(2026, 2, 1))) == 1.0
    assert ctx.get_at(series, Period(date(2026, 2, 1), date(2026, 3, 1))) == 2.0


def test_cells_step_returns_pairs_after_demanding():
    @Series.define("source", exact)
    def source() -> Iterator[tuple[Period, float]]:
        yield Period(START, date(2026, 2, 1)), 100.0

    @Series.define("dependent", exact)
    def dependent() -> Step[Iterator[tuple[Period, float]]]:
        keys = yield from get(source.keys())

        def pairs() -> Iterator[tuple[Period, float]]:
            for k in keys:
                yield k, 2.0

        return pairs()

    ctx = Context()
    assert ctx.get_at(dependent, Period(START, date(2026, 2, 1))) == 2.0


def test_cells_demand_after_first_pair_raises():
    @Series.define("source", exact)
    def source() -> Iterator[tuple[Period, float]]:
        yield Period(START, date(2026, 2, 1)), 100.0

    @Series.define("late", exact)
    def late():
        yield Period(START, date(2026, 2, 1)), 1.0
        value = yield from get_at(source, Period(START, date(2026, 2, 1)))
        yield Period(date(2026, 2, 1), date(2026, 3, 1)), value

    ctx = Context()
    with pytest.raises(TypeError, match="demanded after the first cell pair"):
        ctx.get_at(late, Period(date(2026, 2, 1), date(2026, 3, 1)))


def test_cells_step_demands_then_yields_pairs():
    @Series.define("source", exact)
    def source() -> Iterator[tuple[Period, float]]:
        yield Period(START, date(2026, 2, 1)), 100.0

    @Series.define("dependent", exact)
    def dependent():
        keys = yield from get(source.keys())
        for k in keys:
            yield k, 2.0

    ctx = Context()
    assert ctx.get_at(dependent, Period(START, date(2026, 2, 1))) == 2.0
