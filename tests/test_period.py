# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date

import pytest

from orcaset import Period, date_union, period_union

JAN, FEB, MAR, APR = (date(2026, m, 1) for m in (1, 2, 3, 4))


def test_period_union_passes_ordered_heads_through():
    assert period_union(Period(JAN, FEB), Period(MAR, APR)) == (
        Period(JAN, FEB),
        None,
        Period(MAR, APR),
    )
    assert period_union(Period(MAR, APR), Period(JAN, FEB)) == (
        Period(JAN, FEB),
        Period(MAR, APR),
        None,
    )


def test_period_union_consumes_equal_heads_once():
    assert period_union(Period(JAN, FEB), Period(JAN, FEB)) == (Period(JAN, FEB), None, None)


def test_period_union_splits_offset_starts():
    assert period_union(Period(JAN, MAR), Period(FEB, APR)) == (
        Period(JAN, FEB),
        Period(FEB, MAR),
        Period(FEB, APR),
    )


def test_period_union_splits_containment():
    assert period_union(Period(FEB, MAR), Period(JAN, APR)) == (
        Period(JAN, FEB),
        Period(FEB, MAR),
        Period(FEB, APR),
    )


def test_period_union_splits_shared_start():
    assert period_union(Period(JAN, MAR), Period(JAN, APR)) == (
        Period(JAN, MAR),
        None,
        Period(MAR, APR),
    )
    assert period_union(Period(JAN, APR), Period(JAN, MAR)) == (
        Period(JAN, MAR),
        Period(MAR, APR),
        None,
    )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (JAN, FEB, (JAN, None, FEB)),
        (FEB, JAN, (JAN, FEB, None)),
        (JAN, JAN, (JAN, None, None)),
    ],
)
def test_date_union_orders_and_dedupes(
    left: date, right: date, expected: tuple[date, date | None, date | None]
):
    assert date_union(left, right) == expected
