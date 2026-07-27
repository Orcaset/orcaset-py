# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import operator
from collections.abc import Iterable, Iterator
from datetime import date
from itertools import count, islice

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    MISSING,
    CellReplay,
    Context,
    F,
    LeafSeries,
    Missing,
    MissingError,
    Period,
    Pure,
    Series,
    clip_daily,
    exact,
    fill,
    lift2,
    map2,
    merge,
    only,
    only_or,
    or_else,
    ordered_intersection,
    ordered_union,
    propagate,
    rekey,
    resample,
    strict,
    sum_cells,
    unwrap,
)

MONTHLY = relativedelta(months=1)
QUARTERLY = relativedelta(months=3)
YEARLY = relativedelta(years=1)

QUARTERS = list(islice(Period.seq(date(2025, 12, 31), QUARTERLY), 4))


def quarterly_revenue() -> LeafSeries[Period, float, Period]:
    return LeafSeries.from_pairs(
        zip(QUARTERS, [100.0, 110.0, 120.0, 130.0]),
        clip_daily(),
        sum_cells(0.0),
        label="Revenue",
    )


# Query basics --------------------------------------------------------------


def test_query_exact_key_lookup() -> None:
    series = LeafSeries.from_pairs(
        [(0, 10.0), (1, 20.0), (2, 30.0)], exact(), only(), label="Input"
    )

    ctx = Context()
    assert series.query(1).run(ctx) == 20.0
    assert series.query(2).run(ctx) == 30.0


def test_query_and_select_return_same_node() -> None:
    series = LeafSeries.from_pairs([(0, 1.0)], exact(), only(), label="Input")

    assert series.query(0) is series.query(0)
    assert series.select(0) is series.select(0)
    assert series.keys() is series.keys()
    assert series.query(0).label == "Input[0]"
    assert series.select(0).label == "Input.select[0]"


def test_query_nodes_memoized_by_query_equality() -> None:
    revenue = quarterly_revenue()

    a = revenue.query(Period(date(2026, 3, 1), date(2026, 4, 30)))
    b = revenue.query(Period(date(2026, 3, 1), date(2026, 4, 30)))
    assert a is b

    sa = revenue.select(Period(date(2026, 3, 1), date(2026, 4, 30)))
    sb = revenue.select(Period(date(2026, 3, 1), date(2026, 4, 30)))
    assert sa is sb


def test_query_is_total_and_absent_keys_answer_missing() -> None:
    series = LeafSeries.from_pairs([(0, 1.0), (2, 2.0)], exact(), only(), label="Input")

    ctx = Context()
    assert series.query(1).run(ctx) is MISSING
    assert series.query(99).run(ctx) is MISSING
    assert series.query(2).run(ctx) == 2.0


def test_missing_node_is_shared_across_absent_answers() -> None:
    series = LeafSeries.from_pairs([(0, 1.0)], exact(), only(), label="Input")

    ctx = Context()
    assert series.query(1).run(ctx) is series.query(2).run(ctx) is MISSING


def test_reduce_errors_note_the_query_label() -> None:
    def sel(replay: CellReplay[int, float], q: int) -> tuple[tuple[int, F[float]], ...]:
        return tuple(replay)

    series = LeafSeries.from_pairs([(0, 1.0), (1, 2.0)], sel, only(), label="Input")

    with pytest.raises(ValueError) as excinfo:
        series.query(0).run(Context())

    assert any("reducing Input[0]" in note for note in excinfo.value.__notes__)


def test_context_survives_a_failed_query() -> None:
    def boom() -> float:
        raise RuntimeError("nope")

    series = LeafSeries.from_cells(
        lambda: [(0, F.delay(boom)), (1, Pure(1.0))], exact(), only(), label="Input"
    )

    ctx = Context()
    with pytest.raises(RuntimeError):
        series.query(0).run(ctx)

    assert ctx.frames == []
    assert ctx.values == []
    assert ctx.stack == []
    assert ctx.inflight == set()
    assert series.query(1).run(ctx) == 1.0


