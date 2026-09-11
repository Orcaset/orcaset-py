from collections.abc import Generator, Iterator
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Cell,
    Context,
    CycleError,
    DepNode,
    Period,
    Rule,
    Series,
    Thunk,
    get,
    get_at,
    keys_until,
    map_cells,
    scan_cells,
)
from orcaset.maybe import Maybe, Na, isna
from orcaset.query import exact, last

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
    assert not any(node.name.endswith(".cells") or ".tail@" in node.name for node in dependencies)
    assert not any(node.key == FY19 and "Rent growth" in node.name for node in dependencies)
    assert not any(node.name == f"Market rent.tail@{FY18}" for node in dependencies)
    assert not any(node.name == "Market rent" and node.key == FY19 for node in dependencies)

    structural = tuple(_flatten(ctx.dependencies(market_rent, FY18, structural=True)))
    assert any(node.name.endswith(".cells") or ".tail@" in node.name for node in structural)

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


def test_thunk_seed_tracks_dependency_and_changes_domain_between_contexts():
    first = date(2024, 1, 31)
    second = date(2024, 2, 29)
    start = Cell("Start date", lambda: first)

    def initial():
        return (yield from get(start))

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        "Deferred seed",
        exact,
        seed=Thunk(initial),
        step=step,
    )

    first_context = Context()
    assert first_context.get_at(series, first) == 1.0
    assert first_context.depends_on(series.cells, start)
    assert first_context.depends_on((series, first), start)
    head_dependencies = tuple(
        _flatten(first_context.rule_dependencies(series.cells, structural=True))
    )
    assert head_dependencies[0].name == "Deferred seed.cells"
    assert any(node.name == "Start date" for node in head_dependencies)

    start.fn = lambda: second
    second_context = Context()
    assert second_context.get_at(series, second) == 1.0
    assert isna(second_context.get_at(series, first))


def test_thunk_seed_is_lazy_until_head_is_demanded():
    def poison() -> date:
        raise AssertionError("seed resolved")

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        "Lazy seed",
        exact,
        seed=Thunk(poison),
        step=step,
    )

    with pytest.raises(AssertionError, match="seed resolved"):
        Context().get(series.cells)


def test_next_state_is_not_resolved_as_a_seed():
    first = date(2024, 1, 31)
    second = date(2024, 2, 29)

    def poison() -> int:
        raise AssertionError("next state resolved")

    next_state = Thunk(poison)

    def step(state: int | Thunk[int]) -> tuple[date, float, int | Thunk[int]]:
        if state == 0:
            return first, 1.0, next_state
        assert state is next_state
        return second, 2.0, 1

    series = Series.unfold("Verbatim state", exact, seed=0, step=step)
    assert Context().get_at(series, second) == 2.0


def test_self_demanding_thunk_seed_reports_head_cycle():
    key = date(2024, 1, 31)

    def initial():
        yield from get_at(series, key)
        return key

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        "Seed cycle",
        exact,
        seed=Thunk(initial),
        step=step,
    )

    with pytest.raises(CycleError) as excinfo:
        Context().get_at(series, key)

    assert "Seed cycle.cells" in str(excinfo.value)


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

    def bad_step(state: None) -> tuple[date, Generator[None, None, float], None]:
        return date(2024, 1, 31), live_generator(), state

    bad = Series.unfold(
        "Generator value",
        exact,
        seed=None,
        step=bad_step,
    )

    with pytest.raises(TypeError, match="Thunk"):
        Context().get_at(bad, date(2024, 1, 31))


def test_of_accepts_rule_pairs_updated_between_contexts():
    first = date(2024, 1, 31)
    second = date(2024, 2, 29)
    calls = 0

    def initial_pairs() -> list[tuple[date, float]]:
        nonlocal calls
        calls += 1
        return [(first, 1.0)]

    pairs = Cell("Pairs", initial_pairs)
    series = Series.of("Values", exact, pairs)
    first_context = Context()

    assert calls == 0
    assert first_context.get_at(series, first) == 1.0
    assert calls == 1
    assert isna(first_context.get_at(series, second))
    assert calls == 1
    assert first_context.depends_on((series, first), pairs)

    pairs.fn = lambda: [(first, 2.0), (second, 3.0)]
    second_context = Context()
    assert second_context.get_at(series, first) == 2.0
    assert second_context.get_at(series, second) == 3.0


def test_map_cells_preserves_keys_and_defers_source_values():
    forced: list[float] = []

    def source_value() -> float:
        forced.append(2.0)
        return 2.0

    source = Series.of("Source", exact, [(MODEL_START, Thunk(source_value))])

    def double(_key: date, cell: Rule[float]) -> Thunk[float]:
        def value():
            return (yield from get(cell)) * 2

        return Thunk(value)

    mapped = Series("Mapped", map_cells("Mapped", source.cells, double), exact)
    ctx = Context()

    assert ctx.get(Cell("keys", lambda: keys_until(mapped.cells, MODEL_START))) == [MODEL_START]
    assert forced == []
    assert ctx.get_at(mapped, MODEL_START) == 4.0


def test_scan_cells_carries_structural_state():
    d1, d2 = date(2024, 1, 31), date(2024, 2, 29)
    source = Series.of("Source", exact, [(d1, 10), (d2, 20)])

    def indexed(index: int, _key: date, cell: Rule[int]) -> tuple[Thunk[int], int]:
        def value():
            return (yield from get(cell)) + index

        return Thunk(value), index + 1

    scanned = Series(
        "Scanned",
        scan_cells("Scanned", source.cells, seed=0, fn=indexed),
        exact,
    )
    ctx = Context()

    assert ctx.get_at(scanned, d1) == 10
    assert ctx.get_at(scanned, d2) == 21


def test_scan_cells_resolves_thunk_accumulator_seed():
    day = date(2024, 1, 31)
    offset = Cell("Offset", lambda: 5)
    source = Series.of("Source", exact, [(day, 10)])

    def add_offset(acc: int, _key: date, cell: Rule[int]) -> tuple[Thunk[int], int]:
        return Thunk(lambda: (yield from get(cell)) + acc), acc

    scanned = Series(
        "Scanned",
        scan_cells("Scanned", source.cells, seed=Thunk(lambda: get(offset)), fn=add_offset),
        exact,
    )
    ctx = Context()

    assert ctx.get_at(scanned, day) == 15
    assert ctx.depends_on(scanned.cells, offset)
