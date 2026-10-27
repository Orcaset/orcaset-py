from collections.abc import Generator, Iterator
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Context,
    CycleError,
    DepNode,
    Effect,
    Fn,
    Period,
    Rule,
    Series,
    Thunk,
    Val,
    get,
    get_at,
    keys_until,
    map_cells,
    of_cells,
    scan_cells,
)
from orcaset.maybe import Maybe, Na, isna
from orcaset.query import accrue, accrue_drop, exact, last

MONTH = relativedelta(months=1)
YEAR = relativedelta(years=1, day=31)
MODEL_START = date(2024, 1, 31)

_FISCAL_YEARS = Period.seq(date(2016, 12, 31), YEAR)
FY17 = next(_FISCAL_YEARS)
FY18 = next(_FISCAL_YEARS)
FY19 = next(_FISCAL_YEARS)


def _market_rent_series() -> Series[Period, float, Maybe[float]]:
    rent_growth = Series.of(
        exact,
        [(FY18, 0.035), (FY19, 0.035)],
        name="Rent growth",
    )

    seed: Period | None = None

    @Series.define(exact, seed=seed, name="Market rent")
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

    @Series.define(last, seed=seed, name="Debt")
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

    @Series.define(exact, seed=FY17, name="Poison")
    def poison_step(p: Period):
        return p, Thunk(poison), p.shift(YEAR)

    market_rent = _market_rent_series()
    ctx = Context()

    keys = ctx.get(Fn(lambda: keys_until(market_rent.walk(), FY19), name="probe"))
    poison_keys = ctx.get(Fn(lambda: keys_until(poison_step.walk(), FY19), name="poison probe"))

    assert keys == [FY17, FY18, FY19]
    assert poison_keys == [FY17, FY18, FY19]


def test_ascending_keys_enforced():
    key = date(2024, 1, 31)

    @Series.define(last, seed=0, name="Repeated")
    def repeated_step(state: int):
        return key, float(state), state + 1

    with pytest.raises(ValueError, match="ascending"):
        Context().get_at(repeated_step, date(2024, 2, 29))


def test_domain_cycle_is_terminal():
    k1 = date(2024, 1, 31)
    k2 = date(2024, 2, 29)

    @Series.define(exact, seed=0, name="Domain cycle")
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
    start = Val(first, name="Start date")

    def initial():
        return (yield from get(start))

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        exact,
        seed=Thunk(initial),
        step=step,
        name="Deferred seed",
    )

    first_context = Context()
    assert first_context.get_at(series, first) == 1.0
    assert first_context.depends_on(series._cells, start)
    assert first_context.depends_on((series, first), start)
    head_dependencies = tuple(_flatten(first_context.dependencies(series._cells, structural=True)))
    assert head_dependencies[0].name == "Deferred seed.cells"
    assert any(node.name == "Start date" for node in head_dependencies)

    start.value = second
    second_context = Context()
    assert second_context.get_at(series, second) == 1.0
    assert isna(second_context.get_at(series, first))


def test_thunk_seed_is_lazy_until_head_is_demanded():
    def poison() -> date:
        raise AssertionError("seed resolved")

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        exact,
        seed=Thunk(poison),
        step=step,
        name="Lazy seed",
    )

    with pytest.raises(AssertionError, match="seed resolved"):
        Context().get(series._cells)


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

    series = Series.unfold(exact, seed=0, step=step, name="Verbatim state")
    assert Context().get_at(series, second) == 2.0


def test_self_demanding_thunk_seed_reports_head_cycle():
    key = date(2024, 1, 31)

    def initial():
        yield from get_at(series, key)
        return key

    def step(day: date) -> tuple[date, float, date]:
        return day, 1.0, day + MONTH

    series = Series.unfold(
        exact,
        seed=Thunk(initial),
        step=step,
        name="Seed cycle",
    )

    with pytest.raises(CycleError) as excinfo:
        Context().get_at(series, key)

    assert "Seed cycle.cells" in str(excinfo.value)