def test_only_or_defaults_on_missing_gap_and_past_end() -> None:
    series = LeafSeries.from_pairs([(1, 5.0), (3, 7.0)], exact(), only_or(0.0), label="Input")

    ctx = Context()
    assert series.query(0).run(ctx) == 0.0
    assert series.query(1).run(ctx) == 5.0
    assert series.query(2).run(ctx) == 0.0
    assert series.query(9).run(ctx) == 0.0


# Caching -------------------------------------------------------------------


def test_select_and_reduce_run_once_per_context_per_query() -> None:
    sel_calls = 0
    red_calls = 0
    base_sel = clip_daily()
    base_red = sum_cells(0.0)

    def counting_sel(
        replay: CellReplay[Period, float], q: Period
    ) -> tuple[tuple[Period, F[float]], ...]:
        nonlocal sel_calls
        sel_calls += 1
        return base_sel(replay, q)

    def counting_red(pairs: tuple[tuple[Period, F[float]], ...]) -> F[float | Missing]:
        nonlocal red_calls
        red_calls += 1
        return base_red(pairs)

    revenue = LeafSeries.from_pairs(
        zip(QUARTERS, [100.0, 110.0, 120.0, 130.0]),
        counting_sel,
        counting_red,
        label="Revenue",
    )

    q = Period(date(2025, 12, 31), date(2026, 12, 31))
    ctx = Context()
    assert revenue.query(q).run(ctx) == pytest.approx(460.0)
    assert (sel_calls, red_calls) == (1, 1)

    # Repeats in the same context are pure cache hits, including via an
    # equal-but-distinct query object and the select audit view.
    assert revenue.query(q).run(ctx) == pytest.approx(460.0)
    assert revenue.query(Period(date(2025, 12, 31), date(2026, 12, 31))).run(ctx) == pytest.approx(
        460.0
    )
    assert len(revenue.select(q).run(ctx)) == 4
    assert (sel_calls, red_calls) == (1, 1)

    # A fresh context re-evaluates once.
    assert revenue.query(q).run(Context()) == pytest.approx(460.0)
    assert (sel_calls, red_calls) == (2, 2)


def test_query_recursion_is_linear_and_cached() -> None:
    """counter[n] = counter[n - 1] + 1 via self-query; O(n) evaluations."""
    map_calls = 0

    def cells() -> Iterator[tuple[int, F[int]]]:
        def inc(x: int | Missing) -> int:
            nonlocal map_calls
            map_calls += 1
            return unwrap(x) + 1

        yield 0, Pure(0)
        n = 1
        while True:
            yield n, counter.query(n - 1).map(inc)
            n += 1

    counter = LeafSeries.from_cells(cells, exact(), only(), label="Counter")

    ctx = Context()
    assert counter.query(100).run(ctx) == 100
    assert map_calls == 100

    # Earlier cells were computed along the way; nothing recomputes.
    map_calls = 0
    assert counter.query(50).run(ctx) == 50
    assert map_calls == 0
    assert counter.query(100).run(ctx) == 100
    assert map_calls == 0

    # A fresh context re-runs the factory from scratch.
    map_calls = 0
    assert counter.query(10).run(Context()) == 10
    assert map_calls == 10


def test_generator_state_recursion_is_linear_and_cached() -> None:
    """counter[n] = counter[n - 1] + 1 via generator state; O(n) evaluations."""
    map_calls = 0

    def cells() -> Iterator[tuple[int, F[int]]]:
        def inc(x: int) -> int:
            nonlocal map_calls
            map_calls += 1
            return x + 1

        cell: F[int] = Pure(0)
        n = 0
        while True:
            yield n, cell
            cell = cell.map(inc)
            n += 1

    counter = LeafSeries.from_cells(cells, exact(), only(), label="Counter")

    ctx = Context()
    assert counter.query(100).run(ctx) == 100
    assert map_calls == 100

    map_calls = 0
    assert counter.query(50).run(ctx) == 50
    assert map_calls == 0

    map_calls = 0
    assert counter.query(10).run(Context()) == 10
    assert map_calls == 10


