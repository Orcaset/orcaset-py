# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Tests for the period <-> date transforms ``scan`` and ``paired``."""

import operator
from collections.abc import Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    CellStream,
    Context,
    DateSeries,
    Maybe,
    Na,
    Period,
    PeriodSeries,
    Step,
    accrual,
    exact,
    get,
    get_at,
    isna,
    last,
    map2_some,
    paired,
    scan,
)

MONTHLY = relativedelta(months=1)
JAN1 = date(2026, 1, 1)
FEB1 = date(2026, 2, 1)
MAR1 = date(2026, 3, 1)
APR1 = date(2026, 4, 1)

def _add(a: float, b: float) -> float:
    return a + b


def _sub(begin: float, end: float) -> float:
    return end - begin


add_maybe = map2_some(_add)
sub_maybe = map2_some(_sub)


def month(start: date) -> Period:
    return Period(start, start + MONTHLY)


# ---------- scan ----------


def test_scan_accumulates_flows_into_balances():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, APR1), [10.0, -3.0, 5.0]),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 100.0, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, JAN1) == 100.0
    assert ctx.get_at(balance, FEB1) == 110.0
    assert ctx.get_at(balance, MAR1) == 107.0
    assert ctx.get_at(balance, APR1) == 112.0


def test_scan_keys_are_opening_date_then_period_ends():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, MAR1), [1.0, 2.0]),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    assert list(ctx.get(balance.keys())) == [JAN1, FEB1, MAR1]


def test_scan_last_query_carries_between_grid_dates():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, MAR1), [10.0, 10.0]),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    # As-of semantics: mid-period dates carry the prior grid date's answer.
    assert ctx.get_at(balance, date(2026, 1, 15)) == 0.0
    assert ctx.get_at(balance, date(2026, 2, 15)) == 10.0
    # Before the opening date there is nothing to carry.
    assert isna(ctx.get_at(balance, date(2025, 12, 31)))


def test_scan_opening_accepts_cell_factory():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, MAR1), [1.0, 1.0]),
        accrual(YF.cmonthly),
    )

    def opening() -> Maybe[float]:
        return 50.0

    balance = scan("balance", flows, opening, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, JAN1) == 50.0
    assert ctx.get_at(balance, MAR1) == 52.0


def test_scan_gap_in_flow_grid_carries_prior_balance():
    # Flows only exist for January and March; the February gap contributes no
    # cell, so the March cell reads the carried February balance via `last`.
    def cells() -> Iterator[tuple[Period, float]]:
        yield month(JAN1), 10.0
        yield month(MAR1), 5.0

    flows = PeriodSeries("flows", cells, accrual(YF.cmonthly))
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, FEB1) == 10.0
    assert ctx.get_at(balance, MAR1) == 10.0  # carried across the gap
    assert ctx.get_at(balance, APR1) == 15.0


def test_scan_combine_receives_miss_sentinels():
    # A flow cell that is `Na` reaches the combiner as-is; the Na-propagating
    # combiner poisons that balance and every later one.
    def cells() -> Iterator[tuple[Period, Maybe[float]]]:
        yield month(JAN1), 10.0
        yield month(FEB1), Na
        yield month(MAR1), 5.0

    flows = PeriodSeries("flows", cells, exact)
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, FEB1) == 10.0
    assert isna(ctx.get_at(balance, MAR1))
    assert isna(ctx.get_at(balance, APR1))


def test_scan_lazy_over_infinite_flows():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY), (1.0 for _ in iter(int, 1))),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, MAR1) == 2.0


def test_scan_empty_flows_answers_na():
    flows = PeriodSeries("flows", lambda: iter(()), accrual(YF.cmonthly))
    balance = scan("balance", flows, 0.0, add_maybe, last)

    ctx = Context()
    assert isna(ctx.get_at(balance, JAN1))


