# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from datetime import date
from itertools import islice

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import Period


def test_seq_quarter_boundaries_do_not_drift() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 8))

    assert quarters[0] == Period(date(2025, 12, 31), date(2026, 3, 31))
    assert quarters[3].end == date(2026, 12, 31)
    assert quarters[7].end == date(2027, 12, 31)


def test_seq_year_ago_keys_match_exactly() -> None:
    quarters = list(islice(Period.seq(date(2025, 12, 31), relativedelta(months=3)), 8))

    for later, earlier in zip(quarters[4:], quarters):
        assert later.shift(relativedelta(years=-1)) == earlier


def test_seq_end_clamps_final_period() -> None:
    periods = list(Period.seq(date(2026, 1, 1), relativedelta(years=1), date(2027, 6, 30)))

    assert periods[0] == Period(date(2026, 1, 1), date(2027, 1, 1))
    assert periods[-1].end == date(2027, 6, 30)


def test_non_overlapping_order() -> None:
    a = Period(date(2026, 1, 1), date(2026, 4, 1))
    c = Period(date(2026, 4, 1), date(2026, 7, 1))

    assert a < c
    assert c > a
    assert a <= c
    assert c >= a
    assert sorted([c, a]) == [a, c]


def test_equal_periods_compare_equal_not_ordered() -> None:
    a = Period(date(2026, 1, 1), date(2026, 4, 1))
    b = Period(date(2026, 1, 1), date(2026, 4, 1))

    assert a == b
    assert not (a < b)
    assert not (a > b)
    assert a <= b
    assert a >= b


def test_overlapping_periods_are_incomparable() -> None:
    a = Period(date(2026, 1, 1), date(2026, 4, 1))
    b = Period(date(2026, 1, 1), date(2026, 7, 1))
    c = Period(date(2026, 4, 1), date(2026, 7, 1))

    with pytest.raises(TypeError):
        _ = a < b
    with pytest.raises(TypeError):
        _ = a > b
    with pytest.raises(TypeError):
        _ = b < c
    with pytest.raises(TypeError):
        _ = a <= b
    with pytest.raises(TypeError):
        _ = sorted([c, b, a])