def test_cross_series_shared_cells_compute_once() -> None:
    calls = 0

    def base_cells() -> Iterator[tuple[int, F[float]]]:
        def tick() -> float:
            nonlocal calls
            calls += 1
            return 100.0

        yield 0, F.delay(tick)

    base = LeafSeries.from_cells(base_cells, exact(), only(), label="Base")
    double = base.map(lambda x: x * 2, label="Double")
    triple = base.map(lambda x: x * 3, label="Triple")
    combined = lift2(strict(operator.add), double.query(0), triple.query(0))

    ctx = Context()
    assert combined.run(ctx) == 500.0
    assert calls == 1


# Views ---------------------------------------------------------------------


def test_map_transforms_after_source_query() -> None:
    revenue = quarterly_revenue()
    after_allowance = revenue.map(lambda value: max(value - 150.0, 0.0), label="After allowance")
    first_half = Period(QUARTERS[0].start, QUARTERS[1].end)

    ctx = Context()
    assert after_allowance.query(first_half).run(ctx) == 60.0
    assert [cell.run(ctx) for _, cell in after_allowance.items(ctx)] == [0.0] * 4


def test_map_propagates_missing_and_map_maybe_sees_it() -> None:
    series = LeafSeries.from_pairs([(0, 2.0)], exact(), only(), label="Input")
    doubled = series.map(lambda x: x * 2, label="Doubled")
    defaulted = series.map_maybe(lambda a: or_else(a, -1.0), label="Defaulted")
    filled = series.fill(0.0)

    ctx = Context()
    assert doubled.query(0).run(ctx) == 4.0
    assert doubled.query(1).run(ctx) is MISSING
    assert defaulted.query(1).run(ctx) == -1.0
    assert filled.query(1).run(ctx) == 0.0
    assert filled.query(0).run(ctx) == 2.0


def test_view_shares_the_source_key_node() -> None:
    revenue = quarterly_revenue()
    view = revenue.map(lambda x: x, label="View")

    assert view.keys() is revenue.keys()
    assert list(view.keys().run(Context())) == QUARTERS


def test_view_errors_note_the_query_label() -> None:
    series = LeafSeries.from_pairs([(0, 1.0)], exact(), only(), label="Input")
    view = series.map_maybe(lambda a: unwrap(a), label="Strict view")

    with pytest.raises(MissingError) as excinfo:
        view.query(1).run(Context())

    assert any("mapping Strict view[1]" in note for note in excinfo.value.__notes__)


# Select audit --------------------------------------------------------------


def test_select_audits_clipping_and_reproduces_query_value() -> None:
    revenue = quarterly_revenue()
    window = Period(date(2026, 3, 1), date(2026, 4, 30))

    ctx = Context()
    pairs = revenue.select(window).run(ctx)

    # 30 tail days of Q1 (90 days) + 30 head days of Q2 (91 days), keys clipped.
    assert [key for key, _ in pairs] == [
        Period(date(2026, 3, 1), date(2026, 3, 31)),
        Period(date(2026, 3, 31), date(2026, 4, 30)),
    ]
    values = [cell.run(ctx) for _, cell in pairs]
    assert values == pytest.approx([100.0 * 30 / 90, 110.0 * 30 / 91])
    assert sum(values) == pytest.approx(revenue.query(window).run(ctx))


def test_select_preserves_cell_identity_when_unclipped() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    cells = dict(revenue.stream(ctx))
    [(key, cell)] = revenue.select(QUARTERS[1]).run(ctx)
    assert key == QUARTERS[1]
    assert cell is cells[QUARTERS[1]]


