# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import operator
from collections.abc import Iterator
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    DateExtendSeries,
    DateSeries,
    Maybe,
    Na,
    Period,
    PeriodExtendSeries,
    PeriodSeries,
    Step,
    covered,
    exact,
    get_at,
    isna,
    last,
    map2_some,
)

MONTH = relativedelta(months=1)
Q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
Q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
Q3 = Period(date(2025, 7, 1), date(2025, 10, 1))


@PeriodSeries.define("hist_revenue", covered)
def hist_revenue() -> Iterator[tuple[Period, float]]:
    yield Q1, 300.0
    yield Q2, 330.0
    yield Q3, 363.0


@PeriodExtendSeries.define("revenue", hist_revenue, map2_some(operator.add))
def revenue(last: Period) -> PeriodSeries[Maybe[float]]:
    def cells() -> Iterator[tuple[Period, float]]:
        yield Period(last.end, last.end + MONTH), 100.0
        yield Period(last.end + MONTH, last.end + MONTH * 2), 110.0

    return PeriodSeries("forecast_revenue", cells, covered)


def test_period_extend_uses_base_inside_history():
    ctx = Context()
    assert ctx.get_at(revenue, Q1) == 300.0
    assert ctx.get_at(revenue, Q3) == 363.0
    assert isna(ctx.get_at(revenue, Period(date(2025, 9, 1), date(2025, 10, 1))))


def test_period_extend_uses_forecast_after_seam():
    ctx = Context()
    oct_ = Period(date(2025, 10, 1), date(2025, 11, 1))
    nov = Period(date(2025, 11, 1), date(2025, 12, 1))
    assert ctx.get_at(revenue, oct_) == 100.0
    assert ctx.get_at(revenue, nov) == 110.0


def test_period_extend_combines_aligned_span():
    ctx = Context()
    aligned = Period(date(2025, 7, 1), date(2025, 12, 1))
    misaligned = Period(date(2025, 9, 1), date(2025, 11, 1))
    assert ctx.get_at(revenue, aligned) == 573.0
    assert ctx.get_at(revenue, misaligned) is Na


def test_period_extend_keys_chain_base_then_forecast():
    ctx = Context()
    assert list(ctx.get(revenue.keys())) == [
        Q1,
        Q2,
        Q3,
        Period(date(2025, 10, 1), date(2025, 11, 1)),
        Period(date(2025, 11, 1), date(2025, 12, 1)),
    ]


def test_period_extend_empty_base_raises():
    empty = PeriodSeries("empty", list, covered)

    @PeriodExtendSeries.define("joined", empty, map2_some(operator.add))
    def joined(_last: Period) -> PeriodSeries[Maybe[float]]:
        return PeriodSeries("tail", list, covered)

    ctx = Context()
    with pytest.raises(ValueError, match="base series is empty"):
        ctx.get_at(joined, Q1)


def test_period_extend_with_builds_extend_series():
    def forecast(last_key: Period) -> PeriodSeries[Maybe[float]]:
        return PeriodSeries(
            "fluent_forecast",
            lambda: [(Period(last_key.end, last_key.end + MONTH), 100.0)],
            covered,
        )

    extended = hist_revenue.extend_with(
        "fluent_revenue",
        forecast,
        map2_some(operator.add),
    )

    assert isinstance(extended, PeriodExtendSeries)
    assert (
        Context().get_at(
            extended,
            Period(date(2025, 10, 1), date(2025, 11, 1)),
        )
        == 100.0
    )


D0 = date(2025, 1, 1)
D1 = date(2025, 4, 1)
D2 = date(2025, 7, 1)


@DateSeries.define("hist_cash", exact)
def hist_cash() -> Iterator[tuple[date, float]]:
    yield D0, 100.0
    yield D1, 110.0


@DateExtendSeries.define("cash", hist_cash)
def cash(last_key: date) -> DateSeries[Maybe[float]]:
    def cells() -> Iterator[tuple[date, CellFactory[float]]]:
        nxt = date(2025, 7, 1)

        def factory() -> Step[float]:
            prior = yield from get_at(hist_cash, last_key)
            if isna(prior):
                raise ValueError(f"missing last historical cash {last_key}")
            return prior + 5.0

        yield nxt, factory

    return DateSeries("forecast_cash", cells, last)


def test_date_extend_dispatches_to_base_at_or_before_last():
    ctx = Context()
    assert ctx.get_at(cash, D0) == 100.0
    assert ctx.get_at(cash, D1) == 110.0
    assert isna(ctx.get_at(cash, date(2025, 2, 1)))


def test_date_extend_dispatches_to_forecast_after_last():
    ctx = Context()
    assert ctx.get_at(cash, D2) == 115.0
    assert ctx.get_at(cash, date(2025, 8, 1)) == 115.0


def test_date_extend_keys_chain():
    ctx = Context()
    assert list(ctx.get(cash.keys())) == [D0, D1, D2]


def test_date_extend_gap_uses_base_miss_policy():
    # Dates between the last base key and the first forecast cell dispatch to
    # the base; ``exact`` history answers Na there.
    ctx = Context()
    assert isna(ctx.get_at(cash, date(2025, 5, 15)))


@DateSeries.define("hist_balance", last)
def hist_balance() -> Iterator[tuple[date, float]]:
    yield D0, 100.0
    yield D1, 110.0


@DateExtendSeries.define("balance", hist_balance)
def balance(last_key: date) -> DateSeries[Maybe[float]]:
    def cells() -> Iterator[tuple[date, CellFactory[float]]]:
        def factory() -> Step[float]:
            prior = yield from get_at(hist_balance, last_key)
            if isna(prior):
                raise ValueError(f"missing last historical balance {last_key}")
            return prior + 5.0

        yield D2, factory

    return DateSeries("forecast_balance", cells, last)


def test_date_extend_gap_carries_base_as_of_forward():
    # An as-of (``last``) base query answers the gap before the first forecast
    # cell, so the stock carries forward across the seam instead of going Na.
    ctx = Context()
    assert ctx.get_at(balance, date(2025, 5, 15)) == 110.0
    assert ctx.get_at(balance, date(2025, 6, 30)) == 110.0


def test_date_extend_continuation_owns_from_its_first_key():
    ctx = Context()
    assert ctx.get_at(balance, D2) == 115.0
    assert ctx.get_at(balance, date(2025, 8, 1)) == 115.0


def test_date_extend_empty_continuation_leaves_base_answering():
    @DateExtendSeries.define("carried", hist_balance)
    def carried(_last: date) -> DateSeries[Maybe[float]]:
        return DateSeries("empty_tail", list, last)

    ctx = Context()
    assert ctx.get_at(carried, date(2026, 1, 1)) == 110.0
    assert list(ctx.get(carried.keys())) == [D0, D1]


def test_date_extend_with_builds_extend_series():
    def forecast(_last_key: date) -> DateSeries[Maybe[float]]:
        return DateSeries("fluent_forecast", lambda: [(D2, 115.0)], last)

    extended = hist_balance.extend_with("fluent_balance", forecast)

    assert isinstance(extended, DateExtendSeries)
    assert Context().get_at(extended, D2) == 115.0
