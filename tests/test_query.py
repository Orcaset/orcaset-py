# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

from orcaset import (
    YF,
    Context,
    Na,
    Period,
    Series,
    accrual,
    accrual_or,
    exact,
    exact_or,
    isna,
)

START = date(2026, 1, 1)
P1 = Period(START, date(2026, 2, 1))
P2 = Period(date(2026, 2, 1), date(2026, 3, 1))
P3 = Period(date(2026, 3, 1), date(2026, 4, 1))


def test_exact_or_returns_default_on_miss():
    series = Series(
        "values",
        lambda: [(P1, 10.0), (P2, 20.0)],
        exact_or(0.0),
    )

    ctx = Context()
    assert ctx.get_at(series, P1) == 10.0
    assert ctx.get_at(series, P2) == 20.0
    assert ctx.get_at(series, P3) == 0.0


def test_exact_still_returns_na_on_miss():
    series = Series(
        "values",
        lambda: [(P1, 10.0)],
        exact,
    )

    ctx = Context()
    assert isna(ctx.get_at(series, P2))
    assert ctx.get_at(series, P2) is Na


def test_accrual_or_returns_default_on_miss():
    series = Series(
        "revenue",
        lambda: [(P1, 100.0)],
        accrual_or(YF.cmonthly, 0.0),
    )

    ctx = Context()
    assert ctx.get_at(series, P1) == 100.0
    assert ctx.get_at(series, P3) == 0.0


def test_accrual_still_returns_na_on_miss():
    series = Series(
        "revenue",
        lambda: [(P1, 100.0)],
        accrual(YF.cmonthly),
    )

    ctx = Context()
    assert isna(ctx.get_at(series, P3))


def test_accrual_or_preserves_overlap_answers():
    series = Series(
        "revenue",
        lambda: [(Period(START, date(2026, 4, 1)), 90.0)],
        accrual_or(lambda a, b: (b - a).days, 0.0),
    )

    ctx = Context()
    # 31 / 90 of the quarter lands in January.
    assert ctx.get_at(series, P1) == 90.0 * 31 / 90
    assert ctx.get_at(series, P3) != 0.0