def test_clip_daily_fill_materializes_gaps() -> None:
    q2 = Period(date(2026, 3, 31), date(2026, 6, 30))
    revenue = LeafSeries.from_pairs(
        [(q2, 90.0)], clip_daily(fill=0.0), sum_cells(0.0), label="Revenue"
    )
    window = Period(date(2026, 1, 1), date(2027, 1, 1))

    ctx = Context()
    pairs = revenue.select(window).run(ctx)
    assert [key for key, _ in pairs] == [
        Period(date(2026, 1, 1), date(2026, 3, 31)),
        q2,
        Period(date(2026, 6, 30), date(2027, 1, 1)),
    ]
    assert [cell.run(ctx) for _, cell in pairs] == [0.0, 90.0, 0.0]
    assert revenue.query(window).run(ctx) == pytest.approx(90.0)


# Window queries ------------------------------------------------------------


def test_window_spanning_multiple_periods() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    window = Period(date(2025, 12, 31), date(2026, 12, 31))
    assert revenue.query(window).run(ctx) == pytest.approx(460.0)


def test_window_exactly_one_period() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    assert revenue.query(Period(date(2025, 12, 31), date(2026, 3, 31))).run(ctx) == pytest.approx(
        100.0
    )


def test_window_part_of_one_period() -> None:
    revenue = quarterly_revenue()

    # 30 days of Q1's 90: 100 * 30 / 90
    ctx = Context()
    window = Period(date(2026, 1, 15), date(2026, 2, 14))
    assert revenue.query(window).run(ctx) == pytest.approx(100.0 * 30 / 90)


def test_window_straddling_two_periods() -> None:
    revenue = quarterly_revenue()

    # 30 tail days of Q1 (90 days) + 30 head days of Q2 (91 days)
    expected = 100.0 * 30 / 90 + 110.0 * 30 / 91
    ctx = Context()
    window = Period(date(2026, 3, 1), date(2026, 4, 30))
    assert revenue.query(window).run(ctx) == pytest.approx(expected)


def test_window_touching_no_periods() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    assert revenue.query(Period(date(2020, 1, 1), date(2020, 12, 31))).run(ctx) == 0.0
    assert revenue.query(Period(date(2030, 1, 1), date(2030, 12, 31))).run(ctx) == 0.0


def test_window_past_series_end_sums_covered_part() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    window = Period(date(2026, 9, 30), date(2027, 12, 31))
    assert revenue.query(window).run(ctx) == pytest.approx(130.0)


def test_window_terminates_on_infinite_series() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        for period in Period.seq(date(2025, 12, 31), QUARTERLY):
            yield period, Pure(100.0)

    revenue = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Revenue")

    ctx = Context()
    window = Period(date(2026, 3, 31), date(2026, 9, 30))
    assert revenue.query(window).run(ctx) == pytest.approx(200.0)


# Recursion -----------------------------------------------------------------


def test_calendrical_year_ago_self_reference() -> None:
    """Historicals extended by revenue[q] = revenue[q - 1 year] * 1.1 via window query."""
    historicals = [100.0, 110.0, 120.0, 130.0]

    def cells() -> Iterator[tuple[Period, F[float]]]:
        quarters = iter(Period.seq(date(2025, 12, 31), QUARTERLY))
        for value, period in zip(historicals, quarters):
            yield period, Pure(value)
        for period in quarters:
            prior = revenue.query(period.shift(relativedelta(years=-1)))
            yield period, prior.map(lambda x: unwrap(x) * 1.1)

    revenue = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Revenue")
    quarters = list(islice(Period.seq(date(2025, 12, 31), QUARTERLY), 12))

    ctx = Context()
    assert revenue.query(quarters[4]).run(ctx) == pytest.approx(110.0)  # 100 * 1.1
    assert revenue.query(quarters[7]).run(ctx) == pytest.approx(143.0)  # 130 * 1.1
    assert revenue.query(quarters[11]).run(ctx) == pytest.approx(157.3)  # 130 * 1.1^2

    # Lookback goes through memoized query nodes: one node per (series, query).
    assert revenue.query(quarters[4]) is revenue.query(quarters[4])