def test_thunk_and_plain_values():
    source = Val(2.0, name="source")

    def deferred():
        value = yield from get(source)
        return value * 3.0

    callable_value = lambda: 7.0
    values = Series.of(
        exact,
        [
            (date(2024, 1, 31), 1.0),
            (date(2024, 2, 29), Thunk(deferred)),
            (date(2024, 3, 31), callable_value),
        ],
        name="Values",
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
        exact,
        seed=None,
        step=bad_step,
        name="Generator value",
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

    pairs = Fn(initial_pairs, name="Pairs")
    series = Series.of(exact, pairs, name="Values")
    first_context = Context()

    assert calls == 0
    assert first_context.get_at(series, first) == 1.0
    assert calls == 1
    assert isna(first_context.get_at(series, second))
    assert calls == 1
    assert first_context.depends_on((series, first), pairs)

    pairs._fn = lambda: [(first, 2.0), (second, 3.0)]
    second_context = Context()
    assert second_context.get_at(series, first) == 2.0
    assert second_context.get_at(series, second) == 3.0


def test_map_cells_preserves_keys_and_defers_source_values():
    forced: list[float] = []

    def source_value() -> float:
        forced.append(2.0)
        return 2.0

    source = Series.of(exact, [(MODEL_START, Thunk(source_value))], name="Source")

    def double(_key: date, cell: Rule[float]) -> Thunk[float]:
        def value():
            return (yield from get(cell)) * 2

        return Thunk(value)

    mapped = Series(map_cells(source._cells, double, name="Mapped"), exact, name="Mapped")
    ctx = Context()

    assert ctx.get(Fn(lambda: keys_until(mapped.walk(), MODEL_START), name="keys")) == [MODEL_START]
    assert forced == []
    assert ctx.get_at(mapped, MODEL_START) == 4.0


def test_scan_cells_carries_structural_state():
    d1, d2 = date(2024, 1, 31), date(2024, 2, 29)
    source = Series.of(exact, [(d1, 10), (d2, 20)], name="Source")

    def indexed(index: int, _key: date, cell: Rule[int]) -> tuple[Thunk[int], int]:
        def value():
            return (yield from get(cell)) + index

        return Thunk(value), index + 1

    scanned = Series(
        scan_cells(source._cells, seed=0, fn=indexed, name="Scanned"),
        exact,
        name="Scanned",
    )
    ctx = Context()

    assert ctx.get_at(scanned, d1) == 10
    assert ctx.get_at(scanned, d2) == 21


def test_scan_cells_resolves_thunk_accumulator_seed():
    day = date(2024, 1, 31)
    offset = Val(5, name="Offset")
    source = Series.of(exact, [(day, 10)], name="Source")

    def add_offset(acc: int, _key: date, cell: Rule[int]) -> tuple[Thunk[int], int]:
        return Thunk(lambda: (yield from get(cell)) + acc), acc

    scanned = Series(
        scan_cells(source._cells, seed=Thunk(lambda: get(offset)), fn=add_offset, name="Scanned"),
        exact,
        name="Scanned",
    )
    ctx = Context()

    assert ctx.get_at(scanned, day) == 15
    assert ctx.depends_on(scanned._cells, offset)


def test_empty_series_has_no_cells_and_its_query_answers_every_key():
    q = Period(date(2025, 1, 31), date(2026, 1, 31))
    dropped = Series[Period, float, Maybe[float]].empty(accrue_drop(YF.cmonthly), name="dropped")
    strict = Series[Period, float, Maybe[float]].empty(accrue(YF.cmonthly), name="strict")
    ctx = Context()
    assert ctx.get(dropped._cells) is None
    assert ctx.get_at(dropped, q) == 0.0
    assert isna(ctx.get_at(strict, q))


def test_walk_yields_query_answers_at_cell_keys():
    q1 = Period(date(2024, 12, 31), date(2025, 3, 31))
    q2 = q1.from_end(relativedelta(months=3, day=31))
    rent = Series.of(accrue(YF.cmonthly), [(q1, 30.0), (q2, Na)], name="Rent")
    ctx = Context()

    def items() -> Effect[list[tuple[Period, Maybe[float]]]]:
        out: list[tuple[Period, Maybe[float]]] = []
        node = yield from get(rent.walk())
        while node is not None:
            out.append((node.key, (yield from get(node.value))))
            node = yield from get(node.tail)
        return out

    walked = ctx.get(Fn(items, name="items"))
    assert [key for key, _ in walked] == [q1, q2]
    assert walked[0][1] == ctx.get_at(rent, q1) == 30.0
    assert isna(walked[1][1])
    assert rent.walk() is rent.walk()


def test_walk_reads_keys_without_forcing_values():
    forced: list[int] = []

    def value(i: int) -> Thunk[int]:
        def compute() -> int:
            forced.append(i)
            return i

        return Thunk(compute)

    counter = Series.unfold(exact, seed=0, step=lambda i: (i, value(i), i + 1), name="Counter")
    ctx = Context()

    assert ctx.get(Fn(lambda: keys_until(counter.walk(), 3), name="keys")) == [0, 1, 2, 3]
    assert forced == []
    assert ctx.get(Fn(lambda: get_walked(counter, 2), name="walked")) == 2
    assert forced == [2]


def get_walked(series: Series[int, int, Maybe[int]], key: int) -> Effect[Maybe[int]]:
    node = yield from get(series.walk())
    while node is not None and node.key < key:
        node = yield from get(node.tail)
    assert node is not None and node.key == key
    return (yield from get(node.value))


def test_walk_value_depends_on_the_series_query():
    day = date(2024, 1, 31)
    source = Series.of(exact, [(day, 1.0)], name="Source")
    ctx = Context()
    node = ctx.get(source.walk())
    assert node is not None
    assert ctx.get(node.value) == 1.0
    assert ctx.depends_on(node.value, (source, day))


def test_of_cells_builds_a_standalone_chain():
    chain = of_cells([(1, "a"), (2, Thunk(lambda: "b"))], name="Pairs")
    ctx = Context()
    head = ctx.get(chain)
    assert head is not None and head.key == 1 and ctx.get(head.value) == "a"
    second = ctx.get(head.tail)
    assert second is not None and ctx.get(second.value) == "b"
    assert ctx.get(second.tail) is None
