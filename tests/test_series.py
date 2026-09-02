from collections.abc import Generator, Iterator
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Cell,
    Context,
    CycleError,
    DepNode,
    Maybe,
    Na,
    Period,
    Series,
    Thunk,
    exact,
    get,
    get_at,
    isna,
    keys_until,
    last,
)

MONTH = relativedelta(months=1)
YEAR = relativedelta(years=1, day=31)
MODEL_START = date(2024, 1, 31)

_FISCAL_YEARS = Period.seq(date(2016, 12, 31), YEAR)
FY17 = next(_FISCAL_YEARS)
FY18 = next(_FISCAL_YEARS)
FY19 = next(_FISCAL_YEARS)


def _market_rent_series() -> Series[Period, float, Maybe[float]]:
    rent_growth = Series.of(
        "Rent growth",
        exact,
        [(FY18, 0.035), (FY19, 0.035)],
    )

    seed: Period | None = None

    @Series.define("Market rent", exact, seed=seed)
    def market_rent(p: Period | None):
        if p is None:
            return FY17, 1.777777778, FY18

        def cell():
            prior = yield from get_at(market_rent, p.shift(-YEAR))
            growth = yield from get_at(rent_growth, p)
            if isna(prior) or isna(growth):
                return Na
            return prior * (1.0 + growth)

        return p, Thunk(cell), p.shift(YEAR)

    return market_rent


def _flatten(node: DepNode) -> Iterator[DepNode]:
    yield node
    for child in node.deps:
        yield from _flatten(child)


def test_debt_recurrence():
    first_period = Period(MODEL_START, MODEL_START + MONTH)
    seed: Period | None = None

    @Series.define("Debt", last, seed=seed)
    def debt(p: Period | None):
        if p is None:
            return MODEL_START, 100.0, first_period

        def cell():
            begin = yield from get_at(debt, p.start)
            if isna(begin):
                return Na
            return begin * 1.01

        return p.end, Thunk(cell), p.shift(MONTH)

    third_period = first_period
    for _ in range(3):
        third_period = third_period.shift(MONTH)

    ctx = Context()
    assert ctx.get_at(debt, MODEL_START) == 100.0
    assert ctx.get_at(debt, third_period.start) == pytest.approx(100.0 * 1.01**3)


def test_partial_walk_memoization_and_laziness():
    market_rent = _market_rent_series()
    ctx = Context()

    assert ctx.get_at(market_rent, FY18) == pytest.approx(1.777777778 * 1.035)

    dependencies = tuple(_flatten(ctx.dependencies(market_rent, FY18)))
    assert not any(node.key == FY19 and "Rent growth" in node.name for node in dependencies)
    assert not any(node.name == f"Market rent.tail@{FY18}" for node in dependencies)
    assert not any(node.name == "Market rent" and node.key == FY19 for node in dependencies)

    assert ctx.get_at(market_rent, FY19) == pytest.approx(1.777777778 * 1.035 * 1.035)


def test_keys_until():
    def poison() -> float:
        raise AssertionError("keys_until forced a cell value")

    @Series.define("Poison", exact, seed=FY17)
    def poison_step(p: Period):
        return p, Thunk(poison), p.shift(YEAR)

    market_rent = _market_rent_series()
    ctx = Context()

    keys = ctx.get(Cell("probe", lambda: keys_until(market_rent.cells, FY19)))
    poison_keys = ctx.get(Cell("poison probe", lambda: keys_until(poison_step.cells, FY19)))

    assert keys == [FY17, FY18, FY19]
    assert poison_keys == [FY17, FY18, FY19]


def test_ascending_keys_enforced():
    key = date(2024, 1, 31)

    @Series.define("Repeated", last, seed=0)
    def repeated_step(state: int):
        return key, float(state), state + 1

    with pytest.raises(ValueError, match="ascending"):
        Context().get_at(repeated_step, date(2024, 2, 29))


def test_domain_cycle_is_terminal():
    k1 = date(2024, 1, 31)
    k2 = date(2024, 2, 29)

    @Series.define("Domain cycle", exact, seed=0)
    def cycle_step(state: int):
        if state == 0:
            return k1, 1.0, 1
        future = yield from get_at(cycle_step, k2)
        return k2, future, state + 1

    with pytest.raises(CycleError) as excinfo:
        Context().get_at(cycle_step, k2)

    assert ".tail@" in str(excinfo.value)


def test_thunk_and_plain_values():
    source = Cell("source", lambda: 2.0)

    def deferred():
        value = yield from get(source)
        return value * 3.0

    callable_value = lambda: 7.0
    values = Series.of(
        "Values",
        exact,
        [
            (date(2024, 1, 31), 1.0),
            (date(2024, 2, 29), Thunk(deferred)),
            (date(2024, 3, 31), callable_value),
        ],
    )
    ctx = Context()

    assert ctx.get_at(values, date(2024, 1, 31)) == 1.0
    assert ctx.get_at(values, date(2024, 2, 29)) == 6.0
    assert ctx.get_at(values, date(2024, 3, 31)) is callable_value

    def live_generator() -> Generator[None, None, float]:
        if False:
            yield
        return 1.0

    bad = Series.unfold(
        "Generator value",
        exact,
        seed=None,
        step=lambda state: (date(2024, 1, 31), live_generator(), state),
    )

    with pytest.raises(TypeError, match="Thunk"):
        Context().get_at(bad, date(2024, 1, 31))
