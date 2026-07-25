# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from itertools import islice

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    F,
    Period,
    Pure,
    ReplayIter,
    Series,
    clip_daily,
    exact,
    flow,
    keyed,
    only,
    only_or,
    sum_cells,
)

MONTHLY = relativedelta(months=1)
QUARTERLY = relativedelta(months=3)
YEARLY = relativedelta(years=1)

QUARTERS = list(islice(Period.seq(date(2025, 12, 31), QUARTERLY), 4))


def quarterly_revenue() -> Series[Period, float]:
    return Series.from_pairs(
        zip(QUARTERS, [100.0, 110.0, 120.0, 130.0]),
        clip_daily(),
        sum_cells(0.0),
        label="Revenue",
    )


# Query basics --------------------------------------------------------------


def test_query_exact_key_lookup() -> None:
    series = Series.from_pairs([(0, 10.0), (1, 20.0), (2, 30.0)], exact(), only(), label="Input")

    ctx = Context()
    assert series.query(1).run(ctx) == 20.0
    assert series.query(2).run(ctx) == 30.0


def test_query_and_select_return_same_node() -> None:
    series = Series.from_pairs([(0, 1.0)], exact(), only(), label="Input")

    assert series.query(0) is series.query(0)
    assert series.select(0) is series.select(0)
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


def test_query_missing_key_raises_and_context_survives() -> None:
    series = Series.from_pairs([(0, 1.0), (2, 2.0)], exact(), only(), label="Input")

    ctx = Context()
    with pytest.raises(KeyError):
        series.query(1).run(ctx)

    assert ctx.frames == []
    assert ctx.values == []
    assert ctx.stack == []
    assert ctx.inflight == set()
    assert series.query(2).run(ctx) == 2.0


def test_query_errors_note_the_query_label() -> None:
    series = Series.from_pairs([(0, 1.0)], exact(), only(), label="Input")

    with pytest.raises(KeyError) as excinfo:
        series.query(7).run(Context())

    assert any("Input[7]" in note for note in excinfo.value.__notes__)