def test_scan_flow_may_read_balance_at_period_start():
    # Interest-style feedback: the flow reads the scanned balance at its own
    # period start. No cycle: that read resolves to the prior period's cell.
    balance: DateSeries[Maybe[float]]

    @PeriodSeries.define("interest", accrual(YF.cmonthly))
    def interest() -> CellStream[Period, float]:
        for p in Period.seq(JAN1, MONTHLY, APR1):

            def cell(p: Period = p) -> Step[float]:
                begin = yield from get_at(balance, p.start)
                if isna(begin):
                    return 0.0
                return begin * 0.10

            yield p, cell

    balance = scan("balance", interest, 100.0, add_maybe, last)

    ctx = Context()
    assert ctx.get_at(balance, FEB1) == 110.0
    assert ctx.get_at(balance, MAR1) == 121.0
    apr = ctx.get_at(balance, APR1)
    assert not isna(apr) and round(apr, 6) == 133.1


# ---------- paired ----------


def _balances(values: list[float]) -> DateSeries[Maybe[float]]:
    def cells() -> Iterator[tuple[date, float]]:
        d = JAN1
        for v in values:
            yield d, v
            d += MONTHLY

    return DateSeries("balances", cells, last)


def test_paired_yields_deltas_between_consecutive_dates():
    deltas = paired("deltas", _balances([100.0, 110.0, 107.0]), sub_maybe, exact)

    ctx = Context()
    assert ctx.get_at(deltas, month(JAN1)) == 10.0
    assert ctx.get_at(deltas, month(FEB1)) == -3.0
    assert list(ctx.get(deltas.keys())) == [month(JAN1), month(FEB1)]


def test_paired_fn_receives_miss_sentinels():
    # `exact` answers Na between grid dates; a fn typed over Maybe sees it.
    balances = DateSeries(
        "balances",
        lambda: [(JAN1, 100.0), (MAR1, 90.0)],
        exact,
    )
    seen: list[tuple[Maybe[float], Maybe[float]]] = []

    def fn(begin: Maybe[float], end: Maybe[float]) -> Maybe[float]:
        seen.append((begin, end))
        return sub_maybe(begin, end)

    deltas = paired("deltas", balances, fn, exact)

    ctx = Context()
    assert ctx.get_at(deltas, Period(JAN1, MAR1)) == -10.0
    assert seen == [(100.0, 90.0)]


def test_paired_single_date_has_no_cells():
    deltas = paired("deltas", _balances([100.0]), sub_maybe, exact)

    ctx = Context()
    assert list(ctx.get(deltas.keys())) == []
    assert isna(ctx.get_at(deltas, month(JAN1)))


def test_paired_arbitrary_fn():
    growth = paired(
        "growth",
        _balances([100.0, 110.0, 99.0]),
        map2_some(lambda begin, end: end / begin - 1),
        exact,
    )

    ctx = Context()
    jan = ctx.get_at(growth, month(JAN1))
    feb = ctx.get_at(growth, month(FEB1))
    assert not isna(jan) and round(jan, 6) == 0.1
    assert not isna(feb) and round(feb, 6) == -0.1


# ---------- round trips ----------


def test_paired_of_scan_recovers_flows():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, APR1), [10.0, -3.0, 5.0]),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 100.0, add_maybe, last)
    recovered = paired("recovered", balance, sub_maybe, exact)

    ctx = Context()
    for p, expected in zip(Period.seq(JAN1, MONTHLY, APR1), [10.0, -3.0, 5.0]):
        assert ctx.get_at(recovered, p) == expected


def test_scan_of_paired_recovers_balances():
    balances = _balances([100.0, 110.0, 107.0])
    deltas = paired("deltas", balances, sub_maybe, exact)
    recovered = scan("recovered", deltas, 100.0, add_maybe, last)

    ctx = Context()
    for d in (JAN1, FEB1, MAR1):
        assert ctx.get_at(recovered, d) == ctx.get_at(balances, d)


def test_scan_and_paired_compose_with_operators():
    flows = PeriodSeries(
        "flows",
        lambda: zip(Period.seq(JAN1, MONTHLY, APR1), [10.0, -3.0, 5.0]),
        accrual(YF.cmonthly),
    )
    balance = scan("balance", flows, 100.0, add_maybe, last)
    doubled = balance * 2  # DateSeriesBase arithmetic surface
    deltas = paired("deltas", balance, sub_maybe, exact)
    total = (deltas + flows).named("total")  # PeriodSeriesBase arithmetic surface

    ctx = Context()
    assert ctx.get_at(doubled, FEB1) == 220.0
    assert ctx.get_at(total, month(JAN1)) == 20.0