def test_recursion_states_its_base_case_through_missing() -> None:
    """A self-querying cell resolves MISSING into a seed."""

    def cells() -> Iterator[tuple[int, F[float]]]:
        for n in count():
            prior = series.query(n - 1)
            yield n, prior.map(lambda a: 1.0 if isinstance(a, Missing) else a * 2)

    series = LeafSeries.from_cells(cells, exact(), only(), label="Doubling")

    ctx = Context()
    assert series.query(0).run(ctx) == 1.0
    assert series.query(3).run(ctx) == 8.0


def test_positional_year_ago_with_deque() -> None:
    """Same model with a positional 4-quarter lag carried in generator state."""
    from collections import deque

    historicals = [100.0, 110.0, 120.0, 130.0]
    quarters = list(islice(Period.seq(date(2025, 12, 31), QUARTERLY), 12))

    def cells() -> Iterator[tuple[Period, F[float]]]:
        window: deque[F[float]] = deque(maxlen=4)
        values = iter(historicals)
        for period in quarters:
            value = next(values, None)
            cell: F[float] = Pure(value) if value is not None else window[0].map(lambda x: x * 1.1)
            window.append(cell)
            yield period, cell

    revenue = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Revenue")

    ctx = Context()
    assert revenue.query(quarters[4]).run(ctx) == pytest.approx(110.0)
    assert revenue.query(quarters[11]).run(ctx) == pytest.approx(157.3)


def test_rekeying_growth_series_from_monthly_to_quarterly_stays_correct() -> None:
    """Window-query recursion survives re-keying the forecast calendar.

    Twelve monthly seed cells total 120. Forecast cells are defined as the
    year-ago window times 1.1 — on a monthly calendar in one series and a
    quarterly calendar in the other. Window queries aggregate whatever cells
    exist, so both give the same annual totals; positional (unfold-carried)
    references would silently compound the monthly rate quarterly.
    """
    start = date(2025, 12, 31)

    def growth_series(freq: relativedelta, label: str) -> LeafSeries[Period, float, Period]:
        def cells() -> Iterator[tuple[Period, F[float]]]:
            months = iter(Period.seq(start, MONTHLY))
            for period, value in zip(months, [10.0] * 12):
                yield period, Pure(value)
            for period in Period.seq(start + YEARLY, freq):
                prior = series.query(period.shift(-YEARLY))
                yield period, prior.map(lambda x: unwrap(x) * 1.1)

        series = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label=label)
        return series

    monthly = growth_series(MONTHLY, "Monthly")
    quarterly = growth_series(QUARTERLY, "Quarterly")

    year2 = Period(start + YEARLY, start + relativedelta(years=2))
    year3 = Period(start + relativedelta(years=2), start + relativedelta(years=3))

    ctx = Context()
    assert monthly.query(year2).run(ctx) == pytest.approx(132.0)
    assert quarterly.query(year2).run(ctx) == pytest.approx(132.0)
    assert monthly.query(year3).run(ctx) == pytest.approx(145.2)
    assert quarterly.query(year3).run(ctx) == pytest.approx(145.2)


def test_generator_state_growth_series_with_window_default() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        cell: F[float] = Pure(100.0)
        for period in Period.seq(date(2025, 12, 31), YEARLY):
            yield period, cell
            cell = cell.map(lambda value: value * 1.1)

    revenue = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Revenue")
    periods = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 3))

    ctx = Context()
    assert revenue.query(periods[2]).run(ctx) == pytest.approx(121.0)
    # A window before the series starts finds nothing and reduces to 0.0.
    early = Period(date(2020, 1, 1), date(2021, 1, 1))
    assert revenue.query(early).run(ctx) == 0.0


def test_self_referential_query_cycle_raises() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        for period in Period.seq(date(2025, 12, 31), YEARLY):
            yield period, series.query(period).map(lambda x: unwrap(x))

    series = LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Ouroboros")

    ctx = Context()
    with pytest.raises(RuntimeError, match="cycle detected"):
        series.query(Period(date(2025, 12, 31), date(2026, 12, 31))).run(ctx)

    assert ctx.frames == []
    assert ctx.values == []
    assert ctx.stack == []
    assert ctx.inflight == set()


# Combining views -----------------------------------------------------------


