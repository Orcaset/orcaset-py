from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Cell,
    Context,
    Maybe,
    Na,
    Period,
    Series,
    Thunk,
    accrual,
    add_some,
    covered,
    exact,
    extend_period_series,
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

    def cont(last: Period | None):
        calls.append(last)
        assert last == FY17
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


def test_extend_clips_overlapping_continuation():
    forced: list[bool] = []

    def poison() -> float:
        forced.append(True)
        raise AssertionError("clipped continuation cell was forced")

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

    assert ctx.get(Cell("keys", lambda: keys_until(series.cells, FY19))) == [
        FY17,
        FY18,
        FY19,
    ]
    assert ctx.get_at(series, FY17) == 1.0
    assert ctx.get_at(series, FY18) == 2.0
    assert forced == []


def test_extend_empty_base():
    base = Series.of("Empty", exact, [])
    continuation = Series.of("Continuation", exact, [(FY17, 1.0), (FY18, 2.0)])
    calls: list[Period | None] = []

    def cont(last: Period | None):
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

    def cont(last: Period | None):
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
            seed=last.shift(YEAR),
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


def test_extend_period_series_preserves_query_policies_across_seam():
    history = Series.of("History", covered, [(FY17, 365.0)])
    calls: list[Period | None] = []

    def cont(last: Period | None) -> Series[Period, float, Maybe[float]]:
        calls.append(last)
        return Series.of(
            "Forecast",
            accrual(lambda start, end: float((end - start).days)),
            [(FY18, 365.0)],
        )

    combined = extend_period_series(
        "Combined",
        history,
        cont,
        lambda left, right: add_some((left, right)),
    )
    ctx = Context()

    partial_history = Period(FY17.start, date(2017, 6, 30))
    partial_forecast = Period(FY18.start, date(2018, 6, 30))
    crossing = Period(FY17.start, partial_forecast.end)

    assert isna(ctx.get_at(combined, partial_history))
    assert ctx.get_at(combined, partial_forecast) == pytest.approx(181.0)
    assert ctx.get_at(combined, crossing) == pytest.approx(546.0)
    assert calls == [FY17]
