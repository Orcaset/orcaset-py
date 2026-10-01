# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

import pytest

import orcaset
from orcaset import (
    YF,
    Context,
    Fn,
    Period,
    QueryFn,
    Series,
    Thunk,
)
from orcaset.maybe import Maybe, Na, isna
from orcaset.query import (
    accrue,
    accrue_drop,
    avg,
    avg_drop,
    avg_fill,
    covered,
    exact,
    exact_or,
    filled,
    last,
    last_or,
)

START = date(2026, 1, 1)
P1 = Period(START, date(2026, 2, 1))
P2 = Period(date(2026, 2, 1), date(2026, 3, 1))
P3 = Period(date(2026, 3, 1), date(2026, 4, 1))
Q1 = Period(START, date(2026, 4, 1))


def days(start: date, end: date) -> float:
    return (end - start).days


def test_query_helpers_are_exported_only_from_query_module():
    helpers = {
        "DayCount",
        "accrue",
        "accrue_drop",
        "avg",
        "avg_drop",
        "avg_fill",
        "covered",
        "exact",
        "exact_or",
        "filled",
        "last",
        "last_or",
    }

    assert set(orcaset.query.__all__) == helpers
    assert all(not hasattr(orcaset, helper) for helper in helpers)


def test_filled_lifts_float_fold():
    assert isna(filled(sum)([1.0, Na]))
    assert filled(sum, 0.0)([1.0, Na]) == 1.0
    assert filled(sum, 0.0)([Na, Na]) == 0.0
    assert filled(sum)([1.0, 2.0]) == 3.0


