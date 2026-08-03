# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

import pytest

from orcaset import (
    Context,
    DateSeries,
    Na,
    Period,
    PeriodSeries,
    Series,
    exact,
    map2_some,
)

P1 = Period(date(2026, 1, 1), date(2026, 2, 1))
P2 = Period(date(2026, 2, 1), date(2026, 3, 1))
D1 = date(2026, 1, 1)
D2 = date(2026, 2, 1)


def test_period_scalar_and_unary_ops():
    revenue = PeriodSeries("Revenue", lambda: [(P1, 100.0), (P2, 200.0)], exact)
    costs = (revenue * -0.5).named("Costs")
    negated = -revenue

    ctx = Context()
    assert ctx.get_at(costs, P1) == -50.0
    assert ctx.get_at(costs, P2) == -100.0
    assert ctx.get_at(negated, P1) == -100.0
    assert costs.name == "Costs"
    assert (revenue * -0.5).name == "(Revenue * -0.5)"
    assert negated.name == "(-Revenue)"


def test_period_binary_ops():
    left = PeriodSeries("Left", lambda: [(P1, 10.0), (P2, 3.0)], exact)
    right = PeriodSeries("Right", lambda: [(P1, 5.0), (P2, 7.0)], exact)
    total = (left + right).named("Total")

    ctx = Context()
    assert ctx.get_at(total, P1) == 15.0
    assert ctx.get_at(total, P2) == 10.0
    assert (left + right).name == "(Left + Right)"
    assert total.name == "Total"


def test_period_binary_propagates_na_on_partial_overlap():
    only_left = PeriodSeries("OnlyLeft", lambda: [(P1, 10.0)], exact)
    only_right = PeriodSeries("OnlyRight", lambda: [(P2, 5.0)], exact)
    combined = only_left + only_right

    ctx = Context()
    # Domain is the period union, but each side misses the other's key.
    assert list(ctx.get(combined.keys())) == [P1, P2]
    assert ctx.get_at(combined, P1) is Na
    assert ctx.get_at(combined, P2) is Na


def test_reflected_scalar_ops():
    series = PeriodSeries("Values", lambda: [(P1, 10.0)], exact)
    ctx = Context()
    assert ctx.get_at(2 * series, P1) == 20.0
    assert ctx.get_at(100 - series, P1) == 90.0
    assert (2 * series).name == "(2 * Values)"


def test_date_series_arithmetic():
    cash = DateSeries("Cash", lambda: [(D1, 100.0), (D2, 150.0)], exact)
    debt = DateSeries("Debt", lambda: [(D1, 40.0), (D2, 50.0)], exact)
    equity = (cash - debt).named("Equity")

    ctx = Context()
    assert ctx.get_at(equity, D1) == 60.0
    assert ctx.get_at(equity, D2) == 100.0
    assert (cash - debt).name == "(Cash - Debt)"


def test_operator_chaining():
    left = PeriodSeries("Left", lambda: [(P1, 10.0)], exact)
    right = PeriodSeries("Right", lambda: [(P1, 4.0)], exact)
    result = (left + right) * 2 - 8.0

    ctx = Context()
    assert ctx.get_at(result, P1) == 20.0
    assert result.name == "(((Left + Right) * 2) - 8.0)"


def test_map2_accepts_generic_period_keyed_series():
    def add(a: float, b: float) -> float:
        return a + b

    flavored = PeriodSeries("Flavored", lambda: [(P1, 10.0)], exact)
    generic = Series("Generic", lambda: [(P1, 5.0)], exact)
    combined = flavored.map2("Combined", generic, map2_some(add))

    ctx = Context()
    assert ctx.get_at(combined, P1) == 15.0
    assert list(ctx.get(combined.keys())) == [P1]


def test_period_and_date_series_do_not_mix():
    period = PeriodSeries("Period", lambda: [(P1, 1.0)], exact)
    dates = DateSeries("Date", lambda: [(D1, 1.0)], exact)
    with pytest.raises(TypeError):
        period + dates  # type: ignore
    with pytest.raises(TypeError):
        dates + period  # type: ignore


def test_non_numeric_scalars_rejected_at_construction():
    revenue = PeriodSeries("Revenue", lambda: [(P1, 100.0)], exact)
    with pytest.raises(TypeError):
        revenue + "foo"  # type: ignore
    with pytest.raises(TypeError):
        revenue + None  # type: ignore
    with pytest.raises(TypeError):
        "foo" + revenue  # type: ignore
