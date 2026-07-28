# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import YF, Context, Period, flow, isna, level

MONTHLY = relativedelta(months=1)
QUARTERLY = relativedelta(months=3)


def months(start: date, end: date):
    return lambda: Period.seq(start, MONTHLY, end)


# ---------- flow ----------


def test_flow_exact_cell_query_answers_the_cell_value():
    s = flow("s", months(date(2026, 1, 1), date(2026, 4, 1)), lambda s, k: 100.0, yf=YF.cmonthly)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 2, 1), date(2026, 3, 1))) == pytest.approx(100.0)


def test_flow_spanning_whole_cells_sums():
    s = flow("s", months(date(2026, 1, 1), date(2026, 4, 1)), lambda s, k: 100.0, yf=YF.cmonthly)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 1, 1), date(2026, 4, 1))) == pytest.approx(300.0)


def test_flow_prorates_a_partial_cell_by_yf():
    # act360: June 1-16 is 15 of the 30 days in the June cell -> half the value
    s = flow("s", months(date(2026, 6, 1), date(2026, 7, 1)), lambda s, k: 300.0, yf=YF.act360)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 6, 1), date(2026, 6, 16))) == pytest.approx(150.0)


def test_flow_quarterly_grid_with_cmonthly_treats_each_month_as_a_twelfth():
    # One quarter cell of 100 on a month-end grid; a calendar month is
    # (1/12) / (3/12) = 1/3 of it (cmonthly is exact on month-end dates)
    quarters = lambda: Period.seq(date(2025, 12, 31), QUARTERLY, date(2026, 3, 31))
    s = flow("s", quarters, lambda s, k: 100.0, yf=YF.cmonthly)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 1, 31), date(2026, 2, 28))) == pytest.approx(100 / 3)


def test_flow_past_domain_end_sums_the_covered_part():
    s = flow("s", months(date(2026, 1, 1), date(2026, 3, 1)), lambda s, k: 100.0, yf=YF.cmonthly)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 2, 1), date(2026, 6, 1))) == pytest.approx(100.0)


def test_flow_fully_off_domain_answers_na():
    s = flow("s", months(date(2026, 1, 1), date(2026, 3, 1)), lambda s, k: 100.0, yf=YF.cmonthly)
    ctx = Context()
    assert isna(ctx.demand(s, Period(date(2027, 1, 1), date(2027, 2, 1))))


def test_flow_terminates_on_infinite_domains():
    infinite = lambda: Period.seq(date(2026, 1, 1), MONTHLY)  # no end
    s = flow("s", infinite, lambda s, k: 1.0, yf=YF.cmonthly)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 1, 1), date(2026, 3, 1))) == pytest.approx(2.0)


# ---------- level ----------


def test_level_within_one_cell_answers_the_value_identity():
    s = level("s", months(date(2026, 1, 1), date(2026, 4, 1)), lambda s, k: 42.0, yf=YF.act360)
    ctx = Context()
    assert ctx.demand(s, Period(date(2026, 2, 10), date(2026, 2, 20))) == pytest.approx(42.0)


def test_level_across_cells_answers_the_time_weighted_average():
    # June (30d) at 10, July (31d) at 20 under act360
    vals = {6: 10.0, 7: 20.0}
    s = level(
        "s",
        months(date(2026, 6, 1), date(2026, 8, 1)),
        lambda s, k: vals[k.start.month],
        yf=YF.act360,
    )
    ctx = Context()
    expected = (10.0 * 30 + 20.0 * 31) / 61
    assert ctx.demand(s, Period(date(2026, 6, 1), date(2026, 8, 1))) == pytest.approx(expected)


def test_level_fully_off_domain_answers_na():
    s = level("s", months(date(2026, 1, 1), date(2026, 3, 1)), lambda s, k: 1.0, yf=YF.act360)
    ctx = Context()
    assert isna(ctx.demand(s, Period(date(2030, 1, 1), date(2030, 2, 1))))


# ---------- composition ----------


def test_flow_and_level_compose_inline_without_dedicated_classes():
    # Same grid, different semantics per line item — constructor state only.
    grid = months(date(2026, 1, 1), date(2026, 4, 1))
    revenue = flow("revenue", grid, lambda s, k: 120.0, yf=YF.cmonthly)
    headcount = level("headcount", revenue.keys, lambda s, k: 5.0, yf=YF.act360)
    margin = revenue.map("margin", lambda w: w if isna(w) else w * 0.5)
    ctx = Context()
    q = Period(date(2026, 1, 1), date(2026, 3, 1))
    assert ctx.demand(revenue, q) == pytest.approx(240.0)
    assert ctx.demand(headcount, q) == pytest.approx(5.0)
    assert ctx.demand(margin, q) == pytest.approx(120.0)