def test_exact_returns_na_on_miss():
    series = Series.of("values", exact, [(P1, 10.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert ctx.get_at(series, P2) is Na


def test_exact_does_not_force_tail_after_incomparable_key():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P2:
            raise AssertionError("tail after an incomparable key was forced")
        return P1, 10.0, P2

    series = Series.unfold("values", exact, seed=P1, step=step)
    query_period = Period(date(2026, 1, 15), date(2026, 2, 15))

    assert Context().get_at(series, query_period) is Na


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


def test_last_does_not_force_tail_after_incomparable_key():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P2:
            raise AssertionError("tail after an incomparable key was forced")
        return P1, 10.0, P2

    series = Series.unfold("balance", last, seed=P1, step=step)
    query_period = Period(date(2026, 1, 15), date(2026, 2, 15))

    assert Context().get_at(series, query_period) is Na


def test_exact_or_and_last_or_replace_misses():
    d0, d1, d2 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)
    exact_series = Series.of("Exact default", exact_or(0.0), [(d1, 10.0)])
    last_series = Series.of("Last default", last_or(0.0), [(d1, 10.0)])
    ctx = Context()

    assert ctx.get_at(exact_series, d1) == 10.0
    assert ctx.get_at(exact_series, d2) == 0.0
    assert ctx.get_at(last_series, d0) == 0.0
    assert ctx.get_at(last_series, d2) == 10.0


def test_last_never_forces_superseded_cells():
    def poison() -> float:
        raise AssertionError("superseded cell was forced")

    series = Series.of(
        "balance",
        last,
        [(date(2026, 1, 1), Thunk(poison)), (date(2026, 2, 1), 110.0)],
    )

    assert Context().get_at(series, date(2026, 2, 15)) == 110.0


def test_accrue_exact_hit_returns_cell_unchanged():
    series = Series.of("revenue", accrue(YF.cmonthly), [(P1, 100.0), (P2, 200.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 100.0
    assert ctx.get_at(series, P2) == 200.0


def test_accrue_weights_overlap_by_yf():
    series = Series.of("revenue", accrue(lambda a, b: (b - a).days), [(Q1, 90.0)])

    # January sits inside the quarter, so 31 / 90 of the cell is accrued.
    assert Context().get_at(series, P1) == 90.0 * 31 / 90


def test_accrue_returns_na_when_query_extends_outside_cells():
    series = Series.of("revenue", accrue(lambda a, b: (b - a).days), [(Q1, 90.0)])
    gapped = Series.of(
        "gapped", accrue(lambda a, b: (b - a).days), [(P1, 100.0), (P3, 30.0)]
    )

    ctx = Context()
    assert isna(ctx.get_at(series, Period(date(2025, 12, 31), P1.end)))
    assert isna(ctx.get_at(series, Period(P3.start, date(2026, 5, 1))))
    assert isna(ctx.get_at(gapped, Q1))


def test_accrue_drop_ignores_time_outside_cells():
    series = Series.of("revenue", accrue_drop(lambda a, b: (b - a).days), [(Q1, 90.0)])
    gapped = Series.of(
        "gapped",
        accrue_drop(lambda a, b: (b - a).days),
        [(P1, 100.0), (P3, 30.0)],
    )

    ctx = Context()
    assert ctx.get_at(series, Period(P3.start, date(2026, 5, 1))) == 90.0 * 31 / 90
    assert ctx.get_at(gapped, Q1) == 130.0
    # Dropping all of the query leaves an empty sum.
    assert ctx.get_at(series, Period(date(2026, 4, 1), date(2026, 5, 1))) == 0.0
    empty = Series.of("empty", accrue_drop(days), [])
    assert ctx.get_at(empty, P1) == 0.0


def test_accrue_sums_across_multiple_cells():
    series = Series.of(
        "revenue",
        accrue(lambda a, b: (b - a).days),
        [(P1, 31.0), (P2, 28.0), (P3, 31.0)],
    )

    ctx = Context()
    assert ctx.get_at(series, Q1) == 90.0
    # Half of January plus all of February.
    mid_jan = date(2026, 1, 16)
    assert ctx.get_at(series, Period(mid_jan, P2.end)) == 31.0 * 16 / 31 + 28.0


def test_accrue_returns_na_on_miss():
    series = Series.of("revenue", accrue(YF.cmonthly), [(P1, 100.0)])
    empty = Series.of("empty", accrue(YF.cmonthly), [])

    assert Context().get_at(series, P3) is Na
    assert Context().get_at(empty, P1) is Na


def test_accrue_propagates_na_cells():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "revenue", accrue(YF.cmonthly), [(P1, 100.0), (P2, Na)]
    )

    ctx = Context()
    assert isna(ctx.get_at(series, Period(P1.start, P2.end)))
    # An exact hit passes the cell through, Na included.
    assert ctx.get_at(series, P2) is Na


def test_accrue_drop_propagates_na_cells():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "revenue", accrue_drop(days), [(P1, 100.0), (P2, Na)]
    )

    ctx = Context()
    assert ctx.get_at(series, P1) == 100.0
    assert isna(ctx.get_at(series, Period(P1.start, P2.end)))
    assert isna(ctx.get_at(series, Period(P2.start, P3.end)))


def test_accrue_never_forces_cells_outside_query():
    def poison() -> float:
        raise AssertionError("cell outside the query was forced")

    series = Series.of(
        "revenue",
        accrue(lambda a, b: (b - a).days),
        [(P1, Thunk(poison)), (P2, 20.0), (P3, Thunk(poison))],
    )

    assert Context().get_at(series, Period(P2.start, date(2026, 2, 15))) == 20.0 * 14 / 28


@pytest.mark.parametrize("query_fn", [accrue(days), avg(days), covered])
def test_strict_queries_force_no_values_when_the_cells_miss_part_of_the_query(
    query_fn: QueryFn[Period, float, Maybe[float]],
):
    def poison() -> float:
        raise AssertionError("a value was forced for a query that is Na")

    trailing = Series.of("trailing", query_fn, [(P1, Thunk(poison)), (P2, Thunk(poison))])
    gapped = Series.of("gapped", query_fn, [(P1, Thunk(poison)), (P3, Thunk(poison))])

    ctx = Context()
    assert isna(ctx.get_at(trailing, Q1))
    assert isna(ctx.get_at(gapped, Q1))


def test_accrue_does_not_force_tail_when_cell_ends_with_query():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P3:
            raise AssertionError("tail after the query was forced")
        return period, 10.0, P2 if period == P1 else P3

    series = Series.unfold(
        "revenue",
        accrue(YF.cmonthly),
        seed=P1,
        step=step,
    )

    assert Context().get_at(series, Period(P1.start, P2.end)) == 20.0


def test_accrue_does_not_force_tail_when_cell_extends_past_query():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P3:
            raise AssertionError("tail after the query was forced")
        return period, 10.0, P2 if period == P1 else P3

    series = Series.unfold(
        "revenue",
        accrue(lambda start, end: (end - start).days),
        seed=P1,
        step=step,
    )

    query_end = date(2026, 2, 15)
    assert Context().get_at(series, Period(P1.start, query_end)) == 15.0


def test_avg_weights_overlapping_values_by_day_count():
    series = Series.of(
        "rate",
        avg(lambda start, end: (end - start).days),
        [(P1, 10.0), (P2, 20.0)],
    )

    assert Context().get_at(series, Period(P1.start, P2.end)) == (10.0 * 31 + 20.0 * 28) / 59


def test_avg_returns_na_on_miss_or_na_cell():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "rate", avg(YF.cmonthly), [(P1, 10.0), (P2, Na)]
    )

    ctx = Context()
    assert ctx.get_at(series, P3) is Na
    assert ctx.get_at(series, Period(P1.start, P2.end)) is Na


def test_avg_returns_na_when_query_extends_outside_cells():
    series = Series.of("rate", avg(days), [(P1, 10.0), (P2, 20.0)])
    gapped = Series.of("gapped", avg(days), [(P1, 10.0), (P3, 30.0)])

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert isna(ctx.get_at(series, Period(P2.start, date(2026, 3, 15))))
    assert isna(ctx.get_at(gapped, Q1))


def test_avg_drop_ignores_time_outside_cells():
    series = Series.of("rate", avg_drop(days), [(P1, 10.0)])

    # February is outside the cell, so the average is January's level.
    assert Context().get_at(series, Period(P1.start, P2.end)) == 10.0
    assert isna(Context().get_at(series, P3))
    gapped = Series.of("gapped", avg_drop(days), [(P1, 10.0), (P3, 30.0)])
    # February sits between the cells and is left out of the weights.
    assert Context().get_at(gapped, Q1) == (10.0 * 31 + 30.0 * 31) / 62


def test_avg_does_not_force_tail_when_cell_ends_with_query():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P3:
            raise AssertionError("tail after the query was forced")
        return period, 10.0, P2 if period == P1 else P3

    series = Series.unfold("rate", avg(YF.cmonthly), seed=P1, step=step)

    assert Context().get_at(series, Period(P1.start, P2.end)) == 10.0


def test_avg_fill_plugs_misses_but_propagates_na_cells():
    series: Series[Period, Maybe[float], Maybe[float]] = Series.of(
        "rate", avg_fill(days, 7.0), [(P1, 10.0), (P2, Na)]
    )

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert ctx.get_at(series, P2) is Na
    assert ctx.get_at(series, P3) == 7.0
    assert ctx.get_at(series, Period(P1.start, P2.end)) is Na


def test_avg_fill_fills_uncovered_portions_before_averaging():
    series = Series.of("rate", avg_fill(days, 0.0), [(P1, 10.0), (P3, 30.0)])

    ctx = Context()
    assert ctx.get_at(series, Q1) == (10.0 * 31 + 0.0 * 28 + 30.0 * 31) / 90
    feb_only = Series.of("feb", avg_fill(days, 0.0), [(P2, 20.0)])
    assert Context().get_at(feb_only, Period(P1.start, P2.end)) == (0.0 * 31 + 20.0 * 28) / 59
    jan_only = Series.of("jan", avg_fill(days, 0.0), [(P1, 10.0)])
    assert Context().get_at(jan_only, Period(P1.start, P2.end)) == (10.0 * 31 + 0.0 * 28) / 59
    # Gaps on both sides of the only cell are filled.
    index = Series.of("index", avg_fill(days, 1.0), [(P2, 20.0)])
    assert Context().get_at(index, Q1) == (1.0 * 31 + 20.0 * 28 + 1.0 * 31) / 90


def test_avg_weights_by_actual_days_when_yf_measures_the_query_as_zero():
    # YF.thirty360 measures Jan 30 - Jan 31 as zero, but the query is covered.
    zero_q = Period(date(2026, 1, 30), date(2026, 1, 31))
    series = Series.of("rate", avg(YF.thirty360), [(P1, 10.0)])
    dropped = Series.of("rate", avg_drop(YF.thirty360), [(P1, 10.0)])
    filled_series = Series.of("rate", avg_fill(YF.thirty360, 99.0), [(P1, 10.0)])

    ctx = Context()
    assert ctx.get_at(series, zero_q) == 10.0
    assert ctx.get_at(dropped, zero_q) == 10.0
    assert ctx.get_at(filled_series, zero_q) == 10.0


def test_avg_fill_weights_segments_by_actual_days_when_yf_is_degenerate():
    # When yf measures every segment as zero, actual days decide the weights:
    # 31 days of 10.0 and a 28-day gap of 0.0.
    def zero_yf(a: date, b: date) -> float:
        return 0.0

    series = Series.of("rate", avg_fill(zero_yf, 0.0), [(P1, 10.0)])

    assert Context().get_at(series, Period(P1.start, P2.end)) == (10.0 * 31) / 59


def test_accrue_prorates_zero_yf_cells_by_actual_days():
    # A zero-measure cell strictly inside the query must not divide by zero.
    cell = Period(date(2026, 1, 30), date(2026, 1, 31))
    series = Series.of(
        "revenue",
        accrue(YF.thirty360),
        [(Period(P1.start, cell.start), 29.0), (cell, 100.0)],
    )

    assert Context().get_at(series, Period(P1.start, cell.end)) == 29.0 + 100.0

    half = Series.of("revenue", accrue(YF.thirty360), [(cell, 100.0)])
    # Whole-cell overlap accrues the full value even though yf(cell) == 0.
    assert Context().get_at(half, cell) == 100.0


def test_avg_fill_matches_avg_when_the_query_is_fully_covered():
    pairs = [(P1, 10.0), (P2, 20.0)]
    spanned = Period(P1.start, P2.end)
    filled = Series.of("filled", avg_fill(days, 0.0), pairs)
    raw = Series.of("raw", avg(days), pairs)

    ctx = Context()
    assert ctx.get_at(filled, spanned) == ctx.get_at(raw, spanned)


def test_avg_fill_never_forces_cells_outside_query():
    def poison() -> float:
        raise AssertionError("cell outside the query was forced")

    series = Series.of(
        "rate",
        avg_fill(days, 0.0),
        [(P1, Thunk(poison)), (P2, 20.0), (P3, Thunk(poison))],
    )

    assert Context().get_at(series, Period(P2.start, date(2026, 2, 15))) == 20.0
    gapped = Series.of("gapped", avg_fill(days, 0.0), [(P1, 10.0), (P3, Thunk(poison))])
    assert Context().get_at(gapped, Period(P1.start, P2.end)) == (10.0 * 31 + 0.0 * 28) / 59


def test_avg_fill_does_not_force_tail_when_cell_ends_with_query():
    def step(period: Period) -> tuple[Period, float, Period]:
        if period == P3:
            raise AssertionError("tail after the query was forced")
        return period, 10.0, P2 if period == P1 else P3

    series = Series.unfold("rate", avg_fill(YF.cmonthly, 0.0), seed=P1, step=step)

    assert Context().get_at(series, Period(P1.start, P2.end)) == 10.0


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

    def step(day: date) -> tuple[Period, float, date]:
        month = relativedelta(months=1)
        return Period(day, day + month), 1.0, day + month

    series = Series.unfold(
        "revenue",
        covered,
        seed=START,
        step=step,
    )

    ctx = Context()
    assert ctx.get_at(series, Q1) == 3.0
    assert ctx.get(Fn("probe", lambda: covered(P2, series.cells))) == 1.0
