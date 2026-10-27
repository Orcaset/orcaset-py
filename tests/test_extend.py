from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Chain,
    Cons,
    Context,
    Fn,
    Period,
    Series,
    Thunk,
    get,
    get_at,
    keys_until,
    unfold_cells,
)
from orcaset.maybe import Maybe, Na, isna, mul_some, some
from orcaset.query import exact

YEAR = relativedelta(years=1, day=31)

_FISCAL_YEARS = Period.seq(date(2016, 12, 31), YEAR)
FY17 = next(_FISCAL_YEARS)
FY18 = next(_FISCAL_YEARS)
FY19 = next(_FISCAL_YEARS)
FY20 = next(_FISCAL_YEARS)


def test_extend_two_literal_series():
    first = Series.of(exact, [(FY17, 1.0), (FY18, 2.0)], name="First")
    then = Series.of(exact, [(FY19, 3.0), (FY20, 4.0)], name="Then")
    series = Series.extend(
        exact,
        base=first.walk(),
        cont=lambda _: then.walk(),
        name="Extended",
    )
    ctx = Context()

    assert [ctx.get_at(series, p) for p in (FY17, FY18, FY19, FY20)] == [
        1.0,
        2.0,
        3.0,
        4.0,
    ]
    assert ctx.get(Fn(lambda: keys_until(series.walk(), FY20), name="keys")) == [
        FY17,
        FY18,
        FY19,
        FY20,
    ]


def test_extend_lazy_continuation():
    base = Series.of(exact, [(FY17, 1.0)], name="Base")
    calls: list[Period | None] = []

    def cont(last: Cons[Period, Maybe[float]] | None):
        assert last is not None
        calls.append(last.key)

        def step(period: Period) -> tuple[Period, float, Period]:
            return period, float(period.end.year), period.shift(YEAR)

        return unfold_cells(seed=FY18, step=step, name="Continuation")

    series = Series.extend(exact, base=base.walk(), cont=cont, name="Extended")
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

    base = Series.of(exact, [(FY17, 1.0)], name="Base")
    continuation = Series.of(
        exact,
        [(FY17, Thunk(poison)), (FY18, 2.0), (FY19, 3.0)],
        name="Continuation",
    )
    series = Series.extend(
        exact,
        base=base.walk(),
        cont=lambda _last: continuation.walk(),
        name="Extended",
    )
    ctx = Context()

    assert ctx.get_at(series, FY17) == 1.0
    with pytest.raises(ValueError, match="strictly ascending"):
        ctx.get_at(series, FY18)
    assert forced == []


def test_extend_empty_base():
    base = Series.of(exact, [], name="Empty")
    continuation = Series.of(exact, [(FY17, 1.0), (FY18, 2.0)], name="Continuation")
    calls: list[Cons[Period, Maybe[float]] | None] = []

    def cont(last: Cons[Period, Maybe[float]] | None):
        calls.append(last)
        return continuation.walk()

    series = Series.extend(exact, base=base.walk(), cont=cont, name="Extended")
    ctx = Context()

    assert ctx.get_at(series, FY17) == 1.0
    assert ctx.get_at(series, FY18) == 2.0
    assert calls == [None]


def test_extend_self_referential_compounding():
    base = Series.of(exact, [(FY17, some(1.777777778))], name="Base rent")
    growth = Series.of(exact, [(FY18, 0.035), (FY19, 0.035)], name="Growth")

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
            seed=last.key.shift(YEAR),
            step=step,
            name="Market rent continuation",
        )

    market_rent: Series[Period, Maybe[float], Maybe[float]] = Series.extend(
        exact,
        base=base.walk(),
        cont=cont,
        name="Market rent",
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

    base = Series.of(exact, [(FY17, observed(FY17, 2.0)), (FY18, observed(FY18, 3.0))], name="Base")

    def cont(last: Cons[Period, Maybe[float]] | None) -> Chain[Period, Maybe[float]]:
        assert last is not None
        last_cell = last.value

        def step(period: Period) -> tuple[Period, Thunk[Maybe[float]], Period]:
            return (
                period,
                Thunk(lambda: mul_some((yield from get(last_cell)), 10.0)),
                period.shift(YEAR),
            )

        return unfold_cells(
            seed=last.key.shift(YEAR),
            step=step,
            name="Continuation",
        )

    series = Series.extend(exact, base=base.walk(), cont=cont, name="Extended")
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

    actuals = unfold_cells(seed=(FY17, None), step=actuals_step, name="Actuals")

    def cont(last: Cons[Period, float] | None) -> Chain[Period, float]:
        assert last is not None

        def step(period: Period) -> tuple[Period, float, Period]:
            return period, 100.0, period.shift(YEAR)

        return unfold_cells(
            seed=last.key.shift(YEAR),
            step=step,
            name="Continuation",
        )

    extended: Series[Period, float, Maybe[float]] = Series.extend(
        exact, base=actuals, cont=cont, name="Extended"
    )
    ctx = Context()

    assert [ctx.get_at(extended, p) for p in (FY17, FY18, FY19, FY20)] == [1.0, 2.0, 100.0, 100.0]
