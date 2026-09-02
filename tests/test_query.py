# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

from orcaset import (
    YF,
    Cell,
    Context,
    Maybe,
    Na,
    Period,
    Series,
    Thunk,
    accrual,
    covered,
    exact,
    isna,
    last,
)

START = date(2026, 1, 1)
P1 = Period(START, date(2026, 2, 1))
P2 = Period(date(2026, 2, 1), date(2026, 3, 1))
P3 = Period(date(2026, 3, 1), date(2026, 4, 1))
Q1 = Period(START, date(2026, 4, 1))


def test_exact_returns_na_on_miss():
    series = Series.of("values", exact, [(P1, 10.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert ctx.get_at(series, P2) is Na


def test_last_returns_latest_at_or_before_query():
    d0, d1, d2 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
    series = Series.of("balance", last, [(d0, 100.0), (d1, 110.0), (d2, 120.0)])

    ctx = Context()
    assert ctx.get_at(series, d0) == 100.0
    assert ctx.get_at(series, date(2026, 2, 15)) == 110.0
    assert ctx.get_at(series, d2) == 120.0
    assert ctx.get_at(series, date(2026, 4, 1)) == 120.0


def test_last_returns_na_before_first_observation():
    series = Series.of("balance", last, [(date(2026, 2, 1), 110.0)])

    assert Context().get_at(series, date(2026, 1, 1)) is Na


def test_last_never_forces_superseded_cells():
    def poison() -> float:
        raise AssertionError("superseded cell was forced")

    series = Series.of(
        "balance",
        last,
        [(date(2026, 1, 1), Thunk(poison)), (date(2026, 2, 1), 110.0)],
    )

    assert Context().get_at(series, date(2026, 2, 15)) == 110.0


def test_accrual_exact_hit_returns_cell_unchanged():
    series = Series.of("revenue", accrual(YF.cmonthly), [(P1, 100.0), (P2, 200.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 100.0
    assert ctx.get_at(series, P2) == 200.0


def test_accrual_weights_overlap_by_yf():
    series = Series.of("revenue", accrual(lambda a, b: (b - a).days), [(Q1, 90.0)])

    ctx = Context()
    # 31 / 90 of the quarter lands in January.
    assert ctx.get_at(series, P1) == 90.0 * 31 / 90
    # A query spanning the quarter end takes only the covered share.
    assert ctx.get_at(series, Period(P3.start, date(2026, 5, 1))) == 90.0 * 31 / 90


def test_accrual_sums_across_multiple_cells():
    series = Series.of(
        "revenue",
        accrual(lambda a, b: (b - a).days),
        [(P1, 31.0), (P2, 28.0), (P3, 31.0)],
    )

    ctx = Context()
    assert ctx.get_at(series, Q1) == 90.0
    # Half of January plus all of February.
    mid_jan = date(2026, 1, 16)
    assert ctx.get_at(series, Period(mid_jan, P2.end)) == 31.0 * 16 / 31 + 28.0


def test_accrual_returns_na_on_miss():
    series = Series.of("revenue", accrual(YF.cmonthly), [(P1, 100.0)])

    assert Context().get_at(series, P3) is Na


def test_accrual_propagates_na_cells():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "revenue", accrual(YF.cmonthly), [(P1, 100.0), (P2, Na)]
    )

    ctx = Context()
    assert isna(ctx.get_at(series, Period(P1.start, P2.end)))
    # An exact hit passes the cell through, Na included.
    assert ctx.get_at(series, P2) is Na


def test_accrual_never_forces_cells_outside_query():
    def poison() -> float:
        raise AssertionError("cell outside the query was forced")

    series = Series.of(
        "revenue",
        accrual(lambda a, b: (b - a).days),
        [(P1, Thunk(poison)), (P2, 20.0), (P3, Thunk(poison))],
    )

    assert Context().get_at(series, Period(P2.start, date(2026, 2, 15))) == 20.0 * 14 / 28


def test_covered_sums_adjacent_cells():
    series = Series.of("revenue", covered, [(P1, 10.0), (P2, 20.0), (P3, 30.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert ctx.get_at(series, Period(P1.start, P2.end)) == 30.0
    assert ctx.get_at(series, Q1) == 60.0


def test_covered_returns_na_on_partial_or_gap():
    series = Series.of("revenue", covered, [(P1, 10.0), (P3, 30.0)])

    ctx = Context()
    assert isna(ctx.get_at(series, Period(P1.start, date(2026, 1, 15))))
    assert isna(ctx.get_at(series, Period(date(2026, 1, 15), P1.end)))
    assert isna(ctx.get_at(series, Q1))
    assert isna(ctx.get_at(series, P2))


def test_covered_propagates_na_cells():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "revenue", covered, [(P1, 10.0), (P2, Na)]
    )

    assert isna(Context().get_at(series, Period(P1.start, P2.end)))


def test_covered_works_over_an_infinite_chain():
    from dateutil.relativedelta import relativedelta

    series = Series.unfold(
        "revenue",
        covered,
        seed=START,
        step=lambda d: (Period(d, d + relativedelta(months=1)), 1.0, d + relativedelta(months=1)),
    )

    ctx = Context()
    assert ctx.get_at(series, Q1) == 3.0
    assert ctx.get(Cell("probe", lambda: covered(P2, series.cells))) == 1.0