def test_map2_combines_answers_over_the_union_grid() -> None:
    a = LeafSeries.from_pairs([(1, 1.0), (2, 2.0)], exact(), only(), label="A")
    b = LeafSeries.from_pairs([(2, 20.0), (3, 30.0)], exact(), only(), label="B")
    total = map2(a, b, fill(0.0, operator.add), label="Total")

    ctx = Context()
    assert list(total.keys().run(ctx)) == [1, 2, 3]
    assert [(key, cell.run(ctx)) for key, cell in total.items(ctx)] == [
        (1, 1.0),
        (2, 22.0),
        (3, 30.0),
    ]


def test_combine_policies_differ_on_partial_coverage() -> None:
    a = LeafSeries.from_pairs([(1, 1.0)], exact(), only(), label="A")
    b = LeafSeries.from_pairs([(2, 2.0)], exact(), only(), label="B")

    ctx = Context()
    assert map2(a, b, fill(0.0, operator.add), label="Filled").query(1).run(ctx) == 1.0
    assert map2(a, b, propagate(operator.add), label="Propagated").query(1).run(ctx) is MISSING
    with pytest.raises(MissingError):
        map2(a, b, strict(operator.add), label="Strict").query(1).run(ctx)


def test_merge_folds_as_a_balanced_tree() -> None:
    sources = [
        LeafSeries.from_pairs([(i, float(i))], exact(), only(), label=f"S{i}") for i in range(8)
    ]
    total = merge(sources, fill(0.0, operator.add), label="Total")

    ctx = Context()
    assert total.query(5).run(ctx) == 5.0
    assert list(total.keys().run(ctx)) == list(range(8))
    assert total.label == "Total"

    # Balanced: 8 leaves fold to depth 3, not 7.
    def depth(node: Series[int, float, int]) -> int:
        children = getattr(node, "_a", None), getattr(node, "_b", None)
        if children[0] is None:
            return 0
        return 1 + max(depth(child) for child in children if child is not None)

    assert depth(total) == 3


def test_merge_of_one_returns_the_source() -> None:
    only_source = LeafSeries.from_pairs([(1, 1.0)], exact(), only(), label="A")
    assert merge([only_source], fill(0.0, operator.add), label="Total") is only_source


def test_merge_requires_at_least_one_series() -> None:
    empty: list[Series[int, float, int]] = []
    with pytest.raises(ValueError, match="at least one"):
        merge(empty, fill(0.0, operator.add), label="Total")


def test_merged_cohorts_total_over_disjoint_spans() -> None:
    """Cohorts covering different spans sum where only one has coverage."""
    timeline = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 4))
    cohort1 = LeafSeries.from_cells(
        lambda: [(timeline[1], Pure(50.0)), (timeline[2], Pure(50.0))],
        clip_daily(),
        sum_cells(0.0),
        label="Cohort 1",
    )
    cohort2 = LeafSeries.from_cells(
        lambda: [(timeline[2], Pure(100.0)), (timeline[3], Pure(100.0))],
        clip_daily(),
        sum_cells(0.0),
        label="Cohort 2",
    )
    total = merge([cohort1, cohort2], fill(0.0, operator.add), label="Total")

    ctx = Context()
    assert [total.query(period).run(ctx) for period in timeline] == [0.0, 50.0, 150.0, 100.0]


# Keys ----------------------------------------------------------------------


def test_leaf_keys_replay_within_a_context() -> None:
    pulls = 0

    def cells() -> Iterator[tuple[int, F[int]]]:
        nonlocal pulls
        for i in range(3):
            pulls += 1
            yield i, Pure(i * 10)

    series = LeafSeries.from_cells(cells, exact(), only(), label="Input")

    ctx = Context()
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3


def test_ordered_union_is_lazy_and_dedupes() -> None:
    assert list(islice(ordered_union(count(0, 2), count(0, 3)), 7)) == [0, 2, 3, 4, 6, 8, 9]
    assert list(ordered_union([1, 2], [2, 3])) == [1, 2, 3]
    assert list(ordered_union([], [1, 2])) == [1, 2]
    assert list(ordered_union([1, 2], [])) == [1, 2]


