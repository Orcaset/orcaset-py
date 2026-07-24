# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from itertools import islice

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import Context, F, Period, Pure, Series


def test_at_basic_lookup() -> None:
    series = Series.from_pairs([(0, 10.0), (1, 20.0), (2, 30.0)], label="Input")

    ctx = Context()
    assert series.at(1).run(ctx) == 20.0
    assert series.at(2).run(ctx) == 30.0


def test_at_returns_same_node() -> None:
    series = Series.from_pairs([(0, 1.0)], label="Input")

    assert series.at(0) is series.at(0)
    assert series.at(0).label == "Input@0"


def test_at_missing_key_raises_and_context_survives() -> None:
    series = Series.from_pairs([(0, 1.0), (2, 2.0)], label="Input")

    ctx = Context()
    with pytest.raises(KeyError):
        series.at(1).run(ctx)

    assert ctx.frames == []
    assert ctx.values == []
    assert ctx.stack == []
    assert ctx.inflight == set()
    assert series.at(2).run(ctx) == 2.0


def test_get_defaults_on_missing_gap_and_past_end() -> None:
    series = Series.from_pairs([(1, 5.0), (3, 7.0)], label="Input")

    ctx = Context()
    assert series.get(0, 0.0).run(ctx) == 0.0
    assert series.get(1, 0.0).run(ctx) == 5.0
    assert series.get(2, 0.0).run(ctx) == 0.0
    assert series.get(9, 0.0).run(ctx) == 0.0


def test_unfold_lookback_is_linear_and_cached() -> None:
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

    counter = Series.from_cells(cells, label="Counter")

    ctx = Context()
    assert counter.at(100).run(ctx) == 100
    assert map_calls == 100

    # Earlier cells were computed along the way; nothing recomputes.
    map_calls = 0
    assert counter.at(50).run(ctx) == 50
    assert map_calls == 0
    assert counter.at(100).run(ctx) == 100
    assert map_calls == 0

    # A fresh context re-runs the factory from scratch.
    map_calls = 0
    assert counter.at(10).run(Context()) == 10
    assert map_calls == 10


def test_cross_series_shared_cells_compute_once() -> None:
    calls = 0

    def base_cells() -> Iterator[tuple[int, F[float]]]:
        def tick() -> float:
            nonlocal calls
            calls += 1
            return 100.0

        yield 0, F.delay(tick)

    base = Series.from_cells(base_cells, label="Base")
    double = base.map(lambda x: x * 2, label="Double")
    triple = base.map(lambda x: x * 3, label="Triple")
    total = Series.map2(double, triple, lambda x, y: x + y, label="Total")

    ctx = Context()
    assert total.at(0).run(ctx) == 500.0
    assert calls == 1


def test_map2_misaligned_keys_raise() -> None:
    a = Series.from_pairs([(0, 1.0)], label="A")
    b = Series.from_pairs([(1, 2.0)], label="B")

    with pytest.raises(ValueError, match="misaligned keys"):
        Series.map2(a, b, lambda x, y: x + y, label="Sum").at(0).run(Context())


def test_merge_outer_combines_equal_keys() -> None:
    a = Series.from_pairs([(1, 1.0), (2, 2.0)], label="A")
    b = Series.from_pairs([(2, 20.0), (3, 30.0)], label="B")
    merged = Series.merge([a, b], lambda x, y: x + y, label="Merged")

    ctx = Context()
    assert [(key, cell.run(ctx)) for key, cell in merged.items(ctx)] == [
        (1, 1.0),
        (2, 22.0),
        (3, 30.0),
    ]


def test_items_replays_within_context() -> None:
    pulls = 0

    def cells() -> Iterator[tuple[int, F[int]]]:
        nonlocal pulls
        for i in range(3):
            pulls += 1
            yield i, Pure(i * 10)

    series = Series.from_cells(cells, label="Input")

    ctx = Context()
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3
    assert [(k, c.run(ctx)) for k, c in series.items(ctx)] == [(0, 0), (1, 10), (2, 20)]
    assert pulls == 3


