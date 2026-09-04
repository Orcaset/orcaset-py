from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Cell,
    Cells,
    Cons,
    Context,
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
    some,
    unfold_cells,
)

YEAR = relativedelta(years=1, day=31)

_FISCAL_YEARS = Period.seq(date(2016, 12, 31), YEAR)
FY17 = next(_FISCAL_YEARS)
FY18 = next(_FISCAL_YEARS)
FY19 = next(_FISCAL_YEARS)
FY20 = next(_FISCAL_YEARS)


def test_append_two_literal_series():
    first = Series.of("First", exact, [(FY17, 1.0), (FY18, 2.0)])
    then = Series.of("Then", exact, [(FY19, 3.0), (FY20, 4.0)])
    series = Series.append(
        "Appended",
        exact,
        first=first.cells,
        then=then.cells,
    )
    ctx = Context()

    assert [ctx.get_at(series, p) for p in (FY17, FY18, FY19, FY20)] == [
        1.0,
        2.0,
        3.0,
        4.0,
    ]
    assert ctx.get(Cell("keys", lambda: keys_until(series.cells, FY20))) == [
        FY17,
        FY18,
        FY19,
        FY20,
    ]


def test_extend_lazy_continuation():
    base = Series.of("Base", exact, [(FY17, 1.0)])
    calls: list[Period | None] = []

    def cont(last: Cons[Period, float] | None):
        assert last is not None
        calls.append(last.key)
        return unfold_cells(
            "Continuation",
            seed=FY18,
            step=lambda p: (p, float(p.end.year), p.shift(YEAR)),
        )

    series = Series.extend("Extended", exact, base=base.cells, cont=cont)
    ctx = Context()

    assert ctx.get_at(series, FY17) == 1.0
    assert calls == []
    assert ctx.get_at(series, FY18) == float(FY18.end.year)
    assert calls == [FY17]
    assert ctx.get_at(series, FY19) == float(FY19.end.year)
    assert calls == [FY17]


def test_extend_rejects_overlapping_continuation():
    forced: list[bool] = []

    def poison() -> float:
        forced.append(True)
        raise AssertionError("overlapping continuation cell was forced")

    base = Series.of("Base", exact, [(FY17, 1.0)])
    continuation = Series.of(
        "Continuation",
        exact,
        [(FY17, Thunk(poison)), (FY18, 2.0), (FY19, 3.0)],
    )
    series = Series.extend(
        "Extended",
        exact,
        base=base.cells,
        cont=lambda _last: continuation.cells,
    )
    ctx = Context()

    assert ctx.get_at(series, FY17) == 1.0
    with pytest.raises(ValueError, match="strictly ascending"):
        ctx.get_at(series, FY18)
    assert forced == []


def test_extend_empty_base():
    base = Series.of("Empty", exact, [])
    continuation = Series.of("Continuation", exact, [(FY17, 1.0), (FY18, 2.0)])
    calls: list[Cons[Period, float] | None] = []

    def cont(last: Cons[Period, float] | None):
        calls.append(last)
        return continuation.cells

    series = Series.extend("Extended", exact, base=base.cells, cont=cont)
    ctx = Context()

    assert ctx.get_at(series, FY17) == 1.0
    assert ctx.get_at(series, FY18) == 2.0
    assert calls == [None]


def test_extend_self_referential_compounding():
    base = Series.of("Base rent", exact, [(FY17, some(1.777777778))])
    growth = Series.of("Growth", exact, [(FY18, 0.035), (FY19, 0.035)])

    def cont(last: Cons[Period, Maybe[float]] | None):
        assert last is not None

        def step(p: Period):
            def cell():
                prior = yield from get_at(market_rent, p.shift(-YEAR))
                rate = yield from get_at(growth, p)
                if isna(prior) or isna(rate):
                    return Na
                return prior * (1.0 + rate)

            return p, Thunk(cell), p.shift(YEAR)

        return unfold_cells(
            "Market rent continuation",
            seed=last.key.shift(YEAR),
            step=step,
        )

    market_rent: Series[Period, Maybe[float], Maybe[float]] = Series.extend(
        "Market rent",
        exact,
        base=base.cells,
        cont=cont,
    )
    ctx = Context()

    fy18_value = 1.777777778 * 1.035
    assert ctx.get_at(market_rent, FY17) == 1.777777778
    assert ctx.get_at(market_rent, FY18) == pytest.approx(fy18_value)
    assert ctx.get_at(market_rent, FY19) == pytest.approx(fy18_value * 1.035)


def test_extend_continuation_reads_last_cell():
    forced: list[Period] = []

    def observed(period: Period, value: float) -> Thunk[float]:
        def cell() -> float:
            forced.append(period)
            return value

        return Thunk(cell)

    base = Series.of("Base", exact, [(FY17, observed(FY17, 2.0)), (FY18, observed(FY18, 3.0))])

    def cont(last: Cons[Period, float] | None) -> Cells[Period, float]:
        assert last is not None
        return unfold_cells(
            "Continuation",
            seed=last.key.shift(YEAR),
            step=lambda p: (p, Thunk(lambda: (yield from get(last.cell)) * 10.0), p.shift(YEAR)),
        )

    series = Series.extend("Extended", exact, base=base.cells, cont=cont)
    ctx = Context()

    assert ctx.get_at(series, FY19) == 30.0
    assert ctx.get_at(series, FY20) == 30.0
    assert forced == [FY18]


def test_extend_base_tail_may_depend_on_extended_series():
    """The frontier is found without peeking, so a base tail may consult the
    extended series at the key it just emitted (a case-3 tail) without a cycle."""

    def actuals_step(state: tuple[Period, Period | None]):
        period, prev = state
        if prev is not None:
            current = yield from get_at(extended, prev)
            if not isna(current) and current >= 2.0:
                return None
        return period, float(period.start.year - 2015), (period.shift(YEAR), period)

    actuals = unfold_cells("Actuals", seed=(FY17, None), step=actuals_step)

    def cont(last: Cons[Period, float] | None) -> Cells[Period, float]:
        assert last is not None
        return unfold_cells(
            "Continuation",
            seed=last.key.shift(YEAR),
            step=lambda p: (p, 100.0, p.shift(YEAR)),
        )

    extended: Series[Period, float, Maybe[float]] = Series.extend(
        "Extended", exact, base=actuals, cont=cont
    )
    ctx = Context()

    assert [ctx.get_at(extended, p) for p in (FY17, FY18, FY19, FY20)] == [1.0, 2.0, 100.0, 100.0]