def test_ordered_intersection() -> None:
    assert list(ordered_intersection([1, 2, 3], [2, 3, 4])) == [2, 3]
    assert list(ordered_intersection([1], [2])) == []


def test_map2_can_intersect_keys() -> None:
    a = LeafSeries.from_pairs([(1, 1.0), (2, 2.0)], exact(), only(), label="A")
    b = LeafSeries.from_pairs([(2, 20.0), (3, 30.0)], exact(), only(), label="B")
    inner = map2(a, b, strict(operator.add), merge_keys=ordered_intersection, label="Inner")

    ctx = Context()
    assert list(inner.keys().run(ctx)) == [2]
    assert inner.query(2).run(ctx) == 22.0


# Resampling ----------------------------------------------------------------


def monthly_revenue() -> LeafSeries[Period, float, Period]:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        for i, period in enumerate(islice(Period.seq(date(2025, 12, 31), MONTHLY), 24)):
            yield period, Pure(10.0 + i)

    return LeafSeries.from_cells(cells, clip_daily(), sum_cells(0.0), label="Monthly")


def test_resample_tabulates_answers_on_a_new_grid() -> None:
    monthly = monthly_revenue()
    years = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 2))
    annual = resample(
        monthly,
        lambda: years,
        lambda _, answer: or_else(answer, 0.0),
        clip_daily(),
        sum_cells(0.0),
        label="Annual",
    )

    ctx = Context()
    assert annual.query(years[0]).run(ctx) == pytest.approx(sum(10.0 + i for i in range(12)))
    assert annual.query(years[1]).run(ctx) == pytest.approx(sum(10.0 + i for i in range(12, 24)))
    assert list(annual.keys().run(ctx)) == years


def test_resampled_cells_are_the_source_query_nodes() -> None:
    monthly = monthly_revenue()
    years = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 1))
    annual = resample(
        monthly,
        lambda: years,
        lambda _, answer: answer,
        exact(),
        only(),
        label="Annual",
    )

    ctx = Context()
    assert annual.query(years[0]).run(ctx) == pytest.approx(sum(10.0 + i for i in range(12)))
    # The resampled cell's value came through the source's memoized query node.
    assert monthly.query(years[0]).id in ctx.cache


def test_resample_resolve_states_the_absence_policy() -> None:
    source = LeafSeries.from_pairs([(1, 1.0)], exact(), only(), label="Source")

    filled = resample(
        source, lambda: [1, 2], lambda _, a: or_else(a, 0.0), exact(), only(), label="Filled"
    )
    kept = resample(source, lambda: [1, 2], lambda _, a: a, exact(), only(), label="Kept")
    required = resample(
        source, lambda: [1, 2], lambda _, a: unwrap(a), exact(), only(), label="Required"
    )

    ctx = Context()
    assert filled.query(2).run(ctx) == 0.0
    assert kept.query(2).run(ctx) is MISSING
    with pytest.raises(MissingError):
        required.query(2).run(ctx)


def test_rekey_derives_the_grid_from_source_keys() -> None:
    monthly = monthly_revenue()

    def years(keys: Iterable[Period]) -> Iterator[Period]:
        """Bucket each month into the 12-31-anchored year containing its start."""
        seen: set[Period] = set()
        for key in keys:
            anchor = (
                key.start.year
                if (key.start.month, key.start.day) >= (12, 31)
                else key.start.year - 1
            )
            year = Period(date(anchor, 12, 31), date(anchor + 1, 12, 31))
            if year not in seen:
                seen.add(year)
                yield year

    annual = rekey(
        monthly,
        years,
        lambda _, answer: or_else(answer, 0.0),
        clip_daily(),
        sum_cells(0.0),
        label="Annual",
    )

    ctx = Context()
    keys = list(annual.keys().run(ctx))
    assert keys == [
        Period(date(2025, 12, 31), date(2026, 12, 31)),
        Period(date(2026, 12, 31), date(2027, 12, 31)),
    ]
    assert annual.query(keys[0]).run(ctx) == pytest.approx(sum(10.0 + i for i in range(12)))