def test_only_or_defaults_on_missing_gap_and_past_end() -> None:
    series = Series.from_pairs([(1, 5.0), (3, 7.0)], exact(), only_or(0.0), label="Input")

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
        replay: ReplayIter[Period, float], q: Period
    ) -> tuple[tuple[Period, F[float]], ...]:
        nonlocal sel_calls
        sel_calls += 1
        return base_sel(replay, q)

    def counting_red(pairs: tuple[tuple[Period, F[float]], ...]) -> F[float]:
        nonlocal red_calls
        red_calls += 1
        return base_red(pairs)

    revenue = Series.from_pairs(
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
        def inc(x: int) -> int:
            nonlocal map_calls
            map_calls += 1
            return x + 1

        yield 0, Pure(0)
        n = 1
        while True:
            yield n, counter.query(n - 1).map(inc)
            n += 1

    counter = keyed(cells, label="Counter")

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

    counter = keyed(cells, label="Counter")

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

    base = keyed(base_cells, label="Base")
    double = base.map(lambda x: x * 2, label="Double")
    triple = base.map(lambda x: x * 3, label="Triple")
    combined = Series.map2(double, triple, lambda x, y: x + y, label="Combined")

    ctx = Context()
    assert combined.query(0).run(ctx) == 500.0
    assert calls == 1


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
    cells = dict(revenue.items(ctx))
    [(key, cell)] = revenue.select(QUARTERS[1]).run(ctx)
    assert key == QUARTERS[1]
    assert cell is cells[QUARTERS[1]]


def test_clip_daily_fill_materializes_gaps() -> None:
    q2 = Period(date(2026, 3, 31), date(2026, 6, 30))
    revenue = Series.from_pairs([(q2, 90.0)], clip_daily(fill=0.0), sum_cells(0.0), label="Revenue")
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

    revenue = flow(cells, label="Revenue")

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
            yield period, prior.map(lambda x: x * 1.1)

    revenue = flow(cells, label="Revenue")
    quarters = list(islice(Period.seq(date(2025, 12, 31), QUARTERLY), 12))

    ctx = Context()
    assert revenue.query(quarters[4]).run(ctx) == pytest.approx(110.0)  # 100 * 1.1
    assert revenue.query(quarters[7]).run(ctx) == pytest.approx(143.0)  # 130 * 1.1
    assert revenue.query(quarters[11]).run(ctx) == pytest.approx(157.3)  # 130 * 1.1^2

    # Lookback goes through memoized query nodes: one node per (series, query).
    assert revenue.query(quarters[4]) is revenue.query(quarters[4])


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

    revenue = flow(cells, label="Revenue")

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

    def growth_series(freq: relativedelta, label: str) -> Series[Period, float]:
        def cells() -> Iterator[tuple[Period, F[float]]]:
            months = iter(Period.seq(start, MONTHLY))
            for period, value in zip(months, [10.0] * 12):
                yield period, Pure(value)
            for period in Period.seq(start + YEARLY, freq):
                prior = series.query(period.shift(-YEARLY))
                yield period, prior.map(lambda x: x * 1.1)

        series = flow(cells, label=label)
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

    revenue = flow(cells, label="Revenue")
    periods = list(islice(Period.seq(date(2025, 12, 31), YEARLY), 3))

    ctx = Context()
    assert revenue.query(periods[2]).run(ctx) == pytest.approx(121.0)
    # A window before the series starts finds nothing and reduces to 0.0.
    early = Period(date(2020, 1, 1), date(2021, 1, 1))
    assert revenue.query(early).run(ctx) == 0.0


def test_self_referential_query_cycle_raises() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        for period in Period.seq(date(2025, 12, 31), YEARLY):
            yield period, series.query(period).map(lambda x: x)

    series = flow(cells, label="Ouroboros")

    ctx = Context()
    with pytest.raises(RuntimeError, match="cycle detected"):
        series.query(Period(date(2025, 12, 31), date(2026, 12, 31))).run(ctx)

    assert ctx.frames == []
    assert ctx.values == []
    assert ctx.stack == []
    assert ctx.inflight == set()


# Combinators ---------------------------------------------------------------


def test_map2_misaligned_keys_raise() -> None:
    a = Series.from_pairs([(0, 1.0)], exact(), only(), label="A")
    b = Series.from_pairs([(1, 2.0)], exact(), only(), label="B")

    with pytest.raises(ValueError, match="misaligned keys"):
        Series.map2(a, b, lambda x, y: x + y, label="Sum").query(0).run(Context())


def test_merge_outer_combines_equal_keys() -> None:
    a = Series.from_pairs([(1, 1.0), (2, 2.0)], exact(), only(), label="A")
    b = Series.from_pairs([(2, 20.0), (3, 30.0)], exact(), only(), label="B")
    merged = Series.merge([a, b], lambda x, y: x + y, label="Merged")

    ctx = Context()
    assert [(key, cell.run(ctx)) for key, cell in merged.items(ctx)] == [
        (1, 1.0),
        (2, 22.0),
        (3, 30.0),
    ]
    # The merged series inherits the first series' conventions.
    assert merged.query(2).run(ctx) == 22.0


def test_items_replays_within_context() -> None:
    pulls = 0

    def cells() -> Iterator[tuple[int, F[int]]]:
        nonlocal pulls
        for i in range(3):
            pulls += 1
            yield i, Pure(i * 10)

    series = keyed(cells, label="Input")

    ctx = Context()
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3


# Convention units ----------------------------------------------------------


def test_reducers_preserve_single_cell_identity() -> None:
    cell: F[float] = Pure(1.0)
    assert only()(((0, cell),)) is cell
    assert only_or(9.0)(((0, cell),)) is cell
    assert sum_cells()(((0, cell),)) is cell


def test_only_rejects_empty_and_ambiguous() -> None:
    cell: F[float] = Pure(1.0)
    with pytest.raises(KeyError):
        only()(())
    with pytest.raises(ValueError):
        only()(((0, cell), (1, cell)))
    with pytest.raises(ValueError):
        only_or(0.0)(((0, cell), (1, cell)))


def test_sum_cells_sums_and_defaults_when_empty() -> None:
    ctx = Context()
    assert sum_cells(fill=0.0)(()).run(ctx) == 0.0
    pairs = ((0, Pure(1.0)), (1, Pure(2.0)), (2, Pure(3.5)))
    assert sum_cells()(pairs).run(ctx) == pytest.approx(6.5)


def test_replay_iter_rejects_non_increasing_keys() -> None:
    replay = ReplayIter([(1, Pure(1)), (0, Pure(0))])
    it = iter(replay)
    assert next(it)[0] == 1
    with pytest.raises(ValueError, match="strictly increasing"):
        next(it)


def test_replay_iter_rejects_duplicate_keys() -> None:
    replay = ReplayIter([(1, Pure(1)), (1, Pure(2))])
    it = iter(replay)
    next(it)
    with pytest.raises(ValueError, match="strictly increasing"):
        next(it)


def test_replay_iter_rejects_incomparable_period_keys() -> None:
    a = Period(date(2026, 1, 1), date(2026, 4, 1))
    b = Period(date(2026, 1, 1), date(2026, 7, 1))
    replay = ReplayIter([(a, Pure(1.0)), (b, Pure(2.0))])
    it = iter(replay)
    next(it)
    with pytest.raises(ValueError, match="comparable"):
        next(it)