def test_calendrical_year_ago_self_reference() -> None:
    """Historicals extended by revenue[q] = revenue[q - 1 year] * 1.1 via self-address."""
    historicals = [100.0, 110.0, 120.0, 130.0]

    def cells() -> Iterator[tuple[Period, F[float]]]:
        quarters = Period.seq(date(2025, 12, 31), relativedelta(months=3))
        for value, period in zip(historicals, quarters):
            yield period, Pure(value)
        for period in quarters:
            prior = revenue.at(period.shift(relativedelta(years=-1)))
            yield period, prior.map(lambda x: x * 1.1)

    revenue = Series.from_cells(cells, label="Revenue")
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 12))

    ctx = Context()
    assert revenue.at(quarters[4]).run(ctx) == pytest.approx(110.0)  # 100 * 1.1
    assert revenue.at(quarters[7]).run(ctx) == pytest.approx(143.0)  # 130 * 1.1
    assert revenue.at(quarters[11]).run(ctx) == pytest.approx(157.3)  # 130 * 1.1^2

    # Lookback goes through memoized address nodes: one node per (series, key).
    assert revenue.at(quarters[4]) is revenue.at(quarters[4])


def test_positional_year_ago_with_deque() -> None:
    """Same model with a positional 4-quarter lag carried in generator state."""
    from collections import deque

    historicals = [100.0, 110.0, 120.0, 130.0]
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 12))

    def cells() -> Iterator[tuple[Period, F[float]]]:
        window: deque[F[float]] = deque(maxlen=4)
        values = iter(historicals)
        for period in quarters:
            value = next(values, None)
            cell: F[float] = Pure(value) if value is not None else window[0].map(lambda x: x * 1.1)
            window.append(cell)
            yield period, cell

    revenue = Series.from_cells(cells, label="Revenue")

    ctx = Context()
    assert revenue.at(quarters[4]).run(ctx) == pytest.approx(110.0)
    assert revenue.at(quarters[11]).run(ctx) == pytest.approx(157.3)


def test_between_spanning_multiple_periods() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    ctx = Context()
    assert revenue.between(date(2025, 12, 31), date(2026, 12, 31)).run(ctx) == pytest.approx(460.0)


def test_between_exactly_one_period() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    ctx = Context()
    assert revenue.between(date(2025, 12, 31), date(2026, 3, 31)).run(ctx) == pytest.approx(100.0)


def test_between_part_of_one_period() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    # 30 days of Q1's 90: 100 * 30 / 90
    ctx = Context()
    assert revenue.between(date(2026, 1, 15), date(2026, 2, 14)).run(ctx) == pytest.approx(
        100.0 * 30 / 90
    )


def test_between_straddling_two_periods() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    # 30 tail days of Q1 (90 days) + 30 head days of Q2 (91 days)
    expected = 100.0 * 30 / 90 + 110.0 * 30 / 91
    ctx = Context()
    assert revenue.between(date(2026, 3, 1), date(2026, 4, 30)).run(ctx) == pytest.approx(expected)


def test_between_touching_no_periods() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    ctx = Context()
    assert revenue.between(date(2020, 1, 1), date(2020, 12, 31)).run(ctx) == 0.0
    assert revenue.between(date(2030, 1, 1), date(2030, 12, 31)).run(ctx) == 0.0


def test_between_window_past_series_end_sums_covered_part() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 4))
    revenue = Series.from_pairs(zip(quarters, [100.0, 110.0, 120.0, 130.0]), label="Revenue")

    ctx = Context()
    assert revenue.between(date(2026, 9, 30), date(2027, 12, 31)).run(ctx) == pytest.approx(130.0)


def test_between_terminates_on_infinite_series() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        for period in Period.seq(date(2025, 12, 31), relativedelta(months=3)):
            yield period, Pure(100.0)

    revenue = Series.from_cells(cells, label="Revenue")

    ctx = Context()
    assert revenue.between(date(2026, 3, 31), date(2026, 9, 30)).run(ctx) == pytest.approx(200.0)


def test_period_keyed_growth_series() -> None:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        cell: F[float] = Pure(100.0)
        for period in Period.seq(date(2025, 12, 31), relativedelta(years=1)):
            yield period, cell
            cell = cell.map(lambda value: value * 1.1)

    revenue = Series.from_cells(cells, label="Revenue")
    periods = list(islice(Period.seq(date(2025, 12, 31), relativedelta(years=1)), 3))

    ctx = Context()
    assert revenue.at(periods[2]).run(ctx) == pytest.approx(121.0)
    # A period before the series starts falls back to the default (uses ordering).
    early = Period(date(2020, 1, 1), date(2021, 1, 1))
    assert revenue.get(early, 0.0).run(ctx) == 0.0