def test_resample_after_merge_restores_cells_and_evidence() -> None:
    timeline = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 3))
    a = LeafSeries.from_cells(
        lambda: [(timeline[0], Pure(10.0)), (timeline[1], Pure(20.0))],
        clip_daily(),
        sum_cells(0.0),
        label="A",
    )
    b = LeafSeries.from_cells(
        lambda: [(timeline[1], Pure(5.0))], clip_daily(), sum_cells(0.0), label="B"
    )
    total = merge([a, b], fill(0.0, operator.add), label="Total")
    materialized = resample(
        total,
        lambda: timeline,
        lambda _, answer: or_else(answer, 0.0),
        clip_daily(),
        sum_cells(0.0),
        label="Total (annual)",
    )

    ctx = Context()
    assert [key for key, _ in materialized.select(timeline[1]).run(ctx)] == [timeline[1]]
    assert materialized.query(timeline[1]).run(ctx) == pytest.approx(25.0)
    assert [cell.run(ctx) for _, cell in materialized.stream(ctx)] == [10.0, 25.0, 0.0]


# Convention units ----------------------------------------------------------


def test_reducers_preserve_single_cell_identity() -> None:
    cell: F[float] = Pure(1.0)
    assert only()(((0, cell),)) is cell
    assert only_or(9.0)(((0, cell),)) is cell
    assert sum_cells()(((0, cell),)) is cell


def test_reducers_are_total_on_the_empty_selection() -> None:
    ctx = Context()
    assert only()(()).run(ctx) is MISSING
    assert sum_cells()(()).run(ctx) is MISSING
    assert sum_cells(0.0)(()).run(ctx) == 0.0
    assert only_or(3.0)(()).run(ctx) == 3.0


def test_only_rejects_ambiguous_selections() -> None:
    cell: F[float] = Pure(1.0)
    with pytest.raises(ValueError):
        only()(((0, cell), (1, cell)))
    with pytest.raises(ValueError):
        only_or(0.0)(((0, cell), (1, cell)))


def test_sum_cells_sums() -> None:
    ctx = Context()
    pairs = ((0, Pure(1.0)), (1, Pure(2.0)), (2, Pure(3.5)))
    assert sum_cells()(pairs).run(ctx) == pytest.approx(6.5)


def test_maybe_helpers() -> None:
    assert unwrap(1.0) == 1.0
    with pytest.raises(MissingError):
        unwrap(MISSING)
    assert or_else(MISSING, 2.0) == 2.0
    assert or_else(1.0, 2.0) == 1.0
    assert repr(MISSING) == "MISSING"


# Stream discipline ---------------------------------------------------------


def test_cell_replay_rejects_non_increasing_keys() -> None:
    replay = CellReplay([(1, Pure(1)), (0, Pure(0))])
    it = iter(replay)
    assert next(it)[0] == 1
    with pytest.raises(ValueError, match="strictly increasing"):
        next(it)


def test_cell_replay_rejects_duplicate_keys() -> None:
    replay = CellReplay([(1, Pure(1)), (1, Pure(2))])
    it = iter(replay)
    next(it)
    with pytest.raises(ValueError, match="strictly increasing"):
        next(it)


def test_cell_replay_rejects_incomparable_period_keys() -> None:
    a = Period(date(2026, 1, 1), date(2026, 4, 1))
    b = Period(date(2026, 1, 1), date(2026, 7, 1))
    replay = CellReplay([(a, Pure(1.0)), (b, Pure(2.0))])
    it = iter(replay)
    next(it)
    with pytest.raises(ValueError, match="comparable"):
        next(it)


def test_stream_materializes_once_per_context() -> None:
    revenue = quarterly_revenue()

    ctx = Context()
    assert revenue.stream(ctx) is revenue.stream(ctx)
    assert revenue.stream(Context()) is not revenue.stream(ctx)
